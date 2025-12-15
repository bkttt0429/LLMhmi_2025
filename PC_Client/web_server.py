import sys
import os
import struct
import cv2
import time
import threading
import re
import socket
import select
import math
import psutil
from pathlib import Path
import queue
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import serial
import pygame
import json
import websocket
from queue import SimpleQueue, Empty
from serial.tools import list_ports
from flask import Flask, render_template, Response, request, jsonify, send_from_directory
from flask_socketio import SocketIO, emit
from multiprocessing import Process, Queue

# 路徑設定
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.append(BASE_DIR)
import config

# 導入 Serial Worker 和燒錄函數
from serial_worker import serial_worker, prepare_sketch, compile_and_upload

# 導入 AI 模組
from ai_detector import YOLO_AVAILABLE

# 導入 Video Process
from video_process import video_process_target, CMD_SET_URL, CMD_SET_AI, CMD_SET_MODEL, CMD_EXIT
from video_config import build_initial_video_config
from network_utils import SourceAddressAdapter

# 初始化 Flask 和 SocketIO
template_dir = os.path.join(BASE_DIR, 'templates')
static_dir = os.path.join(BASE_DIR, 'static')
app = Flask(__name__, template_folder=template_dir, static_folder=static_dir)
# CRITICAL: Disable template caching to force browser reload
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0
app.config['TEMPLATES_AUTO_RELOAD'] = True
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

BRIDGE_CACHE_FILE = Path(BASE_DIR) / ".last_bridge_host"


def _is_host_reachable(host: str, port: int, timeout: float = 1.0) -> bool:
    """Check whether a TCP connection to ``host:port`` can be established."""

    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _clear_cached_bridge_host():
    """Remove the cached bridge host file when it is stale or invalid."""

    try:
        BRIDGE_CACHE_FILE.unlink()
    except FileNotFoundError:
        pass
    except Exception:
        pass

# === 雙網卡自動偵測邏輯 ===
def get_network_info():
    """偵測所有網卡並自動分類為 Camera Net 或 Internet Net"""
    info = {
        "all_ifaces": [],
        "camera_net": None,
        "internet_net": None
    }

    try:
        stats = psutil.net_if_stats()
        addrs = psutil.net_if_addrs()

        for iface_name, iface_addrs in addrs.items():
            if iface_name in stats and not stats[iface_name].isup:
                continue

            ip_info = None
            mac_info = None

            for addr in iface_addrs:
                if addr.family == socket.AF_INET:
                    ip_info = addr.address
                elif addr.family == psutil.AF_LINK:
                    mac_info = addr.address

            if ip_info and ip_info != "127.0.0.1":
                iface_data = {
                    "name": iface_name,
                    "ip": ip_info,
                    "mac": mac_info
                }
                info["all_ifaces"].append(iface_data)

                # 分類規則
                if ip_info.startswith("192.168.4."):
                    if info["camera_net"] is None:
                        info["camera_net"] = iface_data
                elif info["internet_net"] is None:
                    # 假設第一個非相機網段的介面為 Internet/Car Control 網段
                    info["internet_net"] = iface_data

    except Exception as e:
        print(f"[NET] Detection Error: {e}")

    return info

def _unique_hosts(hosts):
    seen = set()
    ordered = []
    for host in hosts:
        if host and host not in seen:
            ordered.append(host)
            seen.add(host)
    return ordered

def find_reachable_interface(target_ip):
    """
    Find which local network interface can reach the target IP.
    Returns the local IP that's on the same subnet as target_ip.
    """
    try:
        # Parse target IP into octets
        target_parts = target_ip.split('.')
        if len(target_parts) != 4:
            return None

        target_subnet = '.'.join(target_parts[:3])  # e.g., "10.243.115"

        # Check all network interfaces
        addrs = psutil.net_if_addrs()
        for iface_name, iface_addrs in addrs.items():
            for addr in iface_addrs:
                if addr.family == socket.AF_INET:
                    local_ip = addr.address
                    if local_ip == "127.0.0.1":
                        continue

                    local_parts = local_ip.split('.')
                    if len(local_parts) == 4:
                        local_subnet = '.'.join(local_parts[:3])

                        # If on same subnet, this interface can reach the target
                        if local_subnet == target_subnet:
                            # print(f"[NET] Found reachable interface: {iface_name} ({local_ip}) can reach {target_ip}")
                            return local_ip
    except Exception as e:
        print(f"[NET] Error finding reachable interface: {e}")

    return None

def _apply_camera_ip(ip, stream_url=None, prefix=""):
    """
    Apply discovered camera IP and update video process configuration.
    Now includes smart interface detection.
    """
    updated = False
    if state.camera_ip != ip:
        state.camera_ip = ip
        state.video_url = stream_url or f"http://{ip}:{config.DEFAULT_STREAM_PORT}/stream"
        updated = True

        # Find which local interface can reach this camera
        reachable_interface = find_reachable_interface(ip)
        if reachable_interface:
            state.camera_net_ip = reachable_interface
        else:
            state.camera_net_ip = None

        # Simplified Logging
        msg = f"{prefix}Camera found at {ip} (via {reachable_interface if reachable_interface else 'Default Route'})"
        add_log(msg)
    
    if not state.bridge_ip or state.bridge_ip.endswith('.local') or state.bridge_ip != ip:
        state.bridge_ip = ip
        _persist_bridge_host(ip)
        # add_log(f"{prefix}Bridge host updated to {ip}") # Reduced noise

    # [WS] Update WebSocket Target if IP changed
    if state.ws_client and state.ws_client.target_ip != ip:
        print(f"[WS] IP Changed to {ip}, restarting client...")
        state._init_ws_client(ip)
    elif not state.ws_client and ip:
        state._init_ws_client(ip)

    # Notify Video Process immediately if updated
    if updated and video_cmd_queue:
        config_update = {
            'url': state.video_url,
            'source_ip': state.camera_net_ip
        }
        video_cmd_queue.put((CMD_SET_URL, config_update))
        # add_log(f"{prefix}Video process notified") # Reduced noise

def _build_stream_url(host: str | None):
    if not host:
        return ""
    return f"http://{host}:{config.DEFAULT_STREAM_PORT}/stream"

def _load_cached_bridge_host():
    try:
        content = BRIDGE_CACHE_FILE.read_text(encoding="utf-8").strip()
        return content or None
    except FileNotFoundError:
        return None
    except Exception:
        return None

def _persist_bridge_host(host: str):
    if not host:
        return
    try:
        BRIDGE_CACHE_FILE.write_text(host, encoding="utf-8")
    except Exception:
        pass

import websocket
import threading
import json
import time # Added for time.sleep

# ⭐ WebSocket Client for Low Latency Control
class AsyncControlClient:
    def __init__(self, target_ip):
        self.target_ip = target_ip
        self.ws_url = f"ws://{target_ip}/ws/control"
        self.ws = None
        self.connected = False
        self.lock = threading.Lock()
        self.running = True
        
        # Start background worker
        self.thread = threading.Thread(target=self._worker, daemon=True)
        self.thread.start()

    def _worker(self):
        print(f"[WS] Worker started for {self.ws_url}")
        while self.running:
            try:
                # 1. Connect
                self.ws = websocket.WebSocket()
                self.ws.connect(self.ws_url, timeout=1.0)
                
                with self.lock:
                    self.connected = True
                print(f"[WS] ✅ Connected to {self.target_ip}")
                
                # 2. Keep Connection Alive (Receive Loop)
                while self.running:
                    try:
                        # Simple Ping-Pong or just wait for close
                        # ESP might send stats later
                        result = self.ws.recv() 
                    except (websocket.WebSocketException, ConnectionError):
                        print("[WS] ⚠️ Connection Lost")
                        break
                        
            except Exception as e:
                # print(f"[WS] Connection Failed: {e}") # Reduce noise
                time.sleep(2) # Retry delay
            finally:
                with self.lock:
                    self.connected = False
                if self.ws:
                    try: self.ws.close()
                    except: pass
                # Reconnect delay
                time.sleep(1)

    def send(self, left, right):
        if not self.connected:
            return False
        
        try:
            payload = json.dumps({"l": left, "r": right})
            with self.lock:
                self.ws.send(payload)
            return True
        except Exception as e:
            print(f"[WS] Send Error: {e}")
            return False

    def close(self):
        self.running = False
        if self.ws: self.ws.close()



# === 全域狀態 ===
class SystemState:
    def __init__(self):
        # 1. 執行網卡偵測
        self.net_info = get_network_info()
        self.print_network_summary()

        # 記錄對應介面的 Source IP
        self.camera_net_ip = self.net_info["camera_net"]["ip"] if self.net_info["camera_net"] else None
        self.internet_net_ip = self.net_info["internet_net"]["ip"] if self.net_info["internet_net"] else None

        cached_bridge = _load_cached_bridge_host()
        if cached_bridge and not _is_host_reachable(cached_bridge, config.DEFAULT_STREAM_PORT):
            print(f"[INIT] Cached camera IP {cached_bridge} unreachable on port {config.DEFAULT_STREAM_PORT}, clearing cache.")
            cached_bridge = None
            _clear_cached_bridge_host()

        default_stream_hosts = getattr(config, "DEFAULT_STREAM_HOSTS", [])
        default_stream_ip = getattr(config, "DEFAULT_STREAM_IP", "")

        # 2. 自動設定 IP
        if self.net_info["camera_net"]:
            self.camera_ip = "192.168.4.1"
            print(f"[INIT] Auto-selected Camera IP: {self.camera_ip} (via {self.net_info['camera_net']['name']})")
        else:
            # Use config defaults when no camera_net detected
            self.camera_ip = cached_bridge or getattr(config, "DEFAULT_STREAM_IP", "") or getattr(config, "DEFAULT_CAR_IP", "")
            if self.camera_ip:
                print(f"[INIT] Using configured Camera IP: {self.camera_ip}")

        self.car_ip = getattr(config, "DEFAULT_CAR_IP", "boebot.local")
        self.current_ip = self.car_ip
        self.bridge_ip = cached_bridge or default_stream_ip or getattr(config, "DEFAULT_CAR_IP", "")

        self.stream_hosts = _unique_hosts([
            self.camera_ip,
            cached_bridge,
            default_stream_ip,
            *default_stream_hosts,
            self.bridge_ip,
        ])

        if not self.camera_ip and self.stream_hosts:
            self.camera_ip = self.stream_hosts[0]

        self.serial_port = None
        self.preferred_port = None
        self.ser = None
        self.ws_connected = False
        self.ws_client = None # [FIX] Initialize before use
        self.arm_ip = None  # [Reset] Discovery will fill this
        self.video_url = _build_stream_url(self.camera_ip)
        self.radar_dist = 0.0
        self.logs = []
        self.is_running = True
        self.ai_enabled = False
        self.is_flashing = False
        self.flash_lock = threading.Lock()
        self.add_log = None
        
        self.frame_buffer = None # Now stores JPEG bytes directly
        self.frame_lock = threading.Lock()
        self.stream_connected = False
        self.last_api_control_time = 0.0  # [Input Priority] Track last API/Keyboard command
        self.last_motor_cmd = (0, 0)      # [Soft Start] Track last sent PWM values
        self.last_arm_cmd_json = ""       # [Deduplication] Track last sent Arm JSON
        
        self.consecutive_failures = 0
        self.last_failure_time = 0.0
        self.BACKOFF_DURATION = 2.0  # 2 seconds cooldown after failures

        # Initial Control Session Creation
        self.control_session = self._create_control_session()
        
        # [WS] Initialize WebSocket Client immediately if IP known
        if self.camera_ip:
            self._init_ws_client(self.camera_ip)

    def _init_ws_client(self, ip):
        if self.ws_client:
            self.ws_client.close()
        try:
            print(f"[INIT] Starting WebSocket Client to {ip}...")
            self.ws_client = AsyncControlClient(ip)
        except Exception as e:
            print(f"[INIT] WS Start Failed: {e}")

    def _create_control_session(self):
        """
        Factory to create a correctly configured requests.Session.
        Preserves Source IP Binding logic for Dual-NIC setups.
        Now REFRESHES network info to handle IP changes after reconnect.
        """
        session = requests.Session()
        
        # [FIX] Refresh Network Info to get latest IP
        self.net_info = get_network_info()
        self.camera_net_ip = self.net_info["camera_net"]["ip"] if self.net_info["camera_net"] else None
        
        # [FIX] Better Binding Logic for Station Mode (e.g. 10.x.x.x)
        # If camera_net_ip (192.168.4.x) is not found, try to find which interface can reach the current camera_ip
        bind_ip = self.camera_net_ip
        if not bind_ip and self.camera_ip:
            bind_ip = find_reachable_interface(self.camera_ip)

        # Define Retry Strategy (Fast retry for control latency)
        retry_strategy = Retry(
            total=3,                # Retry 3 times
            backoff_factor=0,       # No delay between retries (immediate)
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET"],
            raise_on_status=False
        )

        if bind_ip:
            try:
                # Bind to the specific local Interface IP
                adapter = SourceAddressAdapter(bind_ip, max_retries=retry_strategy)
                session.mount('http://', adapter)
                print(f"[SESSION] Created Control Session bound to {bind_ip}")
            except Exception as e:
                print(f"[SESSION] Failed to bind Source IP {bind_ip}: {e}. Fallback to default.")
                adapter = HTTPAdapter(max_retries=retry_strategy)
                session.mount('http://', adapter)
        else:
            # Default adapter (System Routing)
            print(f"[SESSION] Created Control Session (Default Routing) - Could not find interface for {self.camera_ip}")
            adapter = HTTPAdapter(max_retries=retry_strategy)
            session.mount('http://', adapter)
            
        return session

    def print_network_summary(self):
        print("="*60)
        print("🌐 Network Interface Detection Summary")
        print("-" * 30)
        if self.net_info['camera_net']:
            n = self.net_info['camera_net']
            print(f"📷 CAMERA NET  : {n['name']} | {n['ip']} | {n['mac']}")
        else:
            print("📷 CAMERA NET  : Not Detected (Is WiFi connected to ESP32CAM?)")

        if self.net_info['internet_net']:
            n = self.net_info['internet_net']
            print(f"🌍 INTERNET NET: {n['name']} | {n['ip']} | {n['mac']}")
        else:
            print("🌍 INTERNET NET: Not Detected")

        print("-" * 30)
        print("Other Interfaces:")
        for iface in self.net_info['all_ifaces']:
            if iface != self.net_info['camera_net'] and iface != self.net_info['internet_net']:
                print(f" - {iface['name']}: {iface['ip']}")
        print("="*60)

state = SystemState()
ws_outbox: "SimpleQueue[str]" = SimpleQueue()
browser_controller_state = {"data": None, "timestamp": 0.0}
# ESP12F UDP Port
UDP_DIST_PORT = 4211

# Multiprocessing Queues (initialized in main)
video_cmd_queue = None
video_frame_queue = None
video_log_queue = None

# Xbox 手把設定
AXIS_LEFT_STICK_X = 0
AXIS_LEFT_STICK_Y = 1
BUTTON_A = 0
BUTTON_B = 1
BUTTON_X = 2
BUTTON_Y = 3
BUTTON_LEFT_STICK = 8
JOYSTICK_DEADZONE = 0.15

# PWM Range
PWM_MAX = 255
TURN_FACTOR = 0.5  # Reduce turning sensitivity if needed

class XboxController:
    def __init__(self):
        pygame.init()
        pygame.joystick.init()
        self.joystick = None
        self._connect()

    def _connect(self):
        joystick_count = pygame.joystick.get_count()
        if joystick_count == 0:
            self.joystick = None
            return False
            
        # [FIX] Auto-Scan for the first valid joystick instead of hardcoding ID 0
        for i in range(joystick_count):
            try:
                js = pygame.joystick.Joystick(i)
                js.init()
                print(f"[XBOX] Found Joystick {i}: {js.get_name()}")
                # Optional: Filter by name if needed, e.g., if "Xbox" in js.get_name()
                self.joystick = js
                return True
            except Exception as e:
                print(f"[XBOX] Failed to init Joystick {i}: {e}")
                
        return False

    def ensure_connected(self):
        if self.joystick and self.joystick.get_init():
            return True
        return self._connect()

    def get_input(self):
        if not self.ensure_connected():
            return None
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return "QUIT"
        left_stick_x = self.joystick.get_axis(AXIS_LEFT_STICK_X)
        left_stick_y = self.joystick.get_axis(AXIS_LEFT_STICK_Y)

        if abs(left_stick_x) < JOYSTICK_DEADZONE:
            left_stick_x = 0.0
        if abs(left_stick_y) < JOYSTICK_DEADZONE:
            left_stick_y = 0.0

        button_a_pressed = self.joystick.get_button(BUTTON_A)
        button_b_pressed = self.joystick.get_button(BUTTON_B)
        button_x_pressed = self.joystick.get_button(BUTTON_X)
        button_y_pressed = self.joystick.get_button(BUTTON_Y)
        stick_pressed = self.joystick.get_button(BUTTON_LEFT_STICK)
        hat_x, hat_y = self.joystick.get_hat(0)
        return {
            "left_stick_x": left_stick_x,
            "left_stick_y": left_stick_y,
            "right_stick_x": self.joystick.get_axis(2), # Right Stick X (Usually)
            "right_stick_y": self.joystick.get_axis(3), # Right Stick Y (Usually)
            "trigger_l": self.joystick.get_axis(4) if self.joystick.get_numaxes() > 4 else 0, # Left Trigger (Sometimes Axis 2 on old drivers)
            "trigger_r": self.joystick.get_axis(5) if self.joystick.get_numaxes() > 5 else 0, # Right Trigger
            "button_a": button_a_pressed,
            "button_b": button_b_pressed,
            "button_x": button_x_pressed,
            "button_y": button_y_pressed,
            "stick_pressed": stick_pressed,
            "dpad_x": hat_x,
            "dpad_y": hat_y
        }

def add_log(msg):
    timestamp = time.strftime("%H:%M:%S")
    log_entry = f"[{timestamp}] {msg}"
    state.logs.append(log_entry)
    if len(state.logs) > 50:
        state.logs.pop(0)
    print(log_entry)
    socketio.emit('log', {'data': log_entry})

state.add_log = add_log

def _build_cmd_from_state(controller_state: dict) -> dict:
    # Returns a dict with left/right values instead of a string cmd
    x = controller_state.get("left_stick_x", 0)
    y = controller_state.get("left_stick_y", 0)

    left_pwm, right_pwm = _calculate_differential_drive(x, y)

    return {"left": left_pwm, "right": right_pwm}

def _calculate_differential_drive(x: float, y: float) -> tuple[int, int]:
    """
    Mix X/Y joystick inputs to Differential Drive (Tank Drive) PWM values.
    x: -1.0 (Left) to 1.0 (Right)
    y: -1.0 (Backward) to 1.0 (Forward) (Input from Pygame is usually -1=Up)
    Returns: (left_pwm, right_pwm) range -255 to 255
    """
    
    # 1. Invert Y to match convention (Up = Forward)
    # Pygame: Up is -1, Down is +1
    # We want: Forward is +1, Backward is -1
    y = -y  # [FIX] Re-enabled based on user analysis

    # 2. Cubic Sensitivity Curve (Exponential Control)
    # Allows "Light Push" for slow speed, "Hard Push" for fast.
    # x^3 preserves sign.
    # 0.5^3 = 0.125 (12% speed at 50% stick)
    x = x * x * x
    y = y * y * y

    # Simple Mixing
    # Left = Throttle + Turn
    # Right = Throttle - Turn

    left = y + x
    right = y - x

    # Normalize if exceeding 1.0
    magnitude = max(abs(left), abs(right))
    if magnitude > 1.0:
        left /= magnitude
        right /= magnitude

    left_pwm = int(left * PWM_MAX)
    right_pwm = int(right * PWM_MAX)

    return left_pwm, right_pwm

def _build_cmd_from_state(controller_state: dict) -> dict:
    # Returns a dict with left/right values instead of a string cmd
    x = controller_state.get("left_stick_x", 0)
    y = controller_state.get("left_stick_y", 0)

    left_pwm, right_pwm = _calculate_differential_drive(x, y)

    return {"left": left_pwm, "right": right_pwm}

# === Control Governor ===
last_esp_cmd_time = 0
MIN_CMD_INTERVAL = 0.08

def send_control_command(left: int, right: int):
    """
    Send motor control command to ESP32-S3.
    Endpoint: GET /motor?left=XX&right=YY (HTTP Fallback)
    Endpoint: WS /ws/control (Primary)
    """
    global last_esp_cmd_time, state

    # [1. Server-Side Governor]
    # Protect ESP32 from request floods (Connection Reset)
    now = time.time()
    
    # Always allow STOP or if meaningful change?
    # We allow STOP (0,0) to bypass rate limit for safety
    is_stop = (left == 0 and right == 0)
    
    if not is_stop and (now - last_esp_cmd_time < MIN_CMD_INTERVAL):
         return True # Rate limit active
         
    # [Circuit Breaker]
    if state.consecutive_failures >= 3:
        if now - state.last_failure_time < state.BACKOFF_DURATION:
            if state.consecutive_failures == 3: 
                pass 
            return False

    target_ip = state.camera_ip or "192.168.4.1"
    url = f"http://{target_ip}/motor"
    params = {"left": left, "right": right}
    
    # Update State
    state.last_motor_cmd = (left, right)

    # ⭐ WebSocket First Strategy
    if state.ws_client and state.ws_client.connected:
        if state.ws_client.send(left, right):
            last_esp_cmd_time = time.time()
            return True
        else:
             print("[CONTROL] WS Send Failed, falling back to HTTP")
    
    # HTTP Fallback
    # add_log(f"[CONTROL] (HTTP) → {target_ip}/motor L:{left} R:{right}")

    try:
        last_esp_cmd_time = time.time()
        resp = state.control_session.get(
            url, 
            params=params, 
            timeout=1.0,
            headers={'Content-Type': 'application/json'}
        )
        resp.close()
        
        if resp.status_code == 200:
            if state.consecutive_failures > 0:
                print("[CONTROL] ✅ Connection Recovered")
                state.consecutive_failures = 0
            return True
        else:
            add_log(f"[CONTROL] ⚠️ Failed: HTTP {resp.status_code}")
            state.consecutive_failures += 1
            state.last_failure_time = time.time()
            return False
            
    except requests.exceptions.Timeout:
        state.consecutive_failures += 1
        state.last_failure_time = time.time()
        add_log(f"[CONTROL] ⚠️ Timeout to {target_ip}")
        state.control_session.close()
        state.control_session = state._create_control_session()
        return False
        
    except requests.exceptions.ConnectionError as e:
        state.consecutive_failures += 1
        state.last_failure_time = time.time()
        add_log(f"[CONTROL] ❌ Connection Error to {target_ip}")
        state.control_session.close()
        state.control_session = state._create_control_session()
        return False
        
    except requests.exceptions.RequestException as e:
        state.consecutive_failures += 1
        state.last_failure_time = time.time()
        return False

def video_manager_thread():
    """Manages the video stream status and reads frames from the video process."""
    add_log("Video Manager Thread Started...")

    # 1. Send initial config to video process
    initial_config = build_initial_video_config(state)
    video_cmd_queue.put((CMD_SET_URL, initial_config))

    while state.is_running:
        try:
            while not video_log_queue.empty():
                msg = video_log_queue.get_nowait()
                add_log(msg)
        except:
            pass
        time.sleep(0.5)

    video_cmd_queue.put((CMD_EXIT, None))
    add_log("Video Manager Stopped")

def frame_receiver_thread():
    """Reads JPEG bytes from the video process queue."""
    log_counter = 0
    print("[DEBUG] Frame Receiver Thread Started")
    while state.is_running:
        try:
            frame_bytes = video_frame_queue.get(timeout=0.1)
            with state.frame_lock:
                state.frame_buffer = frame_bytes
                state.stream_connected = True
            
            log_counter += 1
            if log_counter % 50 == 0:
                pass # print(f"[DEBUG] Frame Receiver: Received {log_counter} frames")

        except queue.Empty:
            # print("[DEBUG] Frame Receiver: Queue Empty")
            pass
        except Exception as e:
            print(f"Frame Receive Error: {e}")

def generate_frames():
    """Flask Stream Generator (reads raw JPEG bytes from buffer)"""
    no_signal_frame_bytes = None
    frame_counter = 0
    print("[DEBUG] generate_frames generator started")
    
    while state.is_running:
        frame_bytes = None
        with state.frame_lock:
            if state.frame_buffer is not None:
                frame_bytes = state.frame_buffer
        
        if frame_bytes is None:
            if no_signal_frame_bytes is None:
                no_signal_frame = create_no_signal_frame()
                ret, buffer = cv2.imencode('.jpg', no_signal_frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
                if ret:
                    no_signal_frame_bytes = buffer.tobytes()
            frame_bytes = no_signal_frame_bytes
        
        if frame_bytes:
            frame_counter += 1
            if frame_counter % 50 == 0:
                pass # print(f"[DEBUG] generate_frames yielding frame {frame_counter}")
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
        
        time.sleep(0.03)

def create_no_signal_frame():
    import numpy as np
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    cv2.putText(frame, "NO SIGNAL", (180, 240),
                cv2.FONT_HERSHEY_SIMPLEX, 2, (0, 0, 255), 3)
    cv2.putText(frame, "Check ESP32-S3 Camera", (140, 300),
                cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
    return frame

def udp_sensor_thread():
    """Listens for Sensor Data from ESP12F (or forwarded) on UDP 4211"""
    add_log("UDP Sensor Listener Started (Port 4211)...")
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        # Bind to all interfaces to catch broadcasts or direct packets
        sock.bind(("0.0.0.0", UDP_DIST_PORT))
    except Exception as e:
        add_log(f"[UDP SENSOR] Bind failed: {e}")
        return

    sock.settimeout(1.0)

    while state.is_running:
        try:
            data, addr = sock.recvfrom(1024)
            message = data.decode(errors="ignore").strip()
            # Try to parse float distance
            try:
                dist = float(message)
                state.radar_dist = dist
            except ValueError:
                pass
        except socket.timeout:
            continue
        except Exception as e:
            add_log(f"[UDP SENSOR] Error: {e}")
            time.sleep(1)

def status_push_thread():
    """Background thread to push system status via WebSocket"""
    add_log("Status Push Thread Started...")
    while state.is_running:
        try:
            status_data = {
                "ip": state.current_ip,
                # Map Arm IP to 'car_ip' for UI display (since UI expects car_ip for Control status)
                "car_ip": state.arm_ip or state.car_ip, 
                "camera_ip": state.camera_ip,
                "video_url": state.video_url,
                "dist": state.radar_dist,
                "logs": state.logs[-30:],
                "stream_connected": state.stream_connected,
                "ai_status": state.ai_enabled
            }
            socketio.emit('status_update', status_data)
        except Exception as e:
            print(f"[STATUS] Push error: {e}")

        time.sleep(2)  # Push every 2 seconds

def discovery_listener_thread():
    """Listens for UDP Broadcasts from ESP32 to auto-configure IP"""
    PORTS = [config.CAMERA_DISCOVERY_PORT, config.ARM_DISCOVERY_PORT]
    add_log(f"Discovery Listener Started on Ports {PORTS}...")

    sockets = []

    # 1. Bind to 0.0.0.0 for EACH Port
    for port in PORTS:
        try:
            sock_all = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock_all.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock_all.bind(("0.0.0.0", port))
            sock_all.setblocking(False)
            sockets.append(sock_all)
        except Exception as e:
            add_log(f"[DISCOVERY] Bind 0.0.0.0:{port} failed: {e}")

    # 2. Bind to Internet Net IP to fix Windows Dual-NIC issues
    if state.internet_net_ip:
        for port in PORTS:
            try:
                sock_specific = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                sock_specific.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                sock_specific.bind((state.internet_net_ip, port))
                sock_specific.setblocking(False)
                sockets.append(sock_specific)
                add_log(f"[DISCOVERY] Binding {state.internet_net_ip}:{port}")
            except Exception as e:
                pass

    if not sockets:
        add_log("[DISCOVERY] No sockets created. Discovery disabled.")
        return

    while state.is_running:
        try:
            readable, _, _ = select.select(sockets, [], [], 1.0)

            for s in readable:
                try:
                    data, addr = s.recvfrom(1024)
                    msg = data.decode('utf-8', errors='ignore')
                    
                    # [NEW] Support Simple Beacon from MicroPython
                    if "ESP8266_ARM" in msg:
                        remote_ip = addr[0]
                        if state.arm_ip != remote_ip:
                            print(f"[DISCOVERY] 🦾 Robot Arm Found at {remote_ip} (Beacon)")
                            state.arm_ip = remote_ip
                        continue

                    # Expecting JSON: {"device": "esp32-s3-car", "ip": "192.168.x.x"}
                    if "{" in msg:
                        try:
                            info = json.loads(msg)
                            if "ip" in info:
                                # Check if this is the Camera or Arm
                                # Currently we assume Camera sends 'ip' but Arm also sends 'ip'
                                # Arm distinguishes itself via 'device' key
                                
                                remote_ip = info["ip"]
                                
                                if "device" in info and info["device"] == "esp8266-arm":
                                    # Found the Robot Arm
                                    if state.arm_ip != remote_ip:
                                        print(f"[DISCOVERY] 🦾 Robot Arm Found at {remote_ip}")
                                        state.arm_ip = remote_ip
                                else:
                                    # Assume it's the Camera (Legacy behavior)
                                    if state.camera_ip != remote_ip:
                                        print(f"[DISCOVERY] 🎥 ESP32 Camera Found at {remote_ip}")
                                        state.camera_ip = remote_ip
                                        
                                        # Trigger WebSocket Reconnection
                                        if state.ws_client:
                                            state.ws_client.last_connect_attempt = 0 
                                            
                            # Helper for Telemetry (Optional)
                            # if "dist" in data: ...
                        except json.JSONDecodeError:
                            pass
                except socket.error:
                    pass
        except Exception as e:
            add_log(f"[DISCOVERY] Error: {e}")
            time.sleep(1)

    for s in sockets:
        s.close()

def xbox_controller_thread():
    add_log("Xbox Controller Thread Started...")
    controller = XboxController()
    if not controller.joystick:
        add_log("Xbox Controller not found. Waiting...")

    last_pwm = (0, 0)
    controller_ready = controller.joystick is not None
    using_browser_stream = False
    
    # [Phase 2] Low Pass Filter State
    last_raw_x = 0.0
    last_raw_y = 0.0
    ALPHA = 0.4 # 0.3-0.5 is good. Lower = smoother but more lag.

    while state.is_running:
        try:
            if state.is_flashing:
                time.sleep(0.5)
                continue

            # [Input Priority] If API (Keyboard) was used recently, suppress Joystick
            # (Checks if last WASD command was within 0.5s)
            if time.time() - state.last_api_control_time < 0.5:
                time.sleep(0.1)
                continue

            controller_state = controller.get_input()
            source = "hardware"

            if controller_state == "QUIT":
                state.is_running = False
                break

            if not controller_state:
                recent_browser_input = browser_controller_state["data"]
                if recent_browser_input and time.time() - browser_controller_state["timestamp"] < 1.0:
                    controller_state = recent_browser_input
                    source = "browser"
                    if not using_browser_stream: using_browser_stream = True
                else:
                    using_browser_stream = False
                    if controller_ready: controller_ready = False
                    time.sleep(0.1)
                    continue

            if not controller_ready and source == "hardware":
                controller_ready = True

            # [Phase 2] Apply Low Pass Filter (Smoothing) to Analog Inputs
            # Only apply if source is hardware (keyboard 'virtual' analog doesn't need this)
            if source == "hardware":
                raw_x = controller_state.get("left_stick_x", 0)
                raw_y = controller_state.get("left_stick_y", 0)
                
                # LPF: y = a*new + (1-a)*old
                filtered_x = (raw_x * ALPHA) + (last_raw_x * (1.0 - ALPHA))
                filtered_y = (raw_y * ALPHA) + (last_raw_y * (1.0 - ALPHA))
                
                last_raw_x = filtered_x
                last_raw_y = filtered_y
                
                # Update state with filtered values for calculation
                controller_state["left_stick_x"] = filtered_x
                controller_state["left_stick_y"] = filtered_y

            # Calculate PWM for Chassis (Left Stick)
            pwm_dict = _build_cmd_from_state(controller_state)
            current_pwm = (pwm_dict["left"], pwm_dict["right"])

            # Send Chassis Cmd if changed significantly
            if abs(current_pwm[0] - last_pwm[0]) > 1 or abs(current_pwm[1] - last_pwm[1]) > 1:
                 send_control_command(current_pwm[0], current_pwm[1])
                 last_pwm = current_pwm
            elif current_pwm == (0, 0) and last_pwm != (0, 0):
                 send_control_command(0, 0)
                 last_pwm = (0, 0)

            # === Robot Arm Control (Rate Control) ===
            # Right Stick X -> Base
            # Right Stick Y -> Shoulder
            # D-Pad Y (or Triggers) -> Elbow
            # Button A -> Gripper Toggle
            
            # 1. Get Inputs
            rs_x = controller_state.get("right_stick_x", 0)
            rs_y = controller_state.get("right_stick_y", 0)
            dpad_y = controller_state.get("dpad_y", 0)
            btn_a = controller_state.get("button_a", 0)

            # Deadzone
            if abs(rs_x) < 0.15: rs_x = 0
            if abs(rs_y) < 0.15: rs_y = 0
            
            # Rate of Change (Degrees per loop) -> Loop is ~20Hz (0.05s)
            # Max Speed: 60 deg/sec -> 3 deg/loop
            ARM_SPEED = 2.0 

            # Update Angles
            # Note: In Pygame, Right is +1, Down is +1 usually.
            # Base: Right(+x) -> Increase Angle
            # Shoulder: Up(-y) -> Increase Angle (Lift)
            # Elbow: Dpad Up(+1) -> Increase Angle (Open/Up)
            
            # Initialize static vars for arm state if not exists
            if not hasattr(state, 'arm_angles'):
                state.arm_angles = {'b': 90.0, 's': 90.0, 'e': 90.0, 'g': 50.0}
                state.last_arm_send = 0
                state.gripper_pressed = False

            # Rate Integration
            state.arm_angles['b'] += rs_x * ARM_SPEED
            state.arm_angles['s'] -= rs_y * ARM_SPEED # Invert Y
            state.arm_angles['e'] += dpad_y * ARM_SPEED * 2 # Faster Dpad
            
            # Clamp (0-180)
            state.arm_angles['b'] = max(0, min(180, state.arm_angles['b']))
            state.arm_angles['s'] = max(0, min(180, state.arm_angles['s']))
            state.arm_angles['e'] = max(0, min(180, state.arm_angles['e']))

            # Gripper Toggle (Latch)
            if btn_a and not state.gripper_pressed:
                state.gripper_pressed = True
                state.arm_angles['g'] = 100.0 if state.arm_angles['g'] < 80 else 10.0 # Toggle Open/Close
            elif not btn_a:
                state.gripper_pressed = False

            # Send Packet (Throttled to 10Hz to save bandwidth, or if changed)
            now = time.time()
            if now - state.last_arm_send > 0.1: # 10Hz
                send_robot_packet(0x03, '<ffff', (
                    state.arm_angles['b'], 
                    state.arm_angles['s'], 
                    state.arm_angles['e'], 
                    state.arm_angles['g']
                ))
                state.last_arm_send = now

            # Emit to UI
            try:
                controller_state_with_cmd = dict(controller_state)
                controller_state_with_cmd["cmd"] = f"L:{current_pwm[0]} R:{current_pwm[1]}"
                controller_state_with_cmd["source"] = source
                socketio.emit('controller_data', controller_state_with_cmd)
            except Exception:
                pass

        except Exception as e:
            # Catch generic errors (like Pygame video system not init) and retry
            # print(f"[XBOX] Loop Error: {e}")
            time.sleep(1)

        time.sleep(0.05) # ~20Hz updates
    
    try:
        pygame.quit()

    except:
        pass


    
@app.route('/video_feed')
def video_feed():
    return Response(generate_frames(), 
                   mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/robot_arm_simulator.html')
def robot_simulator():
    """Serve the simulator with cache disabled"""
    response = send_from_directory(BASE_DIR, 'robot_arm_simulator.html')
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response

@app.route('/models/<path:filename>')
def serve_models(filename):
    models_dir = os.path.join(BASE_DIR, 'models')
    return send_from_directory(models_dir, filename)

@app.route('/favicon.ico')
def favicon():
    return '', 204  # No Content

@socketio.on('connect')
def handle_connect():
    add_log('Client connected via WebSocket')

@socketio.on('disconnect')
def handle_disconnect():
    print('Client disconnected')

@socketio.on('browser_controller_state')
def handle_browser_controller_state(data):
    browser_controller_state["data"] = data or {}
    browser_controller_state["timestamp"] = time.time()

@socketio.on('control_command')
def handle_control_command(data):
    """
    Handle motor control commands via WebSocket for lower latency.
    Expected JSON: {"left": int, "right": int}
    """
    try:
        left = data.get('left')
        right = data.get('right')

        if left is None or right is None:
            return

        # [Input Priority] Mark this command as active
        state.last_api_control_time = time.time()

        # Send to ESP32
        # Use existing function (it handles threaded requests)
        send_control_command(int(left), int(right))
        
    except Exception as e:
        print(f"[WS] Control Error: {e}")

@socketio.on('arm_command')
def handle_arm_command(data):
    """
    Handle robot arm commands via WebSocket.
    Expected JSON: {"base": int, "shoulder": int, "elbow": int}
    """
    try:
        base = data.get('base')
        shoulder = data.get('shoulder')
        elbow = data.get('elbow')

        if base is None or shoulder is None or elbow is None:
            return

        # Create Command String: ARM:B90,S45,E90\n
        # Legacy Serial Format
        cmd = f"ARM:B{int(base)},S{int(shoulder)},E{int(elbow)}\n"
        
        # 1. Try UDP First (New Way)
        if state.arm_ip:
            try:
                msg = json.dumps({"base": int(base), "shoulder": int(shoulder), "elbow": int(elbow)})
                sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                sock.sendto(msg.encode(), (state.arm_ip, 4211))
            except Exception as e:
                print(f"[WS] Arm UDP Fail: {e}")

        # 2. Key Serial Fallback (Old Way)
        if state.ser and state.ser.is_open:
            state.ser.write(cmd.encode('utf-8'))
        else:
            pass

    except Exception as e:
        print(f"[WS] Arm Error: {e}")


@app.route('/api/status')
def api_status():
    return jsonify({
        "ip": state.current_ip,
        "car_ip": state.car_ip,
        "camera_ip": state.camera_ip,
        "video_url": state.video_url,
        "dist": state.radar_dist,
        "logs": state.logs[-30:],
        "stream_connected": state.stream_connected,
        "ai_status": state.ai_enabled
    })

@app.route('/api/toggle_ai', methods=['POST'])
def toggle_ai():
    if not YOLO_AVAILABLE:
        return jsonify({"status": "error", "msg": "AI Library Missing"})

    state.ai_enabled = not state.ai_enabled

    # Notify Process
    if video_cmd_queue:
        video_cmd_queue.put((CMD_SET_AI, state.ai_enabled))

    status_str = "ACTIVATED" if state.ai_enabled else "DEACTIVATED"
    add_log(f"AI HUD {status_str}")
    return jsonify({"status": "ok", "ai_enabled": state.ai_enabled})

@app.route('/api/set_model', methods=['POST'])
def set_model():
    """Endpoint to switch AI Model"""
    data = request.json
    model_name = data.get('model')

    if not model_name:
        return jsonify({"status": "error", "msg": "No model name provided"}), 400

    add_log(f"Requesting model switch to: {model_name}")

    # Notify Process
    if video_cmd_queue:
        video_cmd_queue.put((CMD_SET_MODEL, {'model': model_name}))

    return jsonify({"status": "ok", "model": model_name})

@app.route('/api/get_models', methods=['GET'])
def get_models():
    """List available .pt models in the models directory"""
    try:
        models_dir = os.path.join(BASE_DIR, 'models')
        if not os.path.exists(models_dir):
            return jsonify({"models": [], "error": "Models directory not found"})
        
        models = [f for f in os.listdir(models_dir) if f.endswith('.pt')]
        models.sort()  # Sort alphabetically for consistent display
        return jsonify({"models": models})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/netinfo')
def api_netinfo():
    return jsonify(state.net_info)

@app.route('/api/camera_settings', methods=['GET', 'POST'])
def api_camera_settings():
    """
    GET: Fetch current settings from ESP32 /status endpoint
    POST: Update a setting via ESP32 /control endpoint
    """
    target_ip = state.camera_ip or "192.168.4.1"

    if request.method == 'GET':
        try:
            url = f"http://{target_ip}/status"
            resp = state.control_session.get(url, timeout=2)
            if resp.status_code == 200:
                return jsonify(resp.json())
            return jsonify({"error": f"ESP32 returned {resp.status_code}"}), 502
        except requests.exceptions.RequestException as e:
            return jsonify({"error": str(e)}), 503

    elif request.method == 'POST':
        data = request.json
        var = data.get('var')
        val = data.get('val')

        if var is None or val is None:
            return jsonify({"error": "Missing var or val"}), 400

        try:
            # Forward to ESP32 /control?var=X&val=Y
            url = f"http://{target_ip}/control"
            add_log(f"[Control] Sending {var}={val} to {target_ip}")
            resp = state.control_session.get(url, params={'var': var, 'val': val}, timeout=2)
            if resp.status_code == 200:
                add_log(f"[Control] Success: {var}={val}")
                return jsonify({"status": "ok", "var": var, "val": val})
            add_log(f"[Control] Failed: HTTP {resp.status_code}")
            return jsonify({"error": f"ESP32 returned {resp.status_code}"}), 502
        except requests.exceptions.RequestException as e:
            add_log(f"[Control] Exception: {e}")
            return jsonify({"error": str(e)}), 503

@app.route('/api/control', methods=['POST'])
def api_control():
    """
    Handle motor control commands from the frontend.
    Expected JSON: {"left": int, "right": int}
    """
    try:
        # [DEBUG] Print everything about the request
        # print("=" * 60)
        # print("[API] 📥 Received /api/control request")
        # print(f"[API] Raw Data: {request.data}")
       
        data = request.get_json(silent=True)
        if not data:
            # Fallback for some browsers or bad headers
            try:
                data = json.loads(request.data)
            except:
                pass
        
        if not data:
             # Try form data
            if request.form:
                 data = request.form.to_dict()

        if not data:
            print(f"[API] ❌ Failed to parse JSON. Raw: {request.data}")
            return jsonify({"error": "Invalid JSON", "raw": str(request.data)}), 400

        left = data.get('left')
        right = data.get('right')

        # Convert to int if strings
        if left is not None: left = int(left)
        if right is not None: right = int(right)
        
        if left is None or right is None:
            print(f"[API] ❌ Missing params in {data}")
            return jsonify({"error": "Missing left/right", "data": data}), 400
            
        # [Input Priority] Mark this command as active
        state.last_api_control_time = time.time()

        if send_control_command(left, right):
            return jsonify({"status": "ok", "left": left, "right": right})
        else:
            # 503 Service Unavailable is more appropriate for "Device Unreachable" than 500
            return jsonify({"error": "ESP32 Unreachable"}), 503

    except Exception as e:
        print(f"[API] 💥 Exception: {e}")
        return jsonify({"error": str(e)}), 500

# === Robot Arm UDP Logic (v2.0) ===
def send_robot_packet(cmd_id, payload_fmt, args):
    """
    Constructs and sends a v2.0 Binary Packet.
    """
    try:
        # 1. Construct Payload
        # Support 3 floats (B,S,E) or 4 floats (B,S,E,G)
        payload = struct.pack(payload_fmt, *args)
        
        # 2. Construct Body
        header = b'RM'
        body = header + struct.pack('B', cmd_id) + payload
        
        # 3. CRC Calculation
        crc = 0xFFFF
        for byte in body:
            crc ^= byte << 8
            for _ in range(8):
                if crc & 0x8000:
                    crc = (crc << 1) ^ 0x1021
                else:
                    crc <<= 1
                crc &= 0xFFFF
        
        # 4. Final Packet
        packet = body + struct.pack('<H', crc)
        
        # 5. Send
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        target_ip = state.arm_ip if hasattr(state, 'arm_ip') and state.arm_ip else None
        
        # [Broadcast Fallback]
        # Since we don't have robust discovery yet, always broadcast OR use specific IP
        # If user knows IP, they should set it or we detect it.
        # For now, let's try strict IP first, then fallback to broadcast if configured?
        # Actually, broadcast is safer for immediate 'it just works' experience in private net.
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.sendto(packet, ('<broadcast>', UDP_DIST_PORT))
        # if target_ip:
        #     sock.sendto(packet, (target_ip, UDP_DIST_PORT))
        
        return True
    except Exception as e:
        print(f"[ARM] Send Error: {e}")
        return False

@app.route('/api/arm', methods=['POST'])
def handle_arm_command_api():
    """
    Handle Robot Arm Commands (v2.0 Protocol).
    Input: JSON {"base": 90, "shoulder": 45, "elbow": 90, "gripper": 50}
    """
    try:
        data = request.json
        if not data:
            return jsonify({"status": "error", "message": "No JSON"}), 400
            
        base = float(data.get('base', 90))
        shoulder = float(data.get('shoulder', 90))
        elbow = float(data.get('elbow', 90))
        gripper = float(data.get('gripper', 50)) # Default 50 (Half)
        
        # Send 4 Floats (Base, Shoulder, Elbow, Gripper)
        # We use strict '<ffff' format for 4 arguments
        # FW must be updated to accept 16 bytes payload
        if send_robot_packet(0x03, '<ffff', (base, shoulder, elbow, gripper)):
             return jsonify({"status": "ok", "proto": "v2.0"})
        else:
             return jsonify({"status": "error", "message": "Send Failed"}), 500
        
    except Exception as e:
        add_log(f"[ARM] Error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/robot_arm_control', methods=['POST'])
def api_robot_arm_control():
    """Legacy Serial API (Optional)"""
    return jsonify({"error": "Deprecated, use /api/arm"}), 410

# [NEW] WebSocket Control Handler for Arm
@socketio.on('arm_command')
def handle_arm_command_ws(json_data):
    """
    Handle Robot Arm commands via WebSocket.
    Expected: {"base": float, "shoulder": float, "elbow": float, "gripper": float}
    """
    try:
        base = float(json_data.get('base', 0))
        shoulder = float(json_data.get('shoulder', 90))
        elbow = float(json_data.get('elbow', 90))
        gripper = float(json_data.get('gripper', 50))
        
        state.last_api_control_time = time.time()
        
        send_robot_packet(0x03, '<ffff', (base, shoulder, elbow, gripper))
        
    except Exception as e:
        print(f"[WS] 💥 Error in arm_command: {e}")

# [NEW] WebSocket Control Handler (Legacy Chassis)
@socketio.on('control_command')
def handle_control_command(json_data):
    """
    Handle control commands via WebSocket (Lower latency than HTTP).
    Expected JSON: {"left": int, "right": int}
    """
    try:
        left = int(json_data.get('left', 0))
        right = int(json_data.get('right', 0))
        
        state.last_api_control_time = time.time()
        send_control_command(left, right)
        
    except Exception as e:
        print(f"[WS] 💥 Error in control_command: {e}")

@app.route('/')
def index():
    # Force cache bust for JS files
    ver = int(time.time()) 
    return render_template('index.html', version=ver)

if __name__ == '__main__':
    # Add Retry Adapter
    retry_strategy = Retry(
        total=3,
        backoff_factor=0.1,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["HEAD", "GET", "OPTIONS"]
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    state.control_session.mount("http://", adapter)
    
    print("[SYSTEM] Starting PC Client Server...")
    print(f"[SYSTEM] Please open: http://localhost:{config.WEB_PORT}")

    # Initialize Multiprocessing Queues
    video_cmd_queue = Queue()
    video_frame_queue = Queue(maxsize=3) # Limit buffer to reduce latency
    video_log_queue = Queue()

    # Start Video Process (Optional - skip if camera unavailable)
    video_process_enabled = os.getenv('DISABLE_VIDEO') != '1'
    p = None
    
    if video_process_enabled:
        try:
            print("[INIT] Starting video process...")
            initial_config = build_initial_video_config(state)
            p = Process(target=video_process_target, args=(video_cmd_queue, video_frame_queue, video_log_queue, initial_config))
            p.daemon = True
            p.start()
            print("[INIT] ✅ Video process started")
        except Exception as e:
            print(f"[INIT] ⚠️ Video process failed to start: {e}")
            print("[INIT] Continuing without video stream...")
            p = None
    else:
        print("[INIT] Video process disabled (DISABLE_VIDEO=1)")

    # Threads
    threading.Thread(target=udp_sensor_thread, daemon=True).start()
    threading.Thread(target=xbox_controller_thread, daemon=True).start()
    
    
    # Only start video threads if video process is running
    if p:
        threading.Thread(target=video_manager_thread, daemon=True).start()
        threading.Thread(target=frame_receiver_thread, daemon=True).start()
    
    # ⭐ Start Motion Control Thread (REVERTED - Moved to Firmware)
    # threading.Thread(target=motion_control_thread, daemon=True).start()
    
    threading.Thread(target=status_push_thread, daemon=True).start()
    threading.Thread(target=discovery_listener_thread, daemon=True).start()

    print("=" * 60)
    print(f"🚀 Web Server: http://127.0.0.1:{config.WEB_PORT}")
    print(f"📦 YOLO: {YOLO_AVAILABLE}")
    print(f"🎮 Xbox: {'ACTIVE' if pygame.joystick.get_count() > 0 else 'NOT FOUND'}")
    state.print_network_summary()
    if state.video_url:
        print(f"🎥 Stream URL: {state.video_url}")
    print("=" * 60)

    try:
        # [FIX] Disable debug mode to prevent WinError 10038 socket errors
        # The reloader causes socket issues when combined with multiprocessing
        # For development, manual restart is acceptable
        socketio.run(
            app, 
            host=config.WEB_HOST, 
            port=config.WEB_PORT, 
            debug=False,  # Disabled to prevent socket errors
            use_reloader=False,  # Prevent file watching socket issues
            allow_unsafe_werkzeug=True
        )
    except KeyboardInterrupt:
        print("\n[INIT] 🛑 Shutting down gracefully...")
        state.is_running = False
        if p and video_cmd_queue:
            video_cmd_queue.put((CMD_EXIT, None))
            p.join(timeout=3)
        print("[INIT] ✅ Shutdown complete")
    except OSError as e:
        # Catch socket errors gracefully
        print(f"\n[INIT] ⚠️ Socket error during shutdown: {e}")
        print("[INIT] This is usually harmless. Server stopped.")
        state.is_running = False
        if p and video_cmd_queue:
            video_cmd_queue.put((CMD_EXIT, None))