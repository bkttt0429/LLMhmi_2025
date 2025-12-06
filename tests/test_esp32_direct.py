"""
ESP32 Motor Control Diagnostic Tool
直接測試 ESP32 /motor 端點的連線能力
"""
import requests
import sys

def test_esp32_motor(esp32_ip, left=200, right=200):
    """Test direct HTTP GET to ESP32 /motor endpoint"""
    url = f"http://{esp32_ip}/motor"
    params = {"left": left, "right": right}
    
    print("=" * 60)
    print(f"🚗 ESP32 Motor Control Test")
    print("=" * 60)
    print(f"Target IP: {esp32_ip}")
    print(f"Endpoint: {url}")
    print(f"Parameters: {params}")
    print("-" * 60)
    
    try:
        print(f"⏳ Sending GET request...")
        resp = requests.get(url, params=params, timeout=2.0)
        
        print(f"✅ Response received!")
        print(f"   Status Code: {resp.status_code}")
        print(f"   Content-Type: {resp.headers.get('Content-Type', 'N/A')}")
        print(f"   Response Body: {resp.text[:200]}")
        print("=" * 60)
        
        if resp.status_code == 200:
            print("✅ SUCCESS: ESP32 accepted the command!")
            return True
        else:
            print(f"⚠️  WARNING: ESP32 returned non-200 status")
            return False
            
    except requests.exceptions.Timeout:
        print(f"⏱️  TIMEOUT: ESP32 did not respond within 2 seconds")
        print(f"   → Check if ESP32 is powered on")
        print(f"   → Verify IP address is correct: {esp32_ip}")
        return False
        
    except requests.exceptions.ConnectionError as e:
        print(f"🔌 CONNECTION ERROR: Cannot reach ESP32")
        print(f"   → Verify IP address: {esp32_ip}")
        print(f"   → Check if PC and ESP32 are on same network")
        print(f"   → Details: {e}")
        return False
        
    except Exception as e:
        print(f"💥 UNEXPECTED ERROR: {e}")
        return False

if __name__ == "__main__":
    # Default IP (change this to your ESP32's actual IP)
    esp32_ip = "10.243.115.133"  # <-- CHANGE THIS!
    
    if len(sys.argv) > 1:
        esp32_ip = sys.argv[1]
    
    print(f"\n使用方法: python test_esp32_direct.py [ESP32_IP]")
    print(f"目前使用 IP: {esp32_ip}\n")
    
    # Test forward
    print("\n[Test 1] Forward (前進)")
    test_esp32_motor(esp32_ip, left=200, right=200)
    
    import time
    time.sleep(1)
    
    # Test stop
    print("\n[Test 2] Stop (停止)")
    test_esp32_motor(esp32_ip, left=0, right=0)
