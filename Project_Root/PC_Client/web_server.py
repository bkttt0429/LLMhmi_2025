import sys
import os
import cv2
import time
import threading
import re
import serial
from serial.tools import list_ports
from flask import Flask, render_template, Response, request, jsonify

# 路徑設定
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.append(BASE_DIR)
import config

# 匯入 AI 模組
from ai_detector import ObjectDetector, YOLO_AVAILABLE

# 初始化 Flask
template_dir = os.path.join(BASE_DIR, 'templates')
app = Flask(__name__, template_folder=template_dir, static_folder=template_dir)

# === 全域狀態 ===
class SystemState:
    def __init__(self):
        self.current_ip = ""
        self.serial_port = None
        self.ser = None
        self.video_url = ""
        self.radar_dist = 0.0
        self.logs = []
        self.is_running = True
        # AI 狀態
        self.ai_enabled = False
        self.detector = None

state = SystemState()

# === 輔助函式 ===
def add_log(msg):
    timestamp = time.strftime("%H:%M:%S")
    log_entry = f"[{timestamp}] {msg}"
    state.logs.append(log_entry)
    if len(state.logs) > 20: 
        state.logs.pop(0)
    print(log_entry)  # 同時印到終端

# === Serial 工作執行緒 ===
def serial_worker():
    add_log("Serial Worker Started...")
    while state.is_running:
        if state.ser is None or not state.ser.is_open:
            ports = list_ports.comports()
            target = None
            for p in ports:
                if "USB" in p.description or "COM" in p.device:
                    target = p.device
                    break
            
            if target:
                try:
                    state.ser = serial.Serial(target, config.BAUD_RATE, timeout=0.1)
                    state.serial_port = target
                    add_log(f"Connected to {target}")
                    time.sleep(2)
                except: 
                    time.sleep(2)
            else:
                time.sleep(1)
                continue

        try:
            if state.ser.in_waiting:
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
        except:
            if state.ser: 
                state.ser.close()
            state.ser = None
        
        time.sleep(0.01)

# === 影像串流生成器 ===
def generate_frames():
    cap = None
    frame_count = 0
    
    while state.is_running:
        # 連線串流
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
                
                # --- AI 處理區塊 ---
                if state.ai_enabled:
                    try:
                        # 初始化檢測器
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
                        
                        # 執行偵測
                        if state.detector and state.detector.enabled:
                            # 每30幀印一次提示
                            if frame_count % 30 == 0:
                                print(f"[AI] Processing frame {frame_count}...")
                            
                            # ⚠️ 關鍵修正：接收 3 個回傳值
                            result = state.detector.detect(frame)
                            
                            # 確認回傳格式
                            if isinstance(result, tuple) and len(result) == 3:
                                annotated_frame, detections, control_cmd = result
                                frame = annotated_frame
                                
                                # 如果有偵測到物體,印出來
                                if detections and frame_count % 30 == 0:
                                    print(f"[AI] Detected: {detections}")
                            else:
                                print(f"[AI] Unexpected return format: {type(result)}, len={len(result) if isinstance(result, tuple) else 'N/A'}")
                                # 如果格式不對,至少嘗試取第一個元素(應該是 frame)
                                if isinstance(result, tuple):
                                    frame = result[0]
                    
                    except Exception as e:
                        print(f"[AI ERROR] {e}")
                        import traceback
                        traceback.print_exc()
                        state.ai_enabled = False
                        state.detector = None
                # ------------------------

                # 編碼並傳送
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

# === Flask 路由 ===

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/video_feed')
def video_feed():
    return Response(generate_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/api/status')
def api_status():
    return jsonify({
        "ip": state.current_ip,
        "port": state.serial_port or "DISCONNECTED",
        "dist": state.radar_dist,
        "logs": state.logs,
        "ai_status": state.ai_enabled
    })

@app.route('/api/toggle_ai', methods=['POST'])
def toggle_ai():
    """開關 AI 檢測"""
    print(f"[API] toggle_ai called, YOLO_AVAILABLE={YOLO_AVAILABLE}")
    
    if not YOLO_AVAILABLE:
        msg = "AI Library Missing (ultralytics)"
        print(f"[API] {msg}")
        return jsonify({"status": "error", "msg": msg})

    # 切換狀態
    state.ai_enabled = not state.ai_enabled
    print(f"[API] AI enabled = {state.ai_enabled}")
    
    # 如果啟動但沒有偵測器,先建立
    if state.ai_enabled and state.detector is None:
        print("[API] Creating detector...")
        add_log("Initializing AI Detector...")
        try:
            state.detector = ObjectDetector()
            if not state.detector.enabled:
                print("[API] Detector init failed")
                state.ai_enabled = False
                state.detector = None
                return jsonify({"status": "error", "msg": "AI Init Failed"})
        except Exception as e:
            print(f"[API] Detector creation error: {e}")
            state.ai_enabled = False
            state.detector = None
            return jsonify({"status": "error", "msg": str(e)})

    status_str = "ACTIVATED" if state.ai_enabled else "DEACTIVATED"
    add_log(f"AI HUD {status_str}")
    print(f"[API] Returning ai_enabled={state.ai_enabled}")
    
    return jsonify({"status": "ok", "ai_enabled": state.ai_enabled})

@app.route('/api/control', methods=['POST'])
def api_control():
    data = request.json
    cmd = data.get('cmd')
    if state.ser and state.ser.is_open:
        state.ser.write(cmd.encode())
        return jsonify({"status": "ok"})
    return jsonify({"status": "error"})

@app.route('/api/set_ip', methods=['POST'])
def api_set_ip():
    data = request.json
    ip = data.get('ip')
    if ip:
        state.current_ip = ip
        state.video_url = f"http://{ip}:{config.DEFAULT_STREAM_PORT}/stream"
        add_log(f"Manual IP Set: {ip}")
        return jsonify({"status": "ok"})
    return jsonify({"status": "error"})

if __name__ == '__main__':
    # 啟動 Serial 背景執行緒
    t = threading.Thread(target=serial_worker, daemon=True)
    t.start()
    
    print("=" * 60)
    print(f"🚀 Web Server Online: http://127.0.0.1:{config.WEB_PORT}")
    print(f"📦 YOLO Available: {YOLO_AVAILABLE}")
    print("=" * 60)
    
    app.run(host=config.WEB_HOST, port=config.WEB_PORT, debug=False, threaded=True)