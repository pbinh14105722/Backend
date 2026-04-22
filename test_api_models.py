#!/usr/bin/env python3
"""
Test Anthropic API Key - Check available models
Usage: python test_api_models.py
"""

import sys
import json

try:
    import anthropic
except ImportError:
    print("❌ Installing anthropic package...")
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "anthropic", "--break-system-packages", "-q"])
    import anthropic

# Try to get API key
API_KEY = None

# Method 1: From database.py
try:
    sys.path.insert(0, '.')
    import database
    API_KEY = database.ANTHROPIC_API_KEY
    print(f"✅ Found API key in database.py")
except Exception as e:
    print(f"⚠️ Cannot import from database.py: {e}")

# Method 2: Ask user
if not API_KEY:
    print("\n🔑 Please enter your Anthropic API Key:")
    API_KEY = input("API Key: ").strip()

if not API_KEY:
    print("❌ No API key provided!")
    sys.exit(1)

# Mask for display
masked = f"{API_KEY[:8]}...{API_KEY[-4:]}"
print(f"📝 Using key: {masked}\n")

# Initialize client
client = anthropic.Anthropic(api_key=API_KEY)

# Test models
models_to_test = [
    ("Haiku 4.5", "claude-haiku-4-5-20251001"),
    ("Sonnet 4.5", "claude-sonnet-4-20250514"),
    ("Sonnet 4.6", "claude-sonnet-4-6"),
    ("Opus 4.6", "claude-opus-4-6"),
]

print("=" * 70)
print("Testing Claude Models Access")
print("=" * 70)

test_message = "Hello, respond with just 'OK'"

results = []

for name, model_id in models_to_test:
    try:
        response = client.messages.create(
            model=model_id,
            max_tokens=10,
            messages=[{"role": "user", "content": test_message}]
        )
        
        status = "✅ AVAILABLE"
        reply = response.content[0].text
        tokens = f"{response.usage.input_tokens}→{response.usage.output_tokens}"
        
        results.append({
            "name": name,
            "model": model_id,
            "status": status,
            "reply": reply[:20],
            "tokens": tokens
        })
        
        print(f"\n{status} - {name}")
        print(f"  Model ID: {model_id}")
        print(f"  Response: {reply[:50]}")
        print(f"  Tokens: {tokens}")
        
    except anthropic.BadRequestError as e:
        if "model" in str(e).lower():
            status = "❌ NOT AVAILABLE"
            results.append({
                "name": name,
                "model": model_id,
                "status": status,
                "error": "Model not accessible with this API key"
            })
            print(f"\n{status} - {name}")
            print(f"  Model ID: {model_id}")
            print(f"  Error: Model not available")
        else:
            print(f"\n❌ ERROR - {name}: {e}")
    
    except anthropic.AuthenticationError:
        print(f"\n❌ AUTHENTICATION ERROR")
        print(f"  Your API key is invalid!")
        sys.exit(1)
    
    except Exception as e:
        print(f"\n❌ ERROR - {name}: {type(e).__name__}: {e}")

print("\n" + "=" * 70)
print("SUMMARY")
print("=" * 70)

available_models = [r for r in results if "AVAILABLE" in r.get("status", "")]
unavailable_models = [r for r in results if "NOT AVAILABLE" in r.get("status", "")]

print(f"\n✅ Available models ({len(available_models)}):")
for r in available_models:
    print(f"  • {r['name']}: {r['model']}")

if unavailable_models:
    print(f"\n❌ Unavailable models ({len(unavailable_models)}):")
    for r in unavailable_models:
        print(f"  • {r['name']}: {r['model']}")

print("\n" + "=" * 70)
print("RECOMMENDATION")
print("=" * 70)

if available_models:
    # Recommend best available model
    if any("Sonnet 4.6" in r['name'] for r in available_models):
        rec = "claude-sonnet-4-6"
        print(f"\n🎯 RECOMMENDED: Claude Sonnet 4.6")
        print(f"   Model ID: {rec}")
        print(f"   Reason: Best balance of quality, speed, and cost")
    elif any("Sonnet 4.5" in r['name'] for r in available_models):
        rec = "claude-sonnet-4-20250514"
        print(f"\n🎯 RECOMMENDED: Claude Sonnet 4.5")
        print(f"   Model ID: {rec}")
        print(f"   Reason: Good balance, widely available")
    elif any("Haiku" in r['name'] for r in available_models):
        rec = "claude-haiku-4-5-20251001"
        print(f"\n🎯 RECOMMENDED: Claude Haiku 4.5")
        print(f"   Model ID: {rec}")
        print(f"   Reason: Fastest and cheapest available")
    else:
        rec = available_models[0]['model']
        print(f"\n🎯 RECOMMENDED: {available_models[0]['name']}")
        print(f"   Model ID: {rec}")
else:
    print("\n❌ No models available with this API key!")
    print("   Please check your API key or Anthropic account status")

print("\n" + "=" * 70)
print("To use in your code:")
print("=" * 70)
print(f"""
response = client.messages.create(
    model="{rec if available_models else 'YOUR_MODEL_HERE'}",
    max_tokens=8192,
    messages=[...]
)
""")

print("\n✅ Test complete!\n")
