import cv2
import time
import numpy as np
import torch

# 嘗試匯入 YOLO
try:
    from ultralytics import YOLO
    YOLO_AVAILABLE = True
except ImportError:
    print("⚠️ 警告: 未安裝 ultralytics。請執行 'pip install ultralytics'")
    YOLO_AVAILABLE = False

class ObjectDetector:
    def __init__(self, model_path='yolov13s.pt'):
        self.model = None
        self.enabled = False
        
        # === 裝置選擇 (GPU 優先) ===
        if torch.cuda.is_available():
            self.device = 'cuda'
            print(f"🚀 AI Device: NVIDIA CUDA ({torch.cuda.get_device_name(0)})")
        elif torch.backends.mps.is_available():
            self.device = 'mps'
            print("🚀 AI Device: Apple MPS")
        else:
            self.device = 'cpu'
            print("⚠️ AI Device: CPU")

        # === 控制參數 ===
        self.base_v = 0.6
        self.max_w = 2.0
        self.conf_th = 0.4
        self.target_class = None 

        if YOLO_AVAILABLE:
            print(f"[AI] 嘗試載入模型: {model_path}...")
            try:
                self.model = YOLO(model_path)
                print(f"[AI] {model_path} 載入成功。")
                self.enabled = True
            except Exception as e:
                print(f"[AI] {model_path} 載入失敗: {e}")
                print("[AI] 嘗試降級使用 yolov8n.pt (自動下載)...")
                try:
                    self.model = YOLO('yolov8n.pt')
                    self.enabled = True
                    print("[AI] yolov8n.pt 載入成功。")
                except Exception as e2:
                    print(f"[AI] 嚴重錯誤：無法載入任何模型 ({e2})")

    def decide_control(self, result, img_w, img_h):
        """計算自動駕駛控制量 (v, w)"""
        boxes = result.boxes
        if boxes is None or len(boxes) == 0:
            return 0.0, 0.0

        # 取得 numpy array (如果是在 GPU 上，先轉 CPU)
        xyxy = boxes.xyxy.cpu().numpy()
        cls = boxes.cls.cpu().numpy()
        conf = boxes.conf.cpu().numpy()

        best_box = None
        best_score = -1

        for (x1, y1, x2, y2), c, s in zip(xyxy, cls, conf):
            if s < self.conf_th: continue
            if self.target_class is not None and int(c) != self.target_class: continue

            area = (x2 - x1) * (y2 - y1)
            if area > best_score:
                best_score = area
                best_box = (x1, y1, x2, y2)

        if best_box is None:
            return 0.0, 0.0

        x1, y1, x2, y2 = best_box
        cx = 0.5 * (x1 + x2)
        h = y2 - y1

        x_offset = (cx - img_w / 2) / (img_w / 2)
        size_ratio = h / img_h

        w = x_offset * self.max_w
        v = self.base_v * max(0.0, 1.0 - size_ratio)
        if size_ratio > 0.6: v = 0.0

        return v, w

    def detect(self, frame):
        """
        核心偵測方法
        回傳: (annotated_frame, detections_list, (v, w))
        """
        # 防呆：如果沒啟用或沒模型，原圖奉還
        if not self.enabled or self.model is None:
            return frame, [], (0.0, 0.0)

        start_time = time.time()
        h, w_img = frame.shape[:2]
        
        # 1. 推論 (Track 模式比較穩定)
        # persist=True 能保持 ID 追蹤，對影片串流很重要
        results = self.model.track(frame, device=self.device, persist=True, conf=self.conf_th, verbose=False)
        result = results[0]
        
        # 2. 繪圖 (YOLO 內建繪圖，速度最快)
        annotated_frame = result.plot()
        
        # 3. 計算控制
        v, ang_w = self.decide_control(result, w_img, h)

        # 4. 整理資訊列表
        detections = []
        if result.boxes:
            for box in result.boxes:
                try:
                    cls_id = int(box.cls[0])
                    # 確保 names 字典存在
                    if hasattr(self.model, 'names'):
                        cls_name = self.model.names[cls_id]
                    else:
                        cls_name = str(cls_id)
                    detections.append({"class": cls_name})
                except: pass

        # 5. 顯示資訊
        fps = 1.0 / (time.time() - start_time)
        info_text = f"FPS: {fps:.1f} | v={v:.2f} w={ang_w:.2f}"
        cv2.putText(annotated_frame, info_text, (10, 30), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)

        return annotated_frame, detections, (v, ang_w)