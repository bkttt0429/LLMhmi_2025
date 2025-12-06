"""
直接测试 /api/control 端点
"""
import requests
import json

url = "http://127.0.0.1:5000/api/control"

payload = {"left": 200, "right": 200}

print("=" * 60)
print(f"Testing {url}")
print(f"Payload: {payload}")
print("=" * 60)

try:
    response = requests.post(
        url,
        json=payload,
        headers={'Content-Type': 'application/json'},
        timeout=2.0
    )
    
    print(f"✅ Response received!")
    print(f"   Status Code: {response.status_code}")
    print(f"   Response Text: {response.text}")
    print("=" * 60)
    
except requests.exceptions.ConnectionError as e:
    print(f"❌ CONNECTION ERROR:")
    print(f"   Cannot connect to {url}")
    print(f"   Is the server running?")
    print(f"   Details: {e}")
    
except Exception as e:
    print(f"❌ ERROR: {e}")
