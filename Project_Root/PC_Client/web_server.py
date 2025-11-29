import sys
import os
import cv2
import time
import threading
import re
import serial
import pygame
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
        self.current_ip = ""
        self.serial_port = None
        self.preferred_port = None
        self.ser = None
        self.video_url = (
            f"http://{config.DEFAULT_STREAM_IP}:{config.DEFAULT_STREAM_PORT}/stream"
            if getattr(config, "DEFAULT_STREAM_IP", "")
            else ""
        )
        self.radar_dist = 0.0
        self.logs = []
        self.is_running = True
        self.ai_enabled = False
        self.detector = None
        self.is_flashing = False
        self.flash_lock = threading.Lock()
        self.add_log = None

state = SystemState()

# Xbox 手把按鈕和搖桿的對應編號
AXIS_LEFT_STICK_X = 0
AXIS_LEFT_STICK_Y = 1
AXIS_RIGHT_STICK_X = 2
AXIS_RIGHT_STICK_Y = 3
AXIS_LEFT_TRIGGER = 4
AXIS_RIGHT_TRIGGER = 5
BUTTON_A = 0
BUTTON_B = 1
BUTTON_X = 2
BUTTON_Y = 3
BUTTON_LEFT_BUMPER = 4
BUTTON_RIGHT_BUMPER = 5
BUTTON_BACK = 6
BUTTON_START = 7
BUTTON_LEFT_STICK = 8
BUTTON_RIGHT_STICK = 9
JOYSTICK_DEADZONE = 0.15

class XboxController:
    def __init__(self):
        pygame.init()
        pygame.joystick.init()
        joystick_count = pygame.joystick.get_count()
        if joystick_count == 0:
            print("錯誤：未偵測到任何手把。")
            self.joystick = None
            return
        self.joystick = pygame.joystick.Joystick(0)
        self.joystick.init()
        print(f"成功初始化手把: {self.joystick.get_name()}")

    def get_input(self):
        if not self.joystick:
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
        hat_x, hat_y = self.joystick.get_hat(0)
        return {
            "left_stick_x": left_stick_x,
            "left_stick_y": -left_stick_y,
            "button_a": button_a_pressed,
            "button_b": button_b_pressed,
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

# === 串口寫入輔助 ===
def send_serial_command(cmd, source="HTTP"):
    if not cmd:
        return False, "Empty command"
    if not state.ser or not state.ser.is_open:
        add_log(f"[{source}] Serial unavailable")
        return False, "Serial not ready"
    try:
        state.ser.write(cmd.encode())
        return True, "Sent"
    except Exception as e:
        add_log(f"[{source}] Serial write failed: {e}")
        return False, str(e)

# === Threads ===
def serial_worker_thread():
    add_log("Serial Worker Started...")
    while state.is_running:
        if state.is_flashing:
            time.sleep(0.5)
            continue
        if state.ser is None or not state.ser.is_open:
            ports = list_ports.comports()
            target = None

            # 先檢查使用者指定的 Port
            if state.preferred_port:
                for p in ports:
                    if p.device == state.preferred_port:
                        target = p.device
                        break
                if not target:
                    add_log(f"Preferred port {state.preferred_port} not found, waiting...")

            # 若沒有指定或找不到，退回自動偵測
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
        if state.is_flashing:
            continue
        try:
            if state.ser and state.ser.in_waiting:
                line = state.ser.readline().decode(errors='ignore').strip()
                if not line:
                    continue
                if "IP" in line and ("192." in line or "10." in line):
                    ip_match = re.search(r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}', line)
                    if ip_match:
                        ip = ip_match.group()
                        state.current_ip = ip
                        state.video_url = f"http://{ip}:{config.DEFAULT_STREAM_PORT}/stream"
                        add_log(f"Auto-IP: {ip}")
                if "DIST:" in line:
                    try:
                        parts = line.split(":")
                        state.radar_dist = float(parts[1].strip())
                    except:
                        pass
                elif "DIST" not in line:
                    add_log(f"[ESP] {line}")
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
        add_log("Xbox Controller not found.")
        return
    while state.is_running:
        controller_state = controller.get_input()
        if controller_state == "QUIT":
            state.is_running = False
            break
        if controller_state:
            socketio.emit('controller_data', controller_state)
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
    send_serial_command(cmd, source="WS")

@app.route('/api/status')
def api_status():
    return jsonify({
        "ip": state.current_ip,
        "port": state.serial_port or "DISCONNECTED",
        "preferred_port": state.preferred_port,
        "dist": state.radar_dist,
        "logs": state.logs,
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
            add_log("📌 Closing Serial connection...")
            try:
                state.ser.close()
            except:
                pass
            state.ser = None
        add_log("⏳ Waiting for port release (2s)...")
        time.sleep(2)
        add_log("📁 Preparing sketch files...")
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
    data = request.json
    ip = data.get('ip')
    if ip:
        state.current_ip = ip
        state.video_url = f"http://{ip}:{config.DEFAULT_STREAM_PORT}/stream"
        add_log(f"Manual IP Set: {ip}")
        return jsonify({"status": "ok"})
    return jsonify({"status": "error", "msg": "Invalid IP"})

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

    print("=" * 60)
    print(f"🚀 Web Server Online: http://127.0.0.1:{config.WEB_PORT}")
    print(f"📦 YOLO Available: {YOLO_AVAILABLE}")
    print(f"🔧 Serial Auto-Detection: ACTIVE")
    print(f"🎮 Xbox Controller: {'ACTIVE' if pygame.joystick.get_count() > 0 else 'NOT FOUND'}")
    if state.video_url:
        print(f"🎥 Default Stream URL: {state.video_url}")
    print("=" * 60)

    socketio.run(app, host=config.WEB_HOST, port=config.WEB_PORT, debug=False)
# === 串口寫入輔助 ===
def send_serial_command(cmd, source="HTTP"):
    if not cmd:
        return False, "Empty command"
    if not state.ser or not state.ser.is_open:
        add_log(f"[{source}] Serial unavailable")
        return False, "Serial not ready"
    try:
        state.ser.write(cmd.encode())
        return True, "Sent"
    except Exception as e:
        add_log(f"[{source}] Serial write failed: {e}")
        return False, str(e)
