# serial_worker.py
import os
import shutil
import subprocess
import serial
import time
import re
from serial.tools import list_ports
import config

def prepare_sketch():
    """準備 Arduino 專案資料夾"""
    try:
        if not os.path.exists(config.SKETCH_DIR):
            os.makedirs(config.SKETCH_DIR)
        
        for fname in os.listdir(config.SKETCH_DIR):
            if fname.endswith(".ino") and fname != config.SKETCH_NAME:
                try: os.remove(os.path.join(config.SKETCH_DIR, fname))
                except: pass

        target_ino = os.path.join(config.SKETCH_DIR, config.SKETCH_NAME)
        if os.path.exists(config.SOURCE_INO):
            shutil.copy2(config.SOURCE_INO, target_ino)
            return True, "Sketch prepared"
        return False, f"Source not found: {config.SOURCE_INO}"
    except Exception as e:
        return False, str(e)

def compile_and_upload(port, log_callback=None):
    """編譯並燒錄"""
    def log(msg):
        if log_callback: log_callback(msg)
        print(f"[FLASH] {msg}")
    
    try:
        log("Checking Environment...")
        # 簡化檢查流程，直接嘗試編譯
        compile_cmd = [
            "arduino-cli", "compile", "--fqbn", config.FQBN, config.SKETCH_DIR,
            "--warnings", "none"
        ]
        log("Compiling... (this may take a while)")
        res = subprocess.run(compile_cmd, capture_output=True, encoding='utf-8', errors='ignore')
        if res.returncode != 0:
            log("❌ Compile Failed")
            if res.stderr: log(res.stderr[-200:]) # 只顯示最後錯誤
            return False
            
        log(f"Uploading to {port}...")
        upload_cmd = [
            "arduino-cli", "upload", "-p", port, "--fqbn", config.FQBN, config.SKETCH_DIR
        ]
        res = subprocess.run(upload_cmd, capture_output=True, encoding='utf-8', errors='ignore')
        if res.returncode != 0:
            log("❌ Upload Failed")
            return False
            
        log("✅ Success! Rebooting...")
        return True
    except Exception as e:
        log(f"Error: {e}")
        return False

def serial_worker(state):
    """Serial 監聽執行緒 (修復版)"""
    print("[SERIAL] Worker started")
    
    while state.is_running:
        if state.is_flashing:
            time.sleep(0.5)
            continue
        
        # 連線邏輯
        if state.ser is None or not state.ser.is_open:
            ports = list_ports.comports()
            target = None
            
            if state.preferred_port:
                for p in ports:
                    if p.device == state.preferred_port: target = p.device; break
            
            if not target:
                for p in ports:
                    # 寬鬆匹配 USB 裝置
                    if "USB" in p.description or "COM" in p.device:
                        target = p.device; break
            
            if target:
                try:
                    state.ser = serial.Serial(target, config.BAUD_RATE, timeout=0.1)
                    state.serial_port = target
                    print(f"[SERIAL] Connected to {target}")
                    if state.add_log: state.add_log(f"Serial connected: {target}")
                    time.sleep(2)
                except:
                    time.sleep(2)
            else:
                time.sleep(1)
                continue
        
        # 讀取邏輯
        try:
            if state.ser and state.ser.in_waiting:
                line = state.ser.readline().decode(errors='ignore').strip()
                if not line: continue
                
                # ★★★ 修復：放寬 IP 偵測條件 ★★★
                # 只要看到 "IP" 或 "http://" 或 "Stream" 且包含 IP 格式就抓取
                if ("IP" in line or "http" in line or "Stream" in line) and ("192." in line or "10." in line or "172." in line):
                    ip_match = re.search(r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}', line)
                    if ip_match:
                        ip = ip_match.group()
                        # 只有當 IP 改變時才更新，避免重複 log
                        if state.camera_ip != ip:
                            state.camera_ip = ip
                            state.video_url = f"http://{ip}:{config.DEFAULT_STREAM_PORT}/stream"
                            # 預設 bridge IP 也設為這個，除非有分流
                            if not state.bridge_ip: state.bridge_ip = ip
                            
                            if state.add_log: state.add_log(f"✅ Auto-detected IP: {ip}")
                            print(f"[SERIAL] Found IP: {ip}")

                if "DIST:" in line:
                    try:
                        state.radar_dist = float(line.split(":")[1].strip())
                    except: pass
                elif len(line) > 2 and "DIST" not in line:
                    # 除錯訊息，但過濾掉太短的雜訊
                     pass 
                    
        except Exception:
            if state.ser: state.ser.close()
            state.ser = None
        
        time.sleep(0.01)