import os
import requests
from core_services import load_dotenv

load_dotenv()
api_key = os.getenv("OPENAI_API_KEY")
model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

if not api_key or "your_openai_api_key_here" in api_key:
    print("ERROR: OPENAI_API_KEY is not set correctly in .env")
    exit(1)

print(f"Testing OpenAI with model: {model}...")
print(f"Using key starting with: {api_key[:8]}...")

url = "https://api.openai.com/v1/chat/completions"
headers = {
    "Authorization": f"Bearer {api_key}",
    "Content-Type": "application/json"
}
payload = {
    "model": model,
    "messages": [{"role": "user", "content": "Say 'Connection Successful'"}],
    "max_tokens": 10
}

try:
    response = requests.post(url, headers=headers, json=payload, timeout=10)
    response.raise_for_status()
    result = response.json()
    message = result['choices'][0]['message']['content']
    print(f"SUCCESS: {message}")
except Exception as e:
    print(f"FAILED: {e}")
    if hasattr(e, 'response') and e.response is not None:
        print(f"Response: {e.response.text}")
