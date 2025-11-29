import sys
import os
import cv2
import time
import threading
import re
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
socketio = SocketIO(app)

# === 全域狀態 ===
class SystemState:
    def __init__(self):
        self.current_ip = getattr(config, "DEFAULT_CAR_IP", "boebot.local")  # 車子控制 IP（相容用）
        self.bridge_ip = getattr(config, "DEFAULT_STREAM_IP", "") or getattr(config, "DEFAULT_CAR_IP", "")
        self.camera_ip = ""   # 相機串流 IP
        self.serial_port = None
        self.preferred_port = None
        self.ser = None
        self.ws_connected = False
        
        # 初始化影像串流 URL
        default_stream_ip = getattr(config, "DEFAULT_STREAM_IP", "")
        if default_stream_ip:
            self.video_url = f"http://{default_stream_ip}:{config.DEFAULT_STREAM_PORT}/stream"
        else:
            self.video_url = ""
            
        self.radar_dist = 0.0
        self.logs = []
        self.is_running = True
        self.ai_enabled = False
        self.detector = None
        self.is_flashing = False
        self.flash_lock = threading.Lock()
        self.add_log = None

state = SystemState()
ws_outbox: "SimpleQueue[str]" = SimpleQueue()

# Xbox 手把按鈕和搖桿的對應編號
AXIS_LEFT_STICK_X = 0
AXIS_LEFT_STICK_Y = 1
BUTTON_A = 0
BUTTON_B = 1
BUTTON_X = 2
BUTTON_Y = 3
BUTTON_LEFT_STICK = 8
JOYSTICK_DEADZONE = 0.15

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
    if len(state.logs) > 30:
        state.logs.pop(0)
    print(log_entry)
    socketio.emit('log', {'data': log_entry})

state.add_log = add_log

def _build_ws_url():
    host = state.bridge_ip or state.camera_ip or state.current_ip
    if not host:
        return None
    return f"ws://{host}:82/ws"


def websocket_bridge_thread():
    add_log("WebSocket Bridge Thread Started...")
    while state.is_running:
        url = _build_ws_url()
        if not url:
            state.ws_connected = False
            time.sleep(1)
            continue

        ws = None
        try:
            ws = websocket.create_connection(url, timeout=3)
            state.ws_connected = True
            add_log(f"🔗 WebSocket connected: {url}")

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
            add_log(f"[WS] Reconnect in 1s ({e})")
            time.sleep(1)
        finally:
            if ws:
                try:
                    ws.close()
                except Exception:
                    pass
            state.ws_connected = False

    add_log("WebSocket Bridge Thread Stopped")


# === 🔧 修正後的指令發送函數 ===
def send_serial_command(cmd, source="HTTP"):
    """
    優先透過 WebSocket 將指令推送到 ESP32-S3，再由 ESP-NOW 轉送到車子；
    保留原始 HTTP 控制與 Serial 備援以維持向下相容。
    """
    if not cmd:
        return False, "Empty command"

    ws_url = _build_ws_url()
    if ws_url and state.ws_connected:
        ws_outbox.put(cmd)
        return True, "Sent via WebSocket"

    # 方法2: 直接透過 WiFi HTTP 控制車子（相容）
    target_urls = []

    if state.current_ip:
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

    # 方法3: 透過 Serial 轉發（備用，需要 ESP32-S3 CAM 韌體支援）
    if state.ser and state.ser.is_open:
        try:
            state.ser.write(cmd.encode())
            return True, "Sent via Serial (fallback)"
        except Exception:
            pass

    if not hasattr(send_serial_command, '_last_fail_time') or \
       time.time() - send_serial_command._last_fail_time > 5:
        add_log(f"[{source}] ❌ Car unreachable: {cmd}")
        add_log(f"💡 嘗試的 URL: {', '.join(target_urls)}")
        add_log("💡 提示：確認車子已連線且網路可達")
        send_serial_command._last_fail_time = time.time()

    return False, "Car unreachable"

# === Threads ===
def serial_worker_thread():
    """
    這個 Thread 主要用來：
    1. 自動偵測並連接 Serial Port (通常是 ESP32-S3 CAM)
    2. 讀取 Serial 資料 (例如 IP、距離感測器數據)
    """
    add_log("Serial Worker Started...")
    while state.is_running:
        if state.is_flashing:
            time.sleep(0.5)
            continue
            
        # 自動偵測並連接 Serial Port
        if state.ser is None or not state.ser.is_open:
            ports = list_ports.comports()
            target = None

            # 優先使用使用者指定的 Port
            if state.preferred_port:
                for p in ports:
                    if p.device == state.preferred_port:
                        target = p.device
                        break
                if not target:
                    add_log(f"Preferred port {state.preferred_port} not found, waiting...")

            # 自動偵測
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
                    print(f"[SERIAL] Error: {e}")
                    time.sleep(2)
            else:
                time.sleep(1)
                continue
                
        # 讀取 Serial 資料
        if not state.is_flashing:
            try:
                if state.ser and state.ser.in_waiting:
                    line = state.ser.readline().decode(errors='ignore').strip()
                    if not line:
                        continue

                    add_log(f"[SERIAL] {line}")

                    # 解析 IP 地址
                    if "IP" in line and ("192." in line or "10." in line or "172." in line):
                        ip_match = re.search(r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}', line)
                        if ip_match:
                            ip = ip_match.group()
                            if state.camera_ip != ip:
                                state.camera_ip = ip
                                state.video_url = f"http://{ip}:{config.DEFAULT_STREAM_PORT}/stream"
                                add_log(f"📹 Camera IP detected: {ip}")
                                add_log(f"🎥 Stream URL updated: {state.video_url}")
                                if not state.bridge_ip:
                                    state.bridge_ip = ip
                                    add_log(f"🔗 WebSocket bridge host set: {ip}")
                            # 如果還沒設定車子 IP，使用相同網段猜測
                            if not state.current_ip:
                                add_log(f"💡 提示：請在 Settings 中設定車子的 IP 地址")

                    # 解析距離感測器數據
                    if "DIST:" in line:
                        try:
                            parts = line.split(":")
                            state.radar_dist = float(parts[1].strip())
                        except:
                            pass

            except Exception as e:
                print(f"[SERIAL] Read error: {e}")
                if state.ser:
                    state.ser.close()
                state.ser = None
                
        time.sleep(0.01)

def xbox_controller_thread():
    add_log("Xbox Controller Thread Started...")
    controller = XboxController()
    if not controller.joystick:
        add_log("Xbox Controller not found. Waiting for connection...")

    last_cmd = None
    COMMAND_THRESHOLD = 0.4
    last_missing_log = 0
    controller_ready = controller.joystick is not None

    while state.is_running:
        if state.is_flashing:
            if not paused_for_flash:
                add_log("⏳ Firmware flashing... pausing Xbox polling")
                paused_for_flash = True
            time.sleep(0.5)
            continue
        elif paused_for_flash:
            add_log("✅ Flash complete. Resuming Xbox polling")
            paused_for_flash = False

        controller_state = controller.get_input()
        if controller_state == "QUIT":
            state.is_running = False
            break

        if not controller_state:
            if not controller_ready:
                # 仍未連上
                pass
            else:
                controller_ready = False
                add_log("Xbox controller disconnected.")
            if time.time() - last_missing_log > 3:
                add_log("Waiting for Xbox controller...")
                last_missing_log = time.time()
            time.sleep(0.1)
            continue

        if not controller_ready:
            controller_ready = True
            add_log("Xbox controller connected.")

        # 決定方向指令（優先判斷按鍵）
        if controller_state.get("stick_pressed") or controller_state.get("button_x"):
            cmd = "S"
        else:
            x = controller_state.get("left_stick_x", 0)
            y = controller_state.get("left_stick_y", 0)
            if abs(x) < COMMAND_THRESHOLD and abs(y) < COMMAND_THRESHOLD:
                cmd = "S"
            elif abs(y) >= abs(x):
                cmd = "F" if y > 0 else "B"
            else:
                cmd = "R" if x > 0 else "L"

        if cmd != last_cmd:
            send_serial_command(cmd, source="Xbox")
            last_cmd = cmd

        controller_state_with_cmd = dict(controller_state)
        controller_state_with_cmd["cmd"] = cmd
        socketio.emit('controller_data', controller_state_with_cmd)
        time.sleep(0.02)
        
    pygame.quit()
    add_log("Xbox Controller Thread Stopped.")

def generate_frames():
    cap = None
    frame_count = 0
    while state.is_running:
        if state.video_url and (cap is None or not cap.isOpened()):
            print(f"[VIDEO] Connecting to {state.video_url}")
            cap = cv2.VideoCapture(state.video_url)
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            if not cap.isOpened():
                time.sleep(1)
                continue
            print("[VIDEO] Connected!")
            
        if cap and cap.isOpened():
            success, frame = cap.read()
            if success:
                frame_count += 1
                if state.ai_enabled:
                    try:
                        if state.detector is None:
                            print("[AI] Creating detector instance...")
                            add_log("Initializing AI Detector...")
                            state.detector = ObjectDetector()
                            if state.detector.enabled:
                                print("[AI] Detector ready!")
                                add_log("AI Detector Ready")
                            else:
                                print("[AI] Detector init failed")
                                state.ai_enabled = False
                                state.detector = None
                                
                        if state.detector and state.detector.enabled:
                            if frame_count % 30 == 0:
                                print(f"[AI] Processing frame {frame_count}...")
                            result = state.detector.detect(frame)
                            if isinstance(result, tuple) and len(result) == 3:
                                annotated_frame, detections, control_cmd = result
                                frame = annotated_frame
                                if detections and frame_count % 30 == 0:
                                    print(f"[AI] Detected: {detections}")
                            else:
                                print(f"[AI] Unexpected return format")
                                if isinstance(result, tuple):
                                    frame = result[0]
                    except Exception as e:
                        print(f"[AI ERROR] {e}")
                        import traceback
                        traceback.print_exc()
                        state.ai_enabled = False
                        state.detector = None
                        
                try:
                    ret, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
                    if ret:
                        frame_bytes = buffer.tobytes()
                        yield (b'--frame\r\n'
                               b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
                except Exception as e:
                    print(f"[VIDEO] Encode error: {e}")
            else:
                cap.release()
                cap = None
                time.sleep(0.5)
        else:
            time.sleep(0.5)

# === Flask 路由 和 SocketIO 事件 ===
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/video_feed')
def video_feed():
    return Response(generate_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')

@socketio.on('connect')
def handle_connect():
    print('Client connected')

@socketio.on('disconnect')
def handle_disconnect():
    print('Client disconnected')

@socketio.on('command')
def handle_command(data):
    cmd = data.get('cmd')
    send_serial_command(cmd, source="WebSocket")

@app.route('/api/status')
def api_status():
    return jsonify({
        "ip": state.current_ip,
        "car_ip": state.current_ip,
        "bridge_ip": state.bridge_ip,
        "camera_ip": state.camera_ip,
        "video_url": state.video_url,
        "port": state.serial_port or "DISCONNECTED",
        "preferred_port": state.preferred_port,
        "dist": state.radar_dist,
        "logs": state.logs,
        "ws_connected": state.ws_connected,
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

@app.route('/api/flash', methods=['POST'])
def api_flash():
    with state.flash_lock:
        if state.is_flashing:
            return jsonify({"status": "error", "msg": "Flash already in progress"})
        state.is_flashing = True
        add_log("🔒 Locking Serial Port for flashing...")
        
    try:
        if state.ser and state.ser.is_open:
            add_log("🔌 Closing Serial connection...")
            try:
                state.ser.close()
            except:
                pass
            state.ser = None
            
        add_log("⏳ Waiting for port release (2s)...")
        time.sleep(2)
        
        add_log("📝 Preparing sketch files...")
        success, msg = prepare_sketch()
        if not success:
            add_log(f"❌ Prepare Error: {msg}")
            return jsonify({"status": "error", "msg": msg})
            
        add_log("✅ Sketch files prepared")
        
        if not state.serial_port:
            add_log("❌ No Serial Port detected")
            return jsonify({"status": "error", "msg": "No Port detected. Please connect your ESP32."})
            
        add_log(f"🔥 Starting firmware flash on {state.serial_port}...")
        add_log("⚠️ Please do not disconnect the device!")
        
        def flash_log_callback(msg):
            add_log(f"[FLASH] {msg}")
            
        success = compile_and_upload(state.serial_port, flash_log_callback)
        
        if success:
            add_log("✅ Firmware flash completed successfully!")
            add_log("⏳ Waiting for device reboot (3s)...")
            time.sleep(3)
            return jsonify({"status": "ok", "msg": "Flash successful"})
        else:
            add_log("❌ Firmware flash failed")
            return jsonify({"status": "error", "msg": "Compile or upload failed. Check logs."})
            
    except Exception as e:
        add_log(f"❌ Flash Exception: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({"status": "error", "msg": str(e)})
    finally:
        add_log("🔓 Unlocking Serial Port...")
        state.is_flashing = False
        state.ser = None
        add_log("🔄 Serial Worker will reconnect automatically...")

@app.route('/api/toggle_ai', methods=['POST'])
def toggle_ai():
    if not YOLO_AVAILABLE:
        msg = "AI Library Missing (ultralytics)"
        return jsonify({"status": "error", "msg": msg})
        
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
    """
    設定兩種 IP：
    1. 影像串流 IP (ESP32-S3 CAM)
    2. 車子控制 IP (ESP8266)
    """
    data = request.get_json(silent=True) or {}
    ip = data.get('ip') or request.values.get('ip')
    ip_type = data.get('type', 'stream')  # 'stream' / 'car' / 'bridge'
    
    if not ip:
        return jsonify({"status": "error", "msg": "Invalid IP"})
    
    if ip_type == 'car':
        state.current_ip = ip
        add_log(f"🚗 Car Control IP Set: {ip}")
    elif ip_type == 'bridge':
        state.bridge_ip = ip
        add_log(f"🔗 WebSocket Bridge IP Set: {ip}")
    else:
        state.camera_ip = ip
        state.video_url = f"http://{ip}:{config.DEFAULT_STREAM_PORT}/stream"
        add_log(f"📹 Camera Stream IP Set: {ip}")
        if not state.bridge_ip:
            state.bridge_ip = ip
            add_log(f"🔗 WebSocket bridge host set: {ip}")
    
    return jsonify({"status": "ok", "ip": ip, "type": ip_type})

@app.route('/api/ports')
def api_ports():
    ports = list_ports.comports()
    port_list = [{"device": p.device, "description": p.description} for p in ports]
    return jsonify({"ports": port_list, "current": state.serial_port, "preferred": state.preferred_port})

@app.route('/api/set_port', methods=['POST'])
def api_set_port():
    data = request.json or {}
    port = data.get('port')
    ports = [p.device for p in list_ports.comports()]
    
    if not port or port not in ports:
        return jsonify({"status": "error", "msg": "Port not available"})

    state.preferred_port = port
    add_log(f"Preferred serial port set to {port}")

    # 如果當前連線不是目標 Port，強制重連
    if state.ser and state.ser.is_open and state.serial_port != port:
        try:
            state.ser.close()
        except Exception as e:
            print(f"[SERIAL] Close error: {e}")
        state.ser = None
        state.serial_port = None

    return jsonify({"status": "ok", "port": port})

if __name__ == '__main__':
    threading.Thread(target=serial_worker_thread, daemon=True).start()
    threading.Thread(target=xbox_controller_thread, daemon=True).start()
    threading.Thread(target=websocket_bridge_thread, daemon=True).start()

    print("=" * 60)
    print(f"🚀 Web Server Online: http://127.0.0.1:{config.WEB_PORT}")
    print(f"📦 YOLO Available: {YOLO_AVAILABLE}")
    print(f"🔧 Serial Auto-Detection: ACTIVE")
    print(f"🎮 Xbox Controller: {'ACTIVE' if pygame.joystick.get_count() > 0 else 'NOT FOUND'}")
    if state.video_url:
        print(f"🎥 Default Stream URL: {state.video_url}")
    print("=" * 60)

    socketio.run(app, host=config.WEB_HOST, port=config.WEB_PORT, debug=False)