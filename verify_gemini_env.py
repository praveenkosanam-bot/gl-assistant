import os
import requests
from core_services import load_dotenv

load_dotenv()
api_key = os.getenv("GEMINI_API_KEY")

print(f"Testing Gemini REST API with gemini-3-flash-preview...")

url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3-flash-preview:generateContent?key={api_key}"
headers = {"Content-Type": "application/json"}
payload = {
    "contents": [{"parts": [{"text": "Say 'Gemini 3 Flash Connection Successful'"}]}]
}

try:
    response = requests.post(url, headers=headers, json=payload, timeout=10)
    response.raise_for_status()
    result = response.json()
    text = result['candidates'][0]['content']['parts'][0]['text']
    print(f"SUCCESS: {text}")
except Exception as e:
    print(f"FAILED: {e}")
    if hasattr(e, 'response') and e.response is not None:
        print(f"Response: {e.response.text}")
