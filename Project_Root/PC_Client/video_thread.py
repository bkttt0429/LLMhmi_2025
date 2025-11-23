from PySide6.QtCore import QThread, Signal
from PySide6.QtGui import QImage
import cv2
import numpy as np
import socket
from urllib.parse import urlparse
# 未來解鎖： from ai_detector import ObjectDetector

def check_connection(host, port, timeout=3, retries=1):
    """檢查 TCP 連線是否可以建立

    參數:
    - host: 主機名稱或 IP
    - port: 埠號 (int 或可轉成 int 的字串)
    - retries: 重試次數
    """
    try:
        if not host:
            return False, f"無效的主機: {host}"

        port_int = int(port)
        attempt = 0
        while attempt < max(1, retries):
            try:
                with socket.create_connection((host, port_int), timeout=timeout):
                    return True, "連線成功"
            except socket.timeout:
                attempt += 1
                if attempt >= retries:
                    raise
                # small backoff
                time.sleep(0.3)
    except ValueError:
        return False, f"無效的埠號: {port}"
    except socket.timeout:
        return False, f"連線到 {host}:{port} 超時 ({timeout}秒)"
    except Exception as e:
        return False, f"連線到 {host}:{port} 失敗: {e}"


class VideoThread(QThread):
    change_pixmap_signal = Signal(QImage)
    status_signal = Signal(str)
    
    def __init__(self, url):
        super().__init__()
        self.url = url
        self.is_running = True
        self.enable_ai = False  # AI 開關
        
        # 未來解鎖： self.detector = ObjectDetector()

    def run(self):
        # --- Pre-flight Check ---
        parsed_url = urlparse(self.url)
        hostname = parsed_url.hostname
        port = parsed_url.port or 81 # ESP-CAM 通常是 81

        if not hostname:
            self.status_signal.emit(f"❌ 無效的 URL 或 IP: {self.url}")
            return
            
        self.status_signal.emit(f"正在檢查網路連線到 {hostname}:{port}...")
        
        # 檢查連線（若失敗，不立即放棄，改以警告訊息並嘗試開啟串流）
        connected, message = check_connection(hostname, port, timeout=3, retries=2)
        if not connected:
            # 若 TCP 檢查失敗，仍嘗試使用 OpenCV 開啟串流（某些設備或網路會讓 raw socket 檢查超時）
            self.status_signal.emit(f"⚠️ 檢查網路到 {hostname}:{port} 失敗: {message}，仍嘗試開啟串流...")
        else:
            self.status_signal.emit("✅ 網路連線正常，正在開啟串流...")
        
        # --- OpenCV 連線 ---
        print(f"嘗試連接串流: {self.url}")
        # 先嘗試使用 FFMPEG backend，失敗時回退到系統預設 backend
        cap = cv2.VideoCapture(self.url, cv2.CAP_FFMPEG)

        if not cap.isOpened():
            # 清理並回退
            try:
                cap.release()
            except:
                pass
            self.status_signal.emit("⚠️ FFMPEG 後端無法開啟串流，嘗試使用預設後端...")
            cap = cv2.VideoCapture(self.url)

        if not cap.isOpened():
            self.status_signal.emit("❌ OpenCV 無法開啟串流，請檢查 URL、編碼或防火牆設定")
            self.is_running = False
            return

        self.status_signal.emit("✅ 串流已連接")
        
        # 優化延遲
        try: cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        except: pass 
        
        fail_count = 0

        while self.is_running:
            ret, cv_img = cap.read()
            if ret:
                fail_count = 0
                
                # ========= [擴充區] AI 物體檢測邏輯 =========
                # if self.enable_ai:
                #     cv_img, detections = self.detector.detect(cv_img)
                # ==========================================

                # BGR -> RGB
                rgb_image = cv2.cvtColor(cv_img, cv2.COLOR_BGR2RGB)
                h, w, ch = rgb_image.shape
                
                # 轉換為 Qt 格式 (注意 .copy() 是必須的)
                qt_image = QImage(rgb_image.data, w, h, ch * w, QImage.Format_RGB888).copy()
                
                self.change_pixmap_signal.emit(qt_image)
            else:
                fail_count += 1
                if fail_count > 100:
                    self.status_signal.emit("⚠️ 訊號丟失，可能已中斷連線")
                    # 可以在此停止或嘗試重連
                    break
                self.msleep(10)
        
        cap.release()
        self.status_signal.emit("🔌 串流已關閉")

    def stop(self):
        self.is_running = False
        self.wait()