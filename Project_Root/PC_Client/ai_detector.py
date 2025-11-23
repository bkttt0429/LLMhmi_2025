import cv2
import numpy as np

class ObjectDetector:
    def __init__(self):
        # 這裡未來載入模型，例如 YOLOv8
        # self.model = YOLO("yolov8n.pt")
        print("AI 模型載入中...")

    def detect(self, image):
        """
        接收 OpenCV 影像，回傳繪製好框線的影像與檢測結果
        """
        # --- 模擬檢測邏輯 ---
        # 這裡未來會替換成真實的推論代碼
        # results = self.model(image)
        
        # 範例：畫一個固定的框框測試用
        h, w, _ = image.shape
        cv2.rectangle(image, (50, 50), (w-50, h-50), (0, 255, 0), 2)
        cv2.putText(image, "AI Detecting...", (60, 80), 
                   cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
        
        return image, "Person detected"