import requests

response = requests.post(
    "http://127.0.0.1:8001/query",
    json={"question": "我的电脑经常死机怎么办"},
    timeout=120
)
print(f"Status: {response.status_code}")
print(f"Response: {response.text}")