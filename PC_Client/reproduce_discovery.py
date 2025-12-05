import socket
import json
import threading
import time
from queue import Queue, Empty

# Mock configuration constants
CAMERA_DISCOVERY_PORT = 4213
DEFAULT_STREAM_PORT = 81

# Mock state
class MockState:
    def __init__(self):
        self.camera_ip = "192.168.4.1" # Initial incorrect state
        self.video_url = f"http://{self.camera_ip}:{DEFAULT_STREAM_PORT}/stream"
        self.bridge_ip = "192.168.4.1"
        self.logs = []
        self.is_running = True

state = MockState()

def add_log(msg):
    state.logs.append(msg)
    print(msg)

def _apply_camera_ip(ip, stream_url=None, prefix=""):
    updated = False
    if state.camera_ip != ip:
        state.camera_ip = ip
        state.video_url = stream_url or f"http://{ip}:{DEFAULT_STREAM_PORT}/stream"
        updated = True
        add_log(f"{prefix}Camera IP detected: {ip}")
        add_log(f"{prefix}Stream URL: {state.video_url}")
    
    if not state.bridge_ip or state.bridge_ip.endswith('.local') or state.bridge_ip != ip:
        state.bridge_ip = ip
        add_log(f"{prefix}Bridge host updated to {ip}")

def discovery_listener_thread():
    """Listens for UDP Broadcasts from ESP32 to auto-configure IP"""
    add_log(f"Discovery Listener Started on Port {CAMERA_DISCOVERY_PORT}...")
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        sock.bind(("0.0.0.0", CAMERA_DISCOVERY_PORT))
    except Exception as e:
        add_log(f"[DISCOVERY] Bind failed: {e}")
        return

    sock.settimeout(1.0)

    while state.is_running:
        try:
            data, addr = sock.recvfrom(1024)
            msg = data.decode('utf-8', errors='ignore')
            # Expecting JSON: {"device": "esp32-s3-car", "ip": "192.168.x.x"}
            if "{" in msg:
                try:
                    info = json.loads(msg)
                    if info.get("device") == "esp32-s3-car" and info.get("ip"):
                        new_ip = info["ip"]
                        if new_ip != state.camera_ip:
                            add_log(f"[DISCOVERY] Found Device at {new_ip}")
                            _apply_camera_ip(new_ip, prefix="[AUTO] ")
                except json.JSONDecodeError:
                    pass
        except socket.timeout:
            continue
        except Exception as e:
            add_log(f"[DISCOVERY] Error: {e}")
            time.sleep(1)

# Mock broadcaster
def mock_esp32_broadcast(target_ip="10.243.115.133"):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    
    msg = json.dumps({"device": "esp32-s3-car", "ip": target_ip})
    print(f"[MOCK] Broadcasting: {msg}")
    
    # Broadcast to localhost for testing since we are on the same machine
    # In real scenario, it broadcasts to 255.255.255.255
    sock.sendto(msg.encode(), ('127.0.0.1', CAMERA_DISCOVERY_PORT))
    sock.close()

if __name__ == "__main__":
    t = threading.Thread(target=discovery_listener_thread)
    t.start()
    
    time.sleep(2)
    mock_esp32_broadcast("10.243.115.133")
    
    time.sleep(2)
    state.is_running = False
    t.join()
    
    print("\nFinal State:")
    print(f"Camera IP: {state.camera_ip}")
    print(f"Video URL: {state.video_url}")
    
    if state.camera_ip == "10.243.115.133":
        print("SUCCESS: IP updated correctly.")
    else:
        print("FAILURE: IP did not update.")
""" (yolov13) PS D:\hmidata\project\PC_Client> python reproduce_discovery.py
Discovery Listener Started on Port 4213...
[DISCOVERY] Found Device at 10.243.115.133
[AUTO] Camera IP detected: 10.243.115.133
[AUTO] Stream URL: http://10.243.115.133:81/stream
[AUTO] Bridge host updated to 10.243.115.133
[MOCK] Broadcasting: {"device": "esp32-s3-car", "ip": "10.243.115.133"}

Final State:
Camera IP: 10.243.115.133
Video URL: http://10.243.115.133:81/stream
SUCCESS: IP updated correctly."""