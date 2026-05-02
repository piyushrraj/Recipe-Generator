import requests
import json
import time

BASE_URL = "http://localhost:8000"

test_cases = [
    # Basic cases
    {
        "ingredients": ["chicken", "garlic", "lemon", "rosemary"],
        "cuisine": "Italian"
    },
    {
        "ingredients": ["tofu", "soy sauce", "ginger", "bok choy", "sesame oil"],
        "cuisine": "Chinese"
    },
    {
        "ingredients": ["eggs", "cheese", "spinach", "mushrooms"],
        "cuisine": "French"
    },
    # Indian cuisine
    {
        "ingredients": ["paneer", "tomatoes", "onion", "garam masala", "cream"],
        "cuisine": "Indian"
    },
    {
        "ingredients": ["lentils", "cumin", "turmeric", "coriander", "garlic"],
        "cuisine": "Indian"
    },
    # Minimal ingredients
    {
        "ingredients": ["pasta", "olive oil", "garlic"],
        "cuisine": "Italian"
    },
    # Many ingredients
    {
        "ingredients": ["beef", "carrots", "potatoes", "onion", "celery", 
                        "thyme", "bay leaves", "red wine", "tomato paste"],
        "cuisine": "French"
    },
    # Any cuisine
    {
        "ingredients": ["rice", "beans", "corn", "avocado"],
        "cuisine": "any"
    },
    # Unusual combos
    {
        "ingredients": ["banana", "peanut butter", "oats", "honey"],
        "cuisine": "any"
    },
    {
        "ingredients": ["salmon", "miso", "sake", "mirin", "green onions"],
        "cuisine": "Japanese"
    },
]


def run_tests():
    print("=" * 60)
    print("RECIPE GENERATOR - TEST RUN")
    print("=" * 60)

    # 1. Health check first
    print("\n[1] Health Check")
    try:
        res = requests.get(f"{BASE_URL}/health")
        print(f"    Status : {res.status_code}")
        print(f"    Response: {res.json()}")
    except Exception as e:
        print(f"    ERROR: {e} — is your FastAPI server running?")
        return

    print("\n[2] Recipe Generation Tests")
    print("-" * 60)

    results = []

    for i, test in enumerate(test_cases, 1):
        print(f"\nTest {i}/{len(test_cases)}")
        print(f"  Cuisine     : {test['cuisine']}")
        print(f"  Ingredients : {', '.join(test['ingredients'])}")

        try:
            start = time.time()
            res = requests.post(
                f"{BASE_URL}/generate_recipe",
                json=test,
                timeout=120
            )
            elapsed = (time.time() - start) * 1000

            if res.status_code == 200:
                data = res.json()
                print(f"  Status      : ✅ 200 OK")
                print(f"  Tokens used : {data['tokens_used']}")
                print(f"  Latency     : {data['latency_ms']:.1f} ms")
                print(f"  Recipe preview:")
                # Print first 3 lines of recipe
                preview = "\n".join(data["recipe"].split("\n")[:3])
                print(f"    {preview}")

                results.append({
                    "test": i,
                    "cuisine": test["cuisine"],
                    "status": "PASS",
                    "tokens": data["tokens_used"],
                    "latency_ms": round(data["latency_ms"], 1)
                })
            else:
                print(f"  Status      : ❌ {res.status_code}")
                print(f"  Error       : {res.json()}")
                results.append({
                    "test": i,
                    "cuisine": test["cuisine"],
                    "status": "FAIL",
                    "tokens": 0,
                    "latency_ms": 0
                })

        except requests.exceptions.Timeout:
            print(f"  Status      : ⏰ TIMEOUT (>120s)")
            results.append({
                "test": i,
                "cuisine": test["cuisine"],
                "status": "TIMEOUT",
                "tokens": 0,
                "latency_ms": 0
            })
        except Exception as e:
            print(f"  Status      : ❌ ERROR — {e}")
            results.append({
                "test": i,
                "cuisine": test["cuisine"],
                "status": "ERROR",
                "tokens": 0,
                "latency_ms": 0
            })

        # Small delay between requests to avoid overwhelming Ollama
        time.sleep(2)

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    passed  = sum(1 for r in results if r["status"] == "PASS")
    failed  = sum(1 for r in results if r["status"] == "FAIL")
    timeout = sum(1 for r in results if r["status"] == "TIMEOUT")
    errors  = sum(1 for r in results if r["status"] == "ERROR")

    print(f"  Total   : {len(results)}")
    print(f"  ✅ Pass  : {passed}")
    print(f"  ❌ Fail  : {failed}")
    print(f"  ⏰ Timeout: {timeout}")
    print(f"  💥 Error : {errors}")

    if passed > 0:
        avg_tokens  = sum(r["tokens"] for r in results if r["status"] == "PASS") / passed
        avg_latency = sum(r["latency_ms"] for r in results if r["status"] == "PASS") / passed
        print(f"\n  Avg tokens/request  : {avg_tokens:.0f}")
        print(f"  Avg latency/request : {avg_latency:.0f} ms")

    print("\nFull Results:")
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    run_tests()