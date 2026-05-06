import requests

# 测试通过 vite proxy 转换后的路径
# 前端调用 /api/query -> proxy 转换为 http://127.0.0.1:8001/query

response = requests.post(
    "http://127.0.0.1:8001/query",
    json={"question": "我的电脑经常死机怎么办"},
    timeout=120,
    headers={"Content-Type": "application/json"}
)
print(f"Status: {response.status_code}")
print(f"Response: {response.json()}")