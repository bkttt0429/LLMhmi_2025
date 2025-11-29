# serial_worker.py
import os
import shutil
import subprocess
import serial
import time
from serial.tools import list_ports
import config

def prepare_sketch():
    """
    準備 Arduino 專案資料夾
    回傳 (success: bool, message: str)
    """
    try:
        # 確保目標資料夾存在
        if not os.path.exists(config.SKETCH_DIR):
            os.makedirs(config.SKETCH_DIR)
            print(f"[FLASH] Created directory: {config.SKETCH_DIR}")
        
        # 複製 .ino 檔案
        target_ino = os.path.join(config.SKETCH_DIR, config.SKETCH_NAME)
        if os.path.exists(config.SOURCE_INO):
            shutil.copy2(config.SOURCE_INO, target_ino)
            print(f"[FLASH] Copied {config.SOURCE_INO} -> {target_ino}")
        else:
            return False, f"Source file not found: {config.SOURCE_INO}"
        
        return True, "Sketch prepared successfully"
    
    except Exception as e:
        return False, f"Prepare error: {str(e)}"

def compile_and_upload(port, log_callback=None):
    """
    編譯並燒錄韌體到 ESP32
    
    Args:
        port: Serial port (例如 COM3 或 /dev/ttyUSB0)
        log_callback: 可選的 log 回調函數
    
    Returns:
        bool: 成功為 True, 失敗為 False
    """
    def log(msg):
        if log_callback:
            log_callback(msg)
        print(f"[FLASH] {msg}")
    
    try:
        # 1. 檢查 arduino-cli
        log("Checking Arduino CLI...")
        try:
            result = subprocess.run(["arduino-cli", "version"], 
                         capture_output=True, check=True, timeout=10,
                         encoding='utf-8', errors='ignore')  # ⭐ 修復編碼問題
            if result.stdout:
                log(f"Arduino CLI: {result.stdout.strip()}")
            else:
                log("Arduino CLI: Installed (version check ok)")
        except FileNotFoundError:
            log("ERROR: arduino-cli not found. Please install it first.")
            log("Visit: https://arduino.github.io/arduino-cli/installation/")
            return False
        except subprocess.TimeoutExpired:
            log("ERROR: arduino-cli timeout")
            return False
        except Exception as e:
            log(f"Arduino CLI check warning: {e}")
            # 繼續執行，因為可能只是版本輸出問題
        
        # 2. 更新板卡索引
        log("Updating board index...")
        try:
            subprocess.run([
                "arduino-cli", "core", "update-index",
                "--additional-urls", config.ESP32_URL
            ], capture_output=True, check=True, timeout=60,
               encoding='utf-8', errors='ignore')  # ⭐ 修復編碼
            log("Board index updated")
        except subprocess.TimeoutExpired:
            log("Index update timeout (continuing anyway)")
        except Exception as e:
            log(f"Index update warning: {e}")
        
        # 3. 檢查並安裝 ESP32 核心
        log("Checking ESP32 core...")
        try:
            result = subprocess.run([
                "arduino-cli", "core", "list"
            ], capture_output=True, timeout=10,
               encoding='utf-8', errors='ignore')  # ⭐ 修復編碼
            
            output = result.stdout if result.stdout else ""
            
            if "esp32:esp32" not in output:
                log("Installing ESP32 core (this may take several minutes)...")
                result = subprocess.run([
                    "arduino-cli", "core", "install", "esp32:esp32",
                    "--additional-urls", config.ESP32_URL
                ], capture_output=True, check=True, timeout=300,
                   encoding='utf-8', errors='ignore')  # ⭐ 修復編碼
                log("ESP32 core installed")
            else:
                log("ESP32 core already installed")
        except subprocess.TimeoutExpired:
            log("ERROR: Core installation timeout")
            return False
        except Exception as e:
            log(f"Core install error: {e}")
            return False
        
        # 4. 編譯
        log("Compiling firmware...")
        log(f"Sketch: {config.SKETCH_DIR}")
        log(f"FQBN: {config.FQBN}")
        
        compile_cmd = [
            "arduino-cli", "compile",
            "--fqbn", config.FQBN,
            config.SKETCH_DIR,
            "--verbose"
        ]
        
        result = subprocess.run(compile_cmd, 
                              capture_output=True, 
                              timeout=180,
                              encoding='utf-8', errors='ignore')  # ⭐ 修復編碼
        
        if result.returncode != 0:
            log(f"❌ Compile failed!")
            if result.stderr:
                # 只顯示最後幾行錯誤
                error_lines = result.stderr.strip().split('\n')
                for line in error_lines[-10:]:  # 最後10行
                    log(f"  {line}")
            return False
        
        log("✅ Compile successful!")
        
        # 5. 上傳前確認 Port 可用
        log(f"Verifying port {port}...")
        ports = list_ports.comports()
        port_found = False
        for p in ports:
            if p.device == port:
                port_found = True
                log(f"Port confirmed: {p.device} - {p.description}")
                break
        
        if not port_found:
            log(f"❌ Port {port} not found!")
            log("Available ports:")
            for p in ports:
                log(f"  - {p.device}: {p.description}")
            return False
        
        # 6. 上傳
        log(f"Uploading to {port}...")
        upload_cmd = [
            "arduino-cli", "upload",
            "-p", port,
            "--fqbn", config.FQBN,
            config.SKETCH_DIR,
            "--verbose"
        ]
        
        result = subprocess.run(upload_cmd, 
                              capture_output=True, 
                              timeout=120,
                              encoding='utf-8', errors='ignore')  # ⭐ 修復編碼
        
        if result.returncode != 0:
            log(f"❌ Upload failed!")
            if result.stderr:
                # 只顯示最後幾行錯誤
                error_lines = result.stderr.strip().split('\n')
                for line in error_lines[-10:]:
                    log(f"  {line}")
            return False
        
        log("✅ Upload successful!")
        log("Device is rebooting...")
        time.sleep(3)  # 等待設備重啟
        
        return True
    
    except subprocess.TimeoutExpired:
        log("❌ Operation timeout!")
        return False
    except Exception as e:
        log(f"❌ Flash error: {str(e)}")
        import traceback
        log(traceback.format_exc())
        return False

def serial_worker(state):
    """
    Serial 工作執行緒
    持續監控並連接 Serial Port
    """
    print("[SERIAL] Worker started")
    
    while state.is_running:
        # ⭐ 如果正在燒錄，暫停所有 Serial 操作
        if state.is_flashing:
            time.sleep(0.5)
            continue
        
        # 如果沒有連接, 嘗試連接
        if state.ser is None or not state.ser.is_open:
            ports = list_ports.comports()
            target = None

            # 若 state 有指定 Port，優先使用
            preferred = getattr(state, 'preferred_port', None)
            if preferred:
                for p in ports:
                    if p.device == preferred:
                        target = p.device
                        break

            # 自動偵測
            if not target:
                for p in ports:
                    # 尋找 USB Serial 裝置
                    if "USB" in p.description or "COM" in p.device or "ttyUSB" in p.device or "ttyACM" in p.device:
                        target = p.device
                        break
            
            if target:
                try:
                    state.ser = serial.Serial(target, config.BAUD_RATE, timeout=0.1)
                    state.serial_port = target
                    if state.add_log:
                        state.add_log(f"Connected to {target}")
                    print(f"[SERIAL] Connected to {target}")
                    time.sleep(2)  # 等待裝置初始化
                except Exception as e:
                    print(f"[SERIAL] Connection failed: {e}")
                    time.sleep(2)
            else:
                time.sleep(1)
                continue
        
        # 讀取 Serial 數據
        try:
            if state.ser and state.ser.in_waiting:
                line = state.ser.readline().decode(errors='ignore').strip()
                if not line:
                    continue
                
                # 解析 IP 地址
                if "IP" in line and ("192." in line or "10." in line):
                    import re
                    ip_match = re.search(r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}', line)
                    if ip_match:
                        ip = ip_match.group()
                        state.current_ip = ip
                        state.video_url = f"http://{ip}:{config.DEFAULT_STREAM_PORT}/stream"
                        if state.add_log:
                            state.add_log(f"Auto-detected IP: {ip}")
                        print(f"[SERIAL] IP: {ip}")
                
                # 解析距離數據
                if "DIST:" in line:
                    try:
                        parts = line.split(":")
                        state.radar_dist = float(parts[1].strip())
                    except:
                        pass
                elif "DIST" not in line:
                    # 其他訊息
                    if state.add_log:
                        state.add_log(f"[ESP] {line}")
        
        except Exception as e:
            print(f"[SERIAL] Read error: {e}")
            if state.ser:
                state.ser.close()
            state.ser = None
            state.serial_port = None
        
        time.sleep(0.01)
    
    # 清理
    if state.ser:
        state.ser.close()
    print("[SERIAL] Worker stopped")