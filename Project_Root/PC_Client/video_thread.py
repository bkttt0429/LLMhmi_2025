from PySide6.QtCore import QThread, Signal
from PySide6.QtGui import QImage
import cv2
import numpy as np
# 未來解鎖： from ai_detector import ObjectDetector

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
        print(f"嘗試連接串流: {self.url}")
        cap = cv2.VideoCapture(self.url)
        
        if not cap.isOpened():
            self.status_signal.emit("❌ OpenCV 無法開啟串流")
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
                    self.status_signal.emit("⚠️ 訊號丟失，重連中...")
                    fail_count = 0
                self.msleep(10)
        
        cap.release()

    def stop(self):
        self.is_running = False
        self.wait()