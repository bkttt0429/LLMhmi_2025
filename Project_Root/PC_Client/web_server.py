import sys
import os
import cv2
import time
import threading
import re
import socket
import math
import multiprocessing
from pathlib import Path
import queue
import requests
import serial
import pygame
import websocket
from queue import SimpleQueue, Empty
from serial.tools import list_ports
from flask import Flask, render_template, Response, request, jsonify
from flask_socketio import SocketIO, emit

# 路徑設定
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.append(BASE_DIR)
import config
from network_manager import NetworkManager
from video_process import video_process_target

# 導入 Serial Worker 和燒錄函數
from serial_worker import serial_worker, prepare_sketch, compile_and_upload

# AI is now in video_process.py, checking only for capability
try:
    from ai_detector import YOLO_AVAILABLE
except ImportError:
    YOLO_AVAILABLE = False

# 初始化 Flask 和 SocketIO
template_dir = os.path.join(BASE_DIR, 'templates')
app = Flask(__name__, template_folder=template_dir, static_folder=template_dir)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

BRIDGE_CACHE_FILE = Path(BASE_DIR) / ".last_bridge_host"

# === 全域狀態 ===
class SystemState:
    def __init__(self):
        self.nm = NetworkManager()
        self.net_config = self.nm.detect_interfaces()

        self.car_ip = getattr(config, "DEFAULT_CAR_IP", "boebot.local")
        self.current_ip = self.car_ip # Keeps legacy naming but really means car target IP in some contexts

        # Camera Net Logic
        if self.net_config.camera_net:
            # If camera net is detected (192.168.4.x), we expect camera at .1
            self.camera_ip = "192.168.4.1"
        else:
            # Fallback if config is empty
            cfg_ip = getattr(config, "DEFAULT_STREAM_IP", "")
            self.camera_ip = cfg_ip if cfg_ip else "192.168.4.1"

        self.bridge_ip = self.camera_ip # Simplified logic for now
        self.video_url = f"http://{self.camera_ip}:81/stream"

        self.serial_port = None
        self.preferred_port = None
        self.ser = None
        self.ws_connected = False
        self.radar_dist = 0.0
        self.logs = []
        self.is_running = True

        # Process & Queue
        self.frame_queue = multiprocessing.Queue(maxsize=2)
        self.result_queue = multiprocessing.Queue(maxsize=10)
        self.control_queue = multiprocessing.Queue(maxsize=5)
        self.process_stop_event = multiprocessing.Event()
        self.ai_enabled_flag = multiprocessing.Value('b', False) # Shared boolean
        self.video_process = None

        self.is_flashing = False
        self.flash_lock = threading.Lock()
        self.add_log = None
        
        self.stream_connected = False # Tracking simplified

state = SystemState()
ws_outbox: "SimpleQueue[str]" = SimpleQueue()
browser_controller_state = {"data": None, "timestamp": 0.0}
UDP_PORT = 4210
CAMERA_DISCOVERY_PORT = getattr(config, "CAMERA_DISCOVERY_PORT", 4211)
udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
udp_sock.settimeout(0.3)

# Xbox 手把設定
AXIS_LEFT_STICK_X = 0
AXIS_LEFT_STICK_Y = 1
BUTTON_A = 0
BUTTON_B = 1
BUTTON_X = 2
BUTTON_Y = 3
BUTTON_LEFT_STICK = 8
JOYSTICK_DEADZONE = 0.15
PWM_CENTER = 1500
PWM_RANGE = 200

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
        self.joystick = pygame.joystick.Joystick(0)
        self.joystick.init()
        return True

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
            "left_stick_y": -left_stick_y,
            "button_a": button_a_pressed,
            "button_b": button_b_pressed,
            "button_x": button_x_pressed,
            "button_y": button_y_pressed,
            "stick_pressed": stick_pressed,
            "dpad_x": hat_x,
            "dpad_y": hat_y
        }

# === 輔助函式 ===
def add_log(msg):
    timestamp = time.strftime("%H:%M:%S")
    log_entry = f"[{timestamp}] {msg}"
    state.logs.append(log_entry)
    if len(state.logs) > 50:
        state.logs.pop(0)
    print(log_entry)
    socketio.emit('log', {'data': log_entry})

state.add_log = add_log

def _mix_pwm_from_sticks(x: float, y: float) -> tuple[int, int]:
    """將搖桿輸入轉換為左右輪 PWM 值"""
    throttle = y  # 前後
    turn = x      # 左右

    left = max(min(throttle + turn, 1.0), -1.0)
    right = max(min(throttle - turn, 1.0), -1.0)

    left_pwm = int(PWM_CENTER + left * PWM_RANGE)
    right_pwm = int(PWM_CENTER - right * PWM_RANGE)  # 右輪方向相反
    return left_pwm, right_pwm


def _build_cmd_from_state(controller_state: dict) -> str:
    """
    線性搖桿速度控制，直接輸出 PWM 值
    """
    if controller_state.get("stick_pressed") or controller_state.get("button_x"):
        return "S"

    x = controller_state.get("left_stick_x", 0)
    y = controller_state.get("left_stick_y", 0)

    magnitude = math.sqrt(x**2 + y**2)
    if magnitude < 0.05:
        return "S"

    left_pwm, right_pwm = _mix_pwm_from_sticks(x, y)
    return f"v{left_pwm}:{right_pwm}"

def _build_ws_url(host: str | None = None):
    host = host or state.bridge_ip or state.camera_ip or state.current_ip
    if not host:
        return None
    return f"ws://{host}:82/ws"

def _is_host_resolvable(host: str) -> bool:
    if not host:
        return False
    try:
        socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
        return True
    except socket.gaierror:
        return False


def _is_valid_ip(host: str) -> bool:
    if not host:
        return False
    if host.endswith('.local'):
        return False
    pattern = r'^(?:\d{1,3}\.){3}\d{1,3}$'
    if not re.match(pattern, host):
        return False
    parts = host.split('.')
    return all(0 <= int(p) <= 255 for p in parts)

def websocket_bridge_thread():
    add_log("WebSocket Bridge Thread Started...")
    while state.is_running:
        host = state.car_ip
        if not host:
             time.sleep(2)
             continue

        url = _build_ws_url(host)
        if not url:
            time.sleep(1)
            continue

        try:
             # Very simplified for now since we focus on other things
             time.sleep(1)
        except Exception:
             pass

def send_udp_command(cmd: str):
    if not cmd:
        return False
    target_ip = state.car_ip
    if not target_ip:
        return False
    try:
        udp_sock.sendto(cmd.encode(), (target_ip, UDP_PORT))
        return True
    except OSError:
        return False

def send_serial_command(cmd, source="HTTP"):
    if not cmd:
        return False, "Empty command"

    # 方法0: UDP 直連
    if send_udp_command(cmd):
        return True, "Sent via UDP"

    # 方法2: HTTP (JSON Protocol Preference)
    target_urls = []
    if state.car_ip:
        target_urls.append(f"http://{state.car_ip}/command") # New JSON endpoint
        target_urls.append(f"http://{state.car_ip}/cmd")     # Old endpoint

    for url in target_urls:
        try:
            # Try JSON first if it's the /command endpoint
            if "/command" in url:
                try:
                    resp = requests.post(url, json={"cmd": cmd}, timeout=0.5)
                    if resp.ok: return True, "Sent via HTTP JSON"
                except:
                    pass
            
            # Fallback to GET for /cmd
            if "/cmd" in url:
                resp = requests.get(f"{url}?act={cmd}", timeout=0.5)
                if resp.ok: return True, "Sent via HTTP GET"
        except requests.exceptions.RequestException:
            continue

    return False, "Car unreachable"

def generate_frames():
    """Flask 串流產生器（從 multiprocessing.Queue 讀取）"""
    no_signal_frame = None
    
    while state.is_running:
        try:
            frame = state.frame_queue.get(timeout=0.2)
        except Empty:
            frame = None
        
        # 如果沒有影像，顯示 NO SIGNAL
        if frame is None:
            if no_signal_frame is None:
                no_signal_frame = create_no_signal_frame()
            frame = no_signal_frame
        
        # 編碼並發送
        try:
            ret, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
            if ret:
                frame_bytes = buffer.tobytes()
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
        except Exception as e:
            pass
        
        # No sleep needed here as queue.get blocks or times out

def create_no_signal_frame():
    """建立 NO SIGNAL 畫面"""
    import numpy as np
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    cv2.putText(frame, "NO SIGNAL", (180, 240),
                cv2.FONT_HERSHEY_SIMPLEX, 2, (0, 0, 255), 3)
    cv2.putText(frame, "Check ESP32-S3 Camera", (140, 300),
                cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
    return frame

def ai_result_handler_thread():
    """Thread in Flask process to handle AI results from Video Process"""
    add_log("AI Result Handler Started")
    while state.is_running:
        try:
            result = state.result_queue.get(timeout=0.5)
            if result.get("type") == "command":
                cmd = result.get("cmd")
                if cmd:
                    add_log(f"[AI] Auto-Command: {cmd}")
                    send_serial_command(cmd, source="AI")
        except Empty:
            continue
        except Exception as e:
            print(f"AI Result Handler Error: {e}")

# === Serial Worker Thread ===
def serial_worker_thread():
    # Simplified placeholder to keep existing structure valid
    add_log("Serial Worker Started...")
    while state.is_running:
        time.sleep(1)

# === Xbox Controller Thread ===
def xbox_controller_thread():
    add_log("Xbox Controller Thread Started...")
    controller = XboxController()
    last_cmd = None

    while state.is_running:
        controller_state = controller.get_input()

        if controller_state == "QUIT":
            state.is_running = False
            break

        if not controller_state:
            recent_browser_input = browser_controller_state["data"]
            if recent_browser_input and time.time() - browser_controller_state["timestamp"] < 1.0:
                controller_state = recent_browser_input
            else:
                time.sleep(0.1)
                continue

        cmd = _build_cmd_from_state(controller_state)

        if cmd != last_cmd:
            send_serial_command(cmd, source="Xbox")
            last_cmd = cmd

        controller_state_with_cmd = dict(controller_state)
        controller_state_with_cmd["cmd"] = cmd
        socketio.emit('controller_data', controller_state_with_cmd)
        time.sleep(0.02)
        
    pygame.quit()

# === Flask 路由 ===
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/video_feed')
def video_feed():
    return Response(generate_frames(), 
                   mimetype='multipart/x-mixed-replace; boundary=frame')

@socketio.on('command')
def handle_command(data):
    cmd = data.get('cmd')
    send_serial_command(cmd, source="WebSocket")

@socketio.on('browser_controller_state')
def handle_browser_controller_state(data):
    browser_controller_state["data"] = data or {}
    browser_controller_state["timestamp"] = time.time()

@app.route('/api/status')
def api_status():
    return jsonify({
        "ip": state.current_ip,
        "car_ip": state.car_ip,
        "camera_ip": state.camera_ip,
        "video_url": state.video_url,
        "logs": state.logs[-30:],
        "ai_status": bool(state.ai_enabled_flag.value)
    })

@app.route('/api/control', methods=['POST'])
def api_control():
    data = request.get_json(silent=True) or {}
    cmd = (data.get('cmd') or '').strip()
    if not cmd:
        return jsonify({"status": "error", "msg": "Missing command"}), 400
    success, msg = send_serial_command(cmd, source="API")
    status = "ok" if success else "error"
    code = 200 if success else 500
    return jsonify({"status": status, "msg": msg, "cmd": cmd}), code

@app.route('/api/toggle_ai', methods=['POST'])
def toggle_ai():
    if not YOLO_AVAILABLE:
        return jsonify({"status": "error", "msg": "AI Library Missing"})
    
    current = bool(state.ai_enabled_flag.value)
    state.ai_enabled_flag.value = not current
    
    status_str = "ACTIVATED" if state.ai_enabled_flag.value else "DEACTIVATED"
    add_log(f"AI HUD {status_str}")
    return jsonify({"status": "ok", "ai_enabled": bool(state.ai_enabled_flag.value)})

@app.route('/api/set_ip', methods=['POST'])
def api_set_ip():
    data = request.get_json(silent=True) or {}
    
    car_ip = data.get('car_ip')
    cam_ip = data.get('cam_ip')
    
    if car_ip:
        state.car_ip = car_ip
        state.current_ip = car_ip
        add_log(f"🚗 Car IP Set: {car_ip}")
    
    if cam_ip:
        state.camera_ip = cam_ip
        # Update Video Process via Queue
        state.control_queue.put({"type": "set_ip", "ip": cam_ip})
        add_log(f"📹 Camera IP Set: {cam_ip}")
    
    return jsonify({"status": "ok", "car_ip": car_ip, "cam_ip": cam_ip})

@app.route('/netinfo', methods=['GET'])
def api_netinfo():
    """
    Returns detected network information for debugging.
    """
    return jsonify(state.nm.config.to_dict())

if __name__ == '__main__':
    # Start Video Process
    state.video_process = multiprocessing.Process(
        target=video_process_target,
        args=(state.frame_queue, state.result_queue, state.control_queue,
              state.process_stop_event, state.camera_ip, state.ai_enabled_flag)
    )
    state.video_process.start()

    # Start Helper Threads
    threading.Thread(target=ai_result_handler_thread, daemon=True).start()
    threading.Thread(target=serial_worker_thread, daemon=True).start()
    threading.Thread(target=xbox_controller_thread, daemon=True).start()
    threading.Thread(target=websocket_bridge_thread, daemon=True).start()

    print("=" * 60)
    print(f"🚀 Web Server: http://127.0.0.1:{config.WEB_PORT}")
    print(f"📦 YOLO: {YOLO_AVAILABLE}")
    print(f"🌐 Network Detection: Completed")
    if state.net_config.camera_net:
        print(f"   - Camera Net: {state.net_config.camera_net['name']} ({state.net_config.camera_net['ip']})")
    else:
        print(f"   - Camera Net: Not Found (Defaulting to {state.camera_ip})")

    if state.net_config.internet_net:
        print(f"   - Internet Net: {state.net_config.internet_net['name']} ({state.net_config.internet_net['ip']})")
    print("=" * 60)

    try:
        socketio.run(app, host=config.WEB_HOST, port=config.WEB_PORT, debug=False, use_reloader=False, allow_unsafe_werkzeug=True)
    finally:
        print("Stopping Video Process...")
        state.process_stop_event.set()
        state.video_process.join()
