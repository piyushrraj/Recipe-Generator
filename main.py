import os
import time
import asyncio
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List
from openai import OpenAI
from dotenv import load_dotenv

import backoff
import openai

from azure.monitor.opentelemetry import configure_azure_monitor
from opentelemetry import trace, metrics
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

load_dotenv()

# 1. TELEMETRY SETUP
configure_azure_monitor(
    connection_string=os.getenv("APPLICATIONINSIGHTS_CONNECTION_STRING")
)

meter = metrics.get_meter(__name__)
token_counter = meter.create_counter(
    name="openai.tokens",
    description="Number of tokens consumed",
    unit="tokens"
)
request_counter = meter.create_counter(
    name="api.requests",
    description="Number of API requests",
    unit="requests"
)
latency_histogram = meter.create_histogram(
    name="api.latency",
    description="Request latency",
    unit="ms"
)

tracer = trace.get_tracer(__name__)

# 2. CLIENT SETUP (Ollama Local API)
client = OpenAI(
    api_key="ollama",       # required by the lib but ignored by Ollama
    base_url="http://localhost:11434/v1",
    timeout=60.0            # prevent indefinite hangs
)

# # pip install openai
# from openai import OpenAI

# client = OpenAI(
#     api_key=os.getenv("OPENAI_API_KEY"),
#     timeout=60.0
# )

# # Change model in call_llm() to:
# model="gpt-4o"   # or "gpt-3.5-turbo" for cheaper

# # pip install openai  (same lib, different client)
# from openai import AzureOpenAI

# client = AzureOpenAI(
#     api_key=os.getenv("AZURE_OPENAI_API_KEY"),
#     azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),  # e.g. https://YOUR-RESOURCE.openai.azure.com/
# )

# # Change model in call_llm() to your deployment name:
# model=os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME")  # e.g. "gpt-4o-deployment"

app = FastAPI(title="AI Recipe Generator with AIOps")
FastAPIInstrumentor.instrument_app(app)  # Auto-traces FastAPI HTTP requests


# 3. REQUEST / RESPONSE MODELS
class RecipeRequest(BaseModel):
    ingredients: List[str]
    cuisine: str = "any"

class RecipeResponse(BaseModel):
    recipe: str
    tokens_used: int
    latency_ms: float


# 4. LLM CALL (with backoff)
@backoff.on_exception(
    backoff.expo,
    openai.RateLimitError,
    max_tries=5,
    jitter=backoff.full_jitter
)
def call_llm(system_prompt: str, user_prompt: str):
    """Isolated LLM call so @backoff retries the right function."""
    return client.chat.completions.create(
        model="llama3.2",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        temperature=0.8,
        max_tokens=600
    )


# 5. ROUTES
@app.post("/generate_recipe", response_model=RecipeResponse)
async def generate_recipe(request: RecipeRequest):
    """Generates a recipe based on a list of ingredients."""
    start_time = time.time()

    # Increment request counter
    request_counter.add(1, {"cuisine": request.cuisine})

    with tracer.start_as_current_span("generate_recipe") as span:
        span.set_attribute("ingredients.count", len(request.ingredients))
        span.set_attribute("cuisine", request.cuisine)

        system_prompt = """You are a world-class chef and recipe creator.
        Your task is to generate a creative, delicious, and easy-to-follow recipe
        using the ingredients provided by the user.
        Format your response with a Title, a '## Ingredients' section, and a '## Instructions' section."""

        user_prompt = (
            f"I have the following ingredients: {', '.join(request.ingredients)}. "
            f"I would like a {request.cuisine} dish. Can you suggest a recipe?"
        )

        try:
            with tracer.start_as_current_span("local_llm_completion") as llm_span:
                # Run the sync LLM call in a thread so we don't block the event loop
                response = await asyncio.get_event_loop().run_in_executor(
                    None, call_llm, system_prompt, user_prompt
                )

                # Token tracking — only prompt + completion to avoid double-counting
                tokens_prompt = response.usage.prompt_tokens if response.usage else 0
                tokens_completion = response.usage.completion_tokens if response.usage else 0
                tokens_total = tokens_prompt + tokens_completion

                if response.usage:
                    token_counter.add(tokens_prompt, {"type": "prompt"})
                    token_counter.add(tokens_completion, {"type": "completion"})
                    llm_span.set_attribute("tokens.prompt", tokens_prompt)
                    llm_span.set_attribute("tokens.completion", tokens_completion)
                    llm_span.set_attribute("tokens.total", tokens_total)

                # Latency
                latency_ms = (time.time() - start_time) * 1000
                latency_histogram.record(latency_ms, {"endpoint": "generate_recipe"})
                span.set_attribute("latency_ms", latency_ms)
                span.set_attribute("success", True)

                return RecipeResponse(
                    recipe=response.choices[0].message.content,
                    tokens_used=tokens_total,
                    latency_ms=latency_ms
                )

        except openai.RateLimitError as e:
            span.set_attribute("success", False)
            span.set_attribute("error", "RateLimitError")
            span.record_exception(e)
            raise HTTPException(status_code=429, detail="Rate limit reached after retries.")

        except Exception as e:
            span.set_attribute("success", False)
            span.set_attribute("error", str(e))
            span.record_exception(e)
            raise HTTPException(status_code=500, detail=f"An error occurred: {str(e)}")


@app.get("/health")
async def health_check():
    return {"status": "healthy", "timestamp": time.time()}