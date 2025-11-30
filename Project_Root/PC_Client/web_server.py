import sys
import os
import cv2
import time
import threading
import re
import socket
import math
from pathlib import Path
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

# 導入 Serial Worker 和燒錄函數
from serial_worker import serial_worker, prepare_sketch, compile_and_upload

# 導入 AI 模組
from ai_detector import ObjectDetector, YOLO_AVAILABLE

# 初始化 Flask 和 SocketIO
template_dir = os.path.join(BASE_DIR, 'templates')
app = Flask(__name__, template_folder=template_dir, static_folder=template_dir)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

BRIDGE_CACHE_FILE = Path(BASE_DIR) / ".last_bridge_host"


def _unique_hosts(hosts):
    seen = set()
    ordered = []
    for host in hosts:
        if host and host not in seen:
            ordered.append(host)
            seen.add(host)
    return ordered


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

# === 全域狀態 ===
class SystemState:
    def __init__(self):
        cached_bridge = _load_cached_bridge_host()
        default_stream_hosts = getattr(config, "DEFAULT_STREAM_HOSTS", [])
        default_stream_ip = getattr(config, "DEFAULT_STREAM_IP", "")

        self.car_ip = getattr(config, "DEFAULT_CAR_IP", "boebot.local")
        self.current_ip = self.car_ip
        self.bridge_ip = cached_bridge or default_stream_ip or getattr(config, "DEFAULT_CAR_IP", "")

        self.stream_hosts = _unique_hosts([
            cached_bridge,
            default_stream_ip,
            *default_stream_hosts,
            self.bridge_ip,
        ])

        self.camera_ip = self.stream_hosts[0] if self.stream_hosts else ""
        self.serial_port = None
        self.preferred_port = None
        self.ser = None
        self.ws_connected = False

        # 初始化影像串流 URL（修復）
        self.video_url = _build_stream_url(self.camera_ip)

        self.radar_dist = 0.0
        self.logs = []
        self.is_running = True
        self.ai_enabled = False
        self.detector = None
        self.is_flashing = False
        self.flash_lock = threading.Lock()
        self.add_log = None
        
        # 影像串流相關
        self.frame_buffer = None
        self.frame_lock = threading.Lock()
        self.stream_connected = False

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


def _get_stream_candidates():
    defaults = getattr(config, "DEFAULT_STREAM_HOSTS", [])
    default_stream_ip = getattr(config, "DEFAULT_STREAM_IP", "")

    hosts = _unique_hosts([
        state.camera_ip,
        state.bridge_ip,
        default_stream_ip,
        *defaults,
        *getattr(state, "stream_hosts", []),
    ])
    return [(host, _build_stream_url(host)) for host in hosts if host]


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
    last_unresolved_log = 0.0
    default_host = getattr(config, "DEFAULT_CAR_IP", "boebot.local")
    while state.is_running:
        candidates = [state.bridge_ip, state.camera_ip, state.current_ip]
        host = next((h for h in candidates if h), None)
        url = _build_ws_url(host)
        if not host or not url:
            state.ws_connected = False
            time.sleep(0.5)
            continue

        if not _is_host_resolvable(host):
            alternative = next((h for h in candidates if h and h != host and _is_host_resolvable(h)), None)
            if alternative:
                host = alternative
                url = _build_ws_url(host)
            
        if not _is_host_resolvable(host):
            now = time.time()
            if host == default_host:
                if now - last_unresolved_log > 5:
                    add_log(f"[WS] Waiting for reachable host (current: {host})")
                    last_unresolved_log = now
            else:
                if now - last_unresolved_log > 5:
                    add_log(f"[WS] Host unresolved: {host}")
                    last_unresolved_log = now
            time.sleep(0.5)
            continue

        ws = None
        try:
            ws = websocket.create_connection(url, timeout=3)
            state.ws_connected = True
            add_log(f"🔗 WebSocket connected: {url}")
            _persist_bridge_host(host)

            while state.is_running and state.ws_connected:
                try:
                    cmd = ws_outbox.get(timeout=0.25)
                except Empty:
                    continue
                try:
                    ws.send(cmd)
                except Exception as send_err:
                    add_log(f"[WS] Send error: {send_err}")
                    break

        except Exception as e:
            state.ws_connected = False
            time.sleep(0.5)
        finally:
            if ws:
                try:
                    ws.close()
                except Exception:
                    pass
            state.ws_connected = False

def send_udp_command(cmd: str):
    if not cmd:
        return False
    target_ip = state.car_ip or state.current_ip
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

    # 方法1: WebSocket
    ws_url = _build_ws_url()
    if ws_url and state.ws_connected:
        ws_outbox.put(cmd)
        return True, "Sent via WebSocket"

    # 方法2: HTTP
    target_urls = []
    if state.car_ip:
        target_urls.append(f"http://{state.car_ip}/cmd")
    if state.current_ip and state.current_ip != state.car_ip:
        target_urls.append(f"http://{state.current_ip}/cmd")
    default_car_ip = getattr(config, "DEFAULT_CAR_IP", "")
    if default_car_ip and f"http://{default_car_ip}/cmd" not in target_urls:
        target_urls.append(f"http://{default_car_ip}/cmd")

    for url in target_urls:
        try:
            resp = requests.get(f"{url}?act={cmd}", timeout=0.8)
            if resp.ok:
                return True, "Sent via WiFi"
        except requests.exceptions.RequestException:
            continue

    # 方法3: Serial
    if state.ser and state.ser.is_open:
        try:
            state.ser.write(cmd.encode())
            return True, "Sent via Serial (fallback)"
        except Exception:
            pass

    if not hasattr(send_serial_command, '_last_fail_time') or \
       time.time() - send_serial_command._last_fail_time > 5:
        send_serial_command._last_fail_time = time.time()

    return False, "Car unreachable"

# === 影像串流執行緒（修復版）===
def video_stream_thread():
    """專門負責從 ESP32 拉取影像的執行緒"""
    add_log("Video Stream Thread Started...")
    cap = None
    retry_count = 0
    max_retries = 3
    last_success_time = 0
    candidate_index = 0

    while state.is_running:
        candidates = _get_stream_candidates()
        if not state.video_url and candidates:
            for idx, (host, url) in enumerate(candidates):
                if not _is_host_resolvable(host):
                    continue
                candidate_index = idx
                state.camera_ip, state.video_url = host, url
                add_log(f"[VIDEO] Priming stream target {state.video_url}")
                break

        # 檢查是否有可用的串流 URL
        if not state.video_url:
            time.sleep(1)
            continue

        # 嘗試連接串流
        if cap is None or not cap.isOpened():
            if retry_count >= max_retries:
                add_log(f"[VIDEO] Max retries reached for {state.video_url}, rotating host...")
                if candidates:
                    tried = 0
                    while tried < len(candidates):
                        candidate_index = (candidate_index + 1) % len(candidates)
                        next_host, next_url = candidates[candidate_index]
                        tried += 1
                        if not _is_host_resolvable(next_host):
                            continue
                        state.camera_ip = next_host
                        state.video_url = next_url
                        add_log(f"[VIDEO] Switching to {state.video_url}")
                        break
                time.sleep(2)
                retry_count = 0
                continue

            add_log(f"[VIDEO] Connecting to {state.video_url} (attempt {retry_count + 1})")
            try:
                cap = cv2.VideoCapture(state.video_url)
                cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)  # 減少緩衝延遲
                cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc('M', 'J', 'P', 'G'))
                
                if cap.isOpened():
                    add_log("[VIDEO] Stream connected!")
                    state.stream_connected = True
                    retry_count = 0
                    host_from_url = state.video_url.split("//")[-1].split("/")[0].split(":")[0]
                    if host_from_url:
                        state.camera_ip = host_from_url
                else:
                    add_log("[VIDEO] Failed to open stream")
                    cap = None
                    retry_count += 1
                    time.sleep(2)
                    continue
            except Exception as e:
                add_log(f"[VIDEO] Connection error: {e}")
                cap = None
                retry_count += 1
                time.sleep(2)
                continue
        
        # 讀取影像
        try:
            success, frame = cap.read()
            if success:
                last_success_time = time.time()
                retry_count = 0
                
                # AI 處理
                if state.ai_enabled and state.detector and state.detector.enabled:
                    try:
                        result = state.detector.detect(frame)
                        if isinstance(result, tuple) and len(result) == 3:
                            frame, detections, control_cmd = result
                    except Exception as e:
                        add_log(f"[AI] Processing error: {e}")
                
                # 儲存到緩衝區
                with state.frame_lock:
                    state.frame_buffer = frame.copy()
                
            else:
                # 檢查是否超過 3 秒沒有成功讀取
                if time.time() - last_success_time > 3:
                    add_log("[VIDEO] Stream timeout, reconnecting...")
                    cap.release()
                    cap = None
                    state.stream_connected = False
                    retry_count += 1
                time.sleep(0.1)
                
        except Exception as e:
            add_log(f"[VIDEO] Read error: {e}")
            if cap:
                cap.release()
            cap = None
            state.stream_connected = False
            retry_count += 1
            time.sleep(1)
    
    if cap:
        cap.release()
    add_log("Video Stream Thread Stopped")

def generate_frames():
    """Flask 串流產生器（從緩衝區讀取）"""
    no_signal_frame = None
    last_frame_time = 0
    
    while state.is_running:
        # 從緩衝區取得最新影像
        with state.frame_lock:
            if state.frame_buffer is not None:
                frame = state.frame_buffer.copy()
                last_frame_time = time.time()
            else:
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
            print(f"[VIDEO] Encode error: {e}")
        
        time.sleep(0.03)  # ~30 FPS

def create_no_signal_frame():
    """建立 NO SIGNAL 畫面"""
    import numpy as np
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    cv2.putText(frame, "NO SIGNAL", (180, 240),
                cv2.FONT_HERSHEY_SIMPLEX, 2, (0, 0, 255), 3)
    cv2.putText(frame, "Check ESP32-S3 Camera", (140, 300),
                cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
    return frame


def udp_discovery_thread():
    add_log("UDP Discovery Thread Started...")
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        sock.bind(("", CAMERA_DISCOVERY_PORT))
    except Exception as e:
        add_log(f"[UDP DISCOVERY] Bind failed: {e}")
        return

    sock.settimeout(1.0)

    while state.is_running:
        try:
            data, addr = sock.recvfrom(1024)
        except socket.timeout:
            continue
        except Exception as e:
            add_log(f"[UDP DISCOVERY] Error: {e}")
            time.sleep(1)
            continue

        message = data.decode(errors="ignore")
        ip_match = re.search(r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}', message)
        if not ip_match:
            continue

        ip = ip_match.group()
        if not _is_valid_ip(ip):
            continue

        stream_url = None
        stream_match = re.search(r'STREAM:([^;\s]+)', message)
        if stream_match:
            stream_url = stream_match.group(1).strip()

        _apply_camera_ip(ip, stream_url, "[UDP] ")


# === Serial Worker Thread ===
def serial_worker_thread():
    add_log("Serial Worker Started...")
    while state.is_running:
        if state.is_flashing:
            time.sleep(0.5)
            continue
            
        if state.ser is None or not state.ser.is_open:
            ports = list_ports.comports()
            target = None

            if state.preferred_port:
                for p in ports:
                    if p.device == state.preferred_port:
                        target = p.device
                        break
                        
            if not target:
                for p in ports:
                    if "USB" in p.description or "COM" in p.device or "ttyUSB" in p.device or "ttyACM" in p.device:
                        target = p.device
                        break
                        
            if target:
                try:
                    state.ser = serial.Serial(target, config.BAUD_RATE, timeout=0.1)
                    state.serial_port = target
                    add_log(f"Connected to {target}")
                    time.sleep(2)
                except Exception as e:
                    time.sleep(2)
            else:
                time.sleep(1)
                continue
                
        if not state.is_flashing:
            try:
                if state.ser and state.ser.in_waiting:
                    line = state.ser.readline().decode(errors='ignore').strip()
                    if not line:
                        continue

                    # 解析 IP
                    ip_match = re.search(r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}', line)
                    if ip_match and _is_valid_ip(ip_match.group()):
                        ip = ip_match.group()
                        if state.camera_ip != ip:
                            state.camera_ip = ip
                            state.video_url = f"http://{ip}:{config.DEFAULT_STREAM_PORT}/stream"
                            add_log(f"📹 Camera IP detected: {ip}")
                            add_log(f"🎥 Stream URL: {state.video_url}")

                        if not state.bridge_ip or state.bridge_ip.endswith('.local') or state.bridge_ip != ip:
                            state.bridge_ip = ip
                            _persist_bridge_host(ip)
                            add_log(f"🔄 Bridge host updated to {ip}")

                    # 解析距離
                    if "DIST:" in line:
                        try:
                            parts = line.split(":")
                            state.radar_dist = float(parts[1].strip())
                        except:
                            pass

            except Exception as e:
                if state.ser:
                    state.ser.close()
                state.ser = None
                
        time.sleep(0.01)

# === Xbox Controller Thread ===
def xbox_controller_thread():
    add_log("Xbox Controller Thread Started...")
    controller = XboxController()
    if not controller.joystick:
        add_log("Xbox Controller not found. Waiting...")

    last_cmd = None
    last_missing_log = 0
    controller_ready = controller.joystick is not None
    using_browser_stream = False
    paused_for_flash = False

    while state.is_running:
        if state.is_flashing:
            if not paused_for_flash:
                paused_for_flash = True
            time.sleep(0.5)
            continue
        elif paused_for_flash:
            paused_for_flash = False

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
                if not using_browser_stream:
                    using_browser_stream = True
            else:
                using_browser_stream = False
                if controller_ready:
                    controller_ready = False
                if time.time() - last_missing_log > 3:
                    last_missing_log = time.time()
                time.sleep(0.1)
                continue

        if not controller_ready and source == "hardware":
            controller_ready = True

        cmd = _build_cmd_from_state(controller_state)

        if cmd != last_cmd:
            send_serial_command(cmd, source="Xbox")
            last_cmd = cmd

        controller_state_with_cmd = dict(controller_state)
        controller_state_with_cmd["cmd"] = cmd
        controller_state_with_cmd["source"] = source
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

@socketio.on('connect')
def handle_connect():
    add_log('Client connected via WebSocket')

@socketio.on('disconnect')
def handle_disconnect():
    print('Client disconnected')

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
        "bridge_ip": state.bridge_ip,
        "camera_ip": state.camera_ip,
        "video_url": state.video_url,
        "port": state.serial_port or "DISCONNECTED",
        "preferred_port": state.preferred_port,
        "dist": state.radar_dist,
        "logs": state.logs[-30:],  # 只回傳最近 30 條
        "ws_connected": state.ws_connected,
        "stream_connected": state.stream_connected,
        "ai_status": state.ai_enabled
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
    
    state.ai_enabled = not state.ai_enabled
    
    if state.ai_enabled and state.detector is None:
        try:
            state.detector = ObjectDetector()
            if not state.detector.enabled:
                state.ai_enabled = False
                state.detector = None
                return jsonify({"status": "error", "msg": "AI Init Failed"})
        except Exception as e:
            state.ai_enabled = False
            state.detector = None
            return jsonify({"status": "error", "msg": str(e)})
    
    status_str = "ACTIVATED" if state.ai_enabled else "DEACTIVATED"
    add_log(f"AI HUD {status_str}")
    return jsonify({"status": "ok", "ai_enabled": state.ai_enabled})

@app.route('/api/set_ip', methods=['POST'])
def api_set_ip():
    data = request.get_json(silent=True) or {}
    
    # 支援兩種格式
    car_ip = data.get('car_ip')
    cam_ip = data.get('cam_ip')
    
    if car_ip:
        state.car_ip = car_ip
        state.current_ip = car_ip
        add_log(f"🚗 Car IP Set: {car_ip}")
    
    if cam_ip:
        state.camera_ip = cam_ip
        state.video_url = f"http://{cam_ip}:{config.DEFAULT_STREAM_PORT}/stream"
        add_log(f"📹 Camera IP Set: {cam_ip}")
        add_log(f"🎥 Stream URL: {state.video_url}")
        if not state.bridge_ip:
            state.bridge_ip = cam_ip
            _persist_bridge_host(cam_ip)
    
    return jsonify({"status": "ok", "car_ip": car_ip, "cam_ip": cam_ip})

if __name__ == '__main__':
    # 啟動所有執行緒
    threading.Thread(target=serial_worker_thread, daemon=True).start()
    threading.Thread(target=udp_discovery_thread, daemon=True).start()
    threading.Thread(target=xbox_controller_thread, daemon=True).start()
    threading.Thread(target=websocket_bridge_thread, daemon=True).start()
    threading.Thread(target=video_stream_thread, daemon=True).start()  # 新增影像執行緒

    print("=" * 60)
    print(f"🚀 Web Server: http://127.0.0.1:{config.WEB_PORT}")
    print(f"📦 YOLO: {YOLO_AVAILABLE}")
    print(f"🔧 Serial Auto-Detection: ACTIVE")
    print(f"🎮 Xbox: {'ACTIVE' if pygame.joystick.get_count() > 0 else 'NOT FOUND'}")
    if state.video_url:
        print(f"🎥 Stream URL: {state.video_url}")
    print("=" * 60)

    socketio.run(app, host=config.WEB_HOST, port=config.WEB_PORT, debug=False)