import urllib.request
import urllib.error
import json

from config import GEMINI_API_KEY, GEMINI_MODEL

url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"
payload = {
    "contents": [{"parts": [{"text": "Hello, are you there?"}]}],
}
data = json.dumps(payload).encode("utf-8")

try:
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        print("Success:", resp.read().decode("utf-8")[:100])
except urllib.error.HTTPError as e:
    print(f"HTTP Error {e.code}")
    print(e.read().decode("utf-8"))
except Exception as e:
    print(f"Error: {e}")
