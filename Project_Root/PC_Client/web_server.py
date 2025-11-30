import sys
import os
import cv2
import time
import threading
import re
import socket
import math
import psutil
from pathlib import Path
import queue
import requests
import serial
import pygame
import websocket
import numpy as np
from queue import SimpleQueue, Empty
from serial.tools import list_ports
from flask import Flask, render_template, Response, request, jsonify
from flask_socketio import SocketIO, emit
from requests.adapters import HTTPAdapter

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

# === 雙網卡綁定輔助類別 ===
class SourceAddressAdapter(HTTPAdapter):
    """允許 Requests 綁定特定來源 IP (網卡)"""
    def __init__(self, source_address, **kwargs):
        self.source_address = source_address
        super().__init__(**kwargs)

    def init_poolmanager(self, connections, maxsize, block=False, **pool_kwargs):
        pool_kwargs['source_address'] = (self.source_address, 0)
        super().init_poolmanager(connections, maxsize, block, **pool_kwargs)

# === 雙網卡自動偵測邏輯 ===
def get_network_info():
    """偵測所有網卡並自動分類為 Camera Net 或 Internet Net"""
    info = {
        "all_ifaces": [],
        "camera_net": None,
        "internet_net": None
    }

    try:
        # 取得所有網卡狀態
        stats = psutil.net_if_stats()
        # 取得所有網卡位址
        addrs = psutil.net_if_addrs()

        for iface_name, iface_addrs in addrs.items():
            # 過濾未啟用網卡
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
                    if info["camera_net"] is None: # 優先選第一個
                        info["camera_net"] = iface_data
                elif info["internet_net"] is None: # 非 192.168.4.x 的第一個視為 Internet/Car Net
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

def _apply_camera_ip(ip, stream_url=None, prefix=""):
    if state.camera_ip != ip:
        state.camera_ip = ip
        state.video_url = stream_url or f"http://{ip}:{config.DEFAULT_STREAM_PORT}/stream"
        add_log(f"{prefix}Camera IP detected: {ip}")
        add_log(f"{prefix}Stream URL: {state.video_url}")
    
    if not state.bridge_ip or state.bridge_ip.endswith('.local') or state.bridge_ip != ip:
        state.bridge_ip = ip
        _persist_bridge_host(ip)
        add_log(f"{prefix}Bridge host updated to {ip}")

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
        # 1. 執行網卡偵測
        self.net_info = get_network_info()
        self.print_network_summary()

        cached_bridge = _load_cached_bridge_host()
        default_stream_hosts = getattr(config, "DEFAULT_STREAM_HOSTS", [])
        default_stream_ip = getattr(config, "DEFAULT_STREAM_IP", "")

        # 2. 自動設定 IP
        if self.net_info["camera_net"]:
            self.camera_ip = "192.168.4.1"
            print(f"[INIT] Auto-selected Camera IP: {self.camera_ip} (via {self.net_info['camera_net']['name']})")
        else:
            self.camera_ip = getattr(config, "DEFAULT_STREAM_IP", "") or \
                             (cached_bridge if cached_bridge else "")

        # 車子 IP 設定
        self.car_ip = getattr(config, "DEFAULT_CAR_IP", "boebot.local")
        self.current_ip = self.car_ip

        self.bridge_ip = cached_bridge or default_stream_ip or getattr(config, "DEFAULT_CAR_IP", "")

        self.stream_hosts = _unique_hosts([
            self.camera_ip, # 優先
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

        self.video_url = _build_stream_url(self.camera_ip)

        self.radar_dist = 0.0
        self.logs = []
        self.is_running = True
        self.ai_enabled = False
        self.detector = None
        self.is_flashing = False
        self.flash_lock = threading.Lock()
        self.add_log = None
        
        self.frame_buffer = None
        self.frame_lock = threading.Lock()
        self.stream_connected = False

        # 緩存控制 Session
        self.control_session = requests.Session()
        # 若有偵測到對外網卡，綁定控制 Session 到該網卡 IP
        if self.net_info['internet_net']:
             try:
                 self.control_session.mount('http://', SourceAddressAdapter(self.net_info['internet_net']['ip']))
                 print(f"[INIT] Bound Control/Internet Traffic to: {self.net_info['internet_net']['ip']}")
             except Exception as e:
                 print(f"[INIT] Failed to bind control session: {e}")

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
UDP_PORT = 4210
CAMERA_DISCOVERY_PORT = getattr(config, "CAMERA_DISCOVERY_PORT", 4211)
udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
udp_sock.settimeout(0.3)

# 嘗試綁定 UDP Socket 到對外網卡
try:
    if state.net_info['internet_net']:
        udp_sock.bind((state.net_info['internet_net']['ip'], 0))
        print(f"[UDP] Bound to {state.net_info['internet_net']['ip']}")
except Exception as e:
    print(f"[UDP] Bind error: {e}")

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
    throttle = y
    turn = x
    left = max(min(throttle + turn, 1.0), -1.0)
    right = max(min(throttle - turn, 1.0), -1.0)
    left_pwm = int(PWM_CENTER + left * PWM_RANGE)
    right_pwm = int(PWM_CENTER - right * PWM_RANGE)
    return left_pwm, right_pwm

def _build_cmd_from_state(controller_state: dict) -> str:
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
    while state.is_running:
        base_candidates = [state.bridge_ip, state.camera_ip, state.current_ip]
        stream_hosts = [h for h, _ in _get_stream_candidates()]
        candidates = _unique_hosts([h for h in (*base_candidates, *stream_hosts) if h])

        host = next((h for h in candidates if _is_valid_ip(h) or _is_host_resolvable(h)), None)
        if not host:
            state.ws_connected = False
            time.sleep(0.5)
            continue

        url = _build_ws_url(host)
        if not url:
            state.ws_connected = False
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
                except Exception:
                    break

        except Exception:
            state.ws_connected = False
            time.sleep(0.5)
        finally:
            if ws:
                try: ws.close()
                except: pass
            state.ws_connected = False

def send_udp_command(cmd: str):
    if not cmd:
        return False
    target_ip = state.car_ip or state.current_ip
    if not target_ip:
        return False
    try:
        # UDP Socket 已經在全域初始化並綁定（如果可能）
        udp_sock.sendto(cmd.encode(), (target_ip, UDP_PORT))
        return True
    except OSError:
        return False

# 記錄最後一次成功的發送方式，以優化速度
last_successful_method = "UDP"

def send_serial_command(cmd, source="HTTP"):
    global last_successful_method
    if not cmd:
        return False, "Empty command"

    # === 優化策略：優先使用上次成功的方法 ===

    # 嘗試 UDP
    if last_successful_method == "UDP" or last_successful_method is None:
        if send_udp_command(cmd):
            last_successful_method = "UDP"
            return True, "Sent via UDP"

    # 嘗試 WebSocket
    ws_url = _build_ws_url()
    if state.ws_connected and (last_successful_method == "WS" or last_successful_method is None):
        ws_outbox.put(cmd)
        last_successful_method = "WS"
        return True, "Sent via WebSocket"

    # 嘗試 HTTP (使用 Session 和 Source Binding)
    # 為了避免阻塞，將 HTTP timeout 設得非常短
    target_urls = []
    if state.car_ip: target_urls.append(f"http://{state.car_ip}/cmd")
    if state.current_ip and state.current_ip != state.car_ip: target_urls.append(f"http://{state.current_ip}/cmd")

    # 如果 UDP 失敗，嘗試 HTTP
    for url in target_urls:
        try:
            # 使用已綁定的 session (如果有)
            resp = state.control_session.get(f"{url}?act={cmd}", timeout=0.3)
            if resp.ok:
                last_successful_method = "HTTP"
                return True, "Sent via WiFi"
        except requests.exceptions.RequestException:
            continue

    # 如果 HTTP 也失敗，重試 UDP (也許剛才只是掉包)
    if send_udp_command(cmd):
        last_successful_method = "UDP"
        return True, "Sent via UDP (Retry)"

    # 最後手段：Serial
    if state.ser and state.ser.is_open:
        try:
            state.ser.write(cmd.encode())
            return True, "Sent via Serial (fallback)"
        except Exception:
            pass

    return False, "Car unreachable"

# === MJPEG Reader (Requests + Source Binding) ===
class MJPEGStreamReader:
    def __init__(self, url, source_ip=None):
        self.url = url
        self.source_ip = source_ip
        self.running = False
        self.latest_frame = None
        self.connected = False
        self.lock = threading.Lock()
        self.thread = None
        self._stop_event = threading.Event()

    def start(self):
        if self.running: return
        self.running = True
        self._stop_event.clear()
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def stop(self):
        self.running = False
        self._stop_event.set()
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=1.0)

    def _run(self):
        retry_delay = 1
        while self.running and not self._stop_event.is_set():
            session = requests.Session()
            # 綁定到 Camera 網卡
            if self.source_ip:
                try:
                    session.mount('http://', SourceAddressAdapter(self.source_ip))
                except Exception as e:
                    add_log(f"[VIDEO] Bind Warning: {e}")

            try:
                # add_log(f"[VIDEO] Connecting to {self.url}...")
                with session.get(self.url, stream=True, timeout=5) as r:
                    if r.status_code != 200:
                        add_log(f"[VIDEO] HTTP {r.status_code}")
                        time.sleep(retry_delay)
                        continue

                    add_log("[VIDEO] ✅ Stream connected!")
                    self.connected = True
                    retry_delay = 1
                    
                    bytes_buffer = bytes()
                    
                    # 讀取串流
                    for chunk in r.iter_content(chunk_size=4096):
                        if not self.running or self._stop_event.is_set():
                            break
                        bytes_buffer += chunk

                        # 簡單尋找 JPEG 邊界
                        a = bytes_buffer.find(b'\xff\xd8')
                        b = bytes_buffer.find(b'\xff\xd9')

                        if a != -1 and b != -1:
                            jpg = bytes_buffer[a:b+2]
                            bytes_buffer = bytes_buffer[b+2:]

                            try:
                                frame = cv2.imdecode(np.frombuffer(jpg, dtype=np.uint8), cv2.IMREAD_COLOR)
                                if frame is not None:
                                    # 如果有開啟 AI，可以在這裡處理，或者傳出去處理
                                    if state.ai_enabled and state.detector and state.detector.enabled:
                                        try:
                                            result = state.detector.detect(frame)
                                            if isinstance(result, tuple) and len(result) == 3:
                                                frame, detections, control_cmd = result
                                        except Exception as e:
                                            pass

                                    with self.lock:
                                        self.latest_frame = frame
                            except Exception:
                                pass
            except Exception as e:
                self.connected = False
                # add_log(f"[VIDEO] Disconnected: {e}")
                time.sleep(retry_delay)
                retry_delay = min(retry_delay * 1.5, 5)

def video_stream_thread():
    """使用 Requests-based Reader 替代不穩定的 OpenCV VideoCapture"""
    add_log("Video Stream Thread (Requests) Started...")

    current_reader = None
    last_url = None

    while state.is_running:
        candidates = _get_stream_candidates()
        candidates = [(h, u) for h, u in candidates if h and not h.endswith('.local') and _is_valid_ip(h)]

        target_host = None
        target_url = None

        # 選擇目標 URL
        if candidates:
            # 如果目前有設定的 camera_ip 且在候選名單中，優先使用
            for h, u in candidates:
                if h == state.camera_ip:
                    target_host = h
                    target_url = u
                    break
            # 否則選第一個
            if not target_url:
                target_host, target_url = candidates[0]
                state.camera_ip = target_host
                state.video_url = target_url

        if not target_url:
            time.sleep(2)
            continue

        # 決定綁定 IP
        bind_ip = None
        if state.net_info['camera_net']:
            bind_ip = state.net_info['camera_net']['ip']

        # 啟動或重啟 Reader
        if target_url != last_url or current_reader is None:
            if current_reader:
                current_reader.stop()

            add_log(f"[VIDEO] Target: {target_url} via {bind_ip or 'Default Route'}")
            current_reader = MJPEGStreamReader(target_url, source_ip=bind_ip)
            current_reader.start()
            last_url = target_url
            state.stream_connected = True

        # 同步畫面到全域 Buffer
        if current_reader and current_reader.latest_frame is not None:
            with current_reader.lock:
                frame = current_reader.latest_frame.copy()
            with state.frame_lock:
                state.frame_buffer = frame
            time.sleep(0.01)
        else:
            time.sleep(0.1)

    if current_reader:
        current_reader.stop()
    add_log("Video Stream Thread Stopped")

def generate_frames():
    no_signal_frame = None
    
    while state.is_running:
        with state.frame_lock:
            if state.frame_buffer is not None:
                frame = state.frame_buffer.copy()
            else:
                frame = None
        
        if frame is None:
            if no_signal_frame is None:
                no_signal_frame = create_no_signal_frame()
            frame = no_signal_frame
        
        try:
            ret, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
            if ret:
                frame_bytes = buffer.tobytes()
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
        except Exception:
            pass
        
        time.sleep(0.03)

def create_no_signal_frame():
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

    # 綁定到 Camera 網卡 (如果有的話)，因為相機廣播通常在區域網路
    # 但廣播是 255.255.255.255，可能需要綁定 0.0.0.0
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
        except Exception:
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
                except Exception:
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
                    # 解析 Serial 訊息 (省略詳細解析以保持簡潔)
            except Exception:
                if state.ser:
                    state.ser.close()
                state.ser = None
        time.sleep(0.01)

# === Xbox Controller Thread ===
def xbox_controller_thread():
    add_log("Xbox Controller Thread Started...")
    controller = XboxController()
    last_cmd = None
    using_browser_stream = False
    paused_for_flash = False

    while state.is_running:
        if state.is_flashing:
            time.sleep(0.5)
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
            else:
                time.sleep(0.1)
                continue

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
        "logs": state.logs[-30:],
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
    return jsonify({"status": "ok", "ai_enabled": state.ai_enabled})

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
        state.video_url = f"http://{cam_ip}:{config.DEFAULT_STREAM_PORT}/stream"
        add_log(f"📹 Camera IP Set: {cam_ip}")
        if not state.bridge_ip:
            state.bridge_ip = cam_ip
            _persist_bridge_host(cam_ip)
    return jsonify({"status": "ok", "car_ip": car_ip, "cam_ip": cam_ip})

@app.route('/netinfo')
def api_netinfo():
    return jsonify(state.net_info)

if __name__ == '__main__':
    threading.Thread(target=serial_worker_thread, daemon=True).start()
    threading.Thread(target=udp_discovery_thread, daemon=True).start()
    threading.Thread(target=xbox_controller_thread, daemon=True).start()
    threading.Thread(target=websocket_bridge_thread, daemon=True).start()
    threading.Thread(target=video_stream_thread, daemon=True).start()

    print("=" * 60)
    print(f"🚀 Web Server: http://127.0.0.1:{config.WEB_PORT}")
    print(f"📦 YOLO: {YOLO_AVAILABLE}")
    print("=" * 60)
    state.print_network_summary()

    socketio.run(app, host=config.WEB_HOST, port=config.WEB_PORT, debug=False, allow_unsafe_werkzeug=True)
