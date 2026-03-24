import os
import requests
from core_services import load_dotenv

load_dotenv()
api_key = os.getenv("GEMINI_API_KEY")

print(f"Listing Gemini models for key starting with: {api_key[:8]}...")

url = f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}"
try:
    response = requests.get(url, timeout=10)
    response.raise_for_status()
    result = response.json()
    for model in result['models']:
        print(f"- {model['name']} ({model['displayName']})")
except Exception as e:
    print(f"FAILED: {e}")
