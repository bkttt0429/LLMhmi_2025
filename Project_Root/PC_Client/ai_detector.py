import cv2
import time
import numpy as np
import torch

# === CUDA 效能優化 ===
if torch.cuda.is_available():
    torch.backends.cudnn.benchmark = True  # 自動尋找最佳卷積演算法
    torch.backends.cudnn.deterministic = False  # 允許非確定性演算法以提升速度
    print("✅ CUDA cuDNN 加速已啟用")

# 嘗試匯入 YOLO
try:
    from ultralytics import YOLO
    YOLO_AVAILABLE = True
except ImportError:
    print("⚠️ 警告: 未安裝 ultralytics。請執行 'pip install ultralytics'")
    YOLO_AVAILABLE = False

class ObjectDetector:
    def __init__(self, model_path='./yolov8n.pt'):
        self.model = None
        self.enabled = False
        self.frame_count = 0
        self.total_inference_time = 0
        
        # === 裝置選擇與詳細資訊 ===
        self.device = self._select_device()
        
        # === 控制參數 ===
        self.base_v = 0.6          # 基礎速度
        self.max_w = 2.0           # 最大角速度
        self.conf_th = 0.4         # 信心度閾值
        self.target_class = None   # 目標類別 (None = 所有類別)
        
        # === 效能優化參數 ===
        self.skip_frames = 0       # 跳幀計數器 (0 = 每幀都處理)
        self.process_every_n = 1   # 每 N 幀處理一次 (1 = 不跳幀)
        self.input_size = 640      # YOLO 輸入尺寸 (320/640/1280)
        
        # === 模型載入 ===
        if YOLO_AVAILABLE:
            self._load_model(model_path)

    def _select_device(self):
        """智能選擇運算裝置"""
        if torch.cuda.is_available():
            device = 'cuda'
            gpu_name = torch.cuda.get_device_name(0)
            gpu_memory = torch.cuda.get_device_properties(0).total_memory / 1024**3
            compute_capability = torch.cuda.get_device_capability(0)
            
            print(f"🚀 AI Device: NVIDIA CUDA")
            print(f"   └─ GPU: {gpu_name}")
            print(f"   └─ VRAM: {gpu_memory:.1f} GB")
            print(f"   └─ CUDA Version: {torch.version.cuda}")
            print(f"   └─ Compute Capability: {compute_capability[0]}.{compute_capability[1]}")
            print(f"   └─ cuDNN Benchmark: {'Enabled' if torch.backends.cudnn.benchmark else 'Disabled'}")
            
            # 根據 VRAM 調整批次大小建議
            if gpu_memory < 4:
                print("   └─ ⚠️ 低 VRAM 檢測，建議使用 yolov8n.pt")
                self.input_size = 320
            elif gpu_memory >= 8:
                print("   └─ ✅ 充足 VRAM，可使用更大模型")
                self.input_size = 640
            
            # 清空 GPU 快取
            torch.cuda.empty_cache()
            print("   └─ GPU 快取已清空")
            
        elif torch.backends.mps.is_available():
            device = 'mps'
            print("🚀 AI Device: Apple Metal (MPS)")
            print("   └─ Optimized for Apple Silicon")
            
        else:
            device = 'cpu'
            print("⚠️ AI Device: CPU")
            print("   └─ 建議: 使用 GPU 以獲得更好效能")
            self.process_every_n = 2  # CPU 模式自動跳幀
            
        return device

    def _load_model(self, model_path):
        """載入 YOLO 模型"""
        print(f"\n[AI] 嘗試載入模型: {model_path}...")
        
        try:
            self.model = YOLO(model_path)
            self.model.to(self.device)  # 明確移動到目標裝置
            print(f"[AI] ✅ {model_path} 載入成功")
            self.enabled = True
            
            # 顯示模型資訊
            if hasattr(self.model, 'names'):
                print(f"[AI] 可偵測類別數: {len(self.model.names)}")
                print(f"[AI] 範例類別: {list(self.model.names.values())[:5]}...")
                
        except FileNotFoundError:
            print(f"[AI] ⚠️ {model_path} 不存在")
            print("[AI] 嘗試使用 yolov8n.pt (自動下載)...")
            try:
                self.model = YOLO('yolov8n.pt')
                self.model.to(self.device)
                self.enabled = True
                print("[AI] ✅ yolov8n.pt 載入成功")
            except Exception as e2:
                print(f"[AI] ❌ 無法載入備用模型: {e2}")
                
        except Exception as e:
            print(f"[AI] ❌ 載入失敗: {e}")
            print("[AI] 嘗試降級到 CPU...")
            try:
                self.device = 'cpu'
                self.model = YOLO(model_path)
                self.enabled = True
                print("[AI] ✅ CPU 模式載入成功")
            except:
                print("[AI] ❌ 嚴重錯誤：無法載入任何模型")

    def decide_control(self, result, img_w, img_h):
        """
        計算自動駕駛控制量
        
        Returns:
            (v, w): 線速度和角速度
        """
        boxes = result.boxes
        if boxes is None or len(boxes) == 0:
            return 0.0, 0.0

        # GPU -> CPU 轉換 (必要時)
        xyxy = boxes.xyxy.cpu().numpy() if boxes.xyxy.is_cuda else boxes.xyxy.numpy()
        cls = boxes.cls.cpu().numpy() if boxes.cls.is_cuda else boxes.cls.numpy()
        conf = boxes.conf.cpu().numpy() if boxes.conf.is_cuda else boxes.conf.numpy()

        # 尋找最佳目標 (面積最大 + 符合條件)
        best_box = None
        best_score = -1

        for (x1, y1, x2, y2), c, s in zip(xyxy, cls, conf):
            # 過濾條件
            if s < self.conf_th: 
                continue
            if self.target_class is not None and int(c) != self.target_class: 
                continue

            # 計算面積
            area = (x2 - x1) * (y2 - y1)
            if area > best_score:
                best_score = area
                best_box = (x1, y1, x2, y2)

        if best_box is None:
            return 0.0, 0.0

        # 計算控制量
        x1, y1, x2, y2 = best_box
        cx = 0.5 * (x1 + x2)  # 中心 X
        h = y2 - y1           # 高度

        # 正規化偏移量 [-1, 1]
        x_offset = (cx - img_w / 2) / (img_w / 2)
        
        # 物體大小比例
        size_ratio = h / img_h

        # 角速度控制 (根據 X 偏移)
        w = x_offset * self.max_w
        
        # 線速度控制 (物體越近越慢)
        v = self.base_v * max(0.0, 1.0 - size_ratio)
        
        # 緊急停止 (物體太近)
        if size_ratio > 0.6:
            v = 0.0

        return v, w

    def detect(self, frame):
        """
        核心偵測方法
        
        Args:
            frame: BGR 圖像 (numpy array)
            
        Returns:
            (annotated_frame, detections_list, control_cmd)
        """
        # 防呆檢查
        if not self.enabled or self.model is None:
            return frame, [], (0.0, 0.0)

        # 跳幀優化 (提升 FPS)
        self.skip_frames += 1
        if self.skip_frames < self.process_every_n:
            return frame, [], (0.0, 0.0)
        self.skip_frames = 0

        # === 開始推論 ===
        start_time = time.time()
        h, w_img = frame.shape[:2]
        
        try:
            # 1. YOLO 推論 (使用 track 模式保持 ID)
            results = self.model.track(
                frame, 
                device=self.device,
                persist=True,           # 保持追蹤 ID
                conf=self.conf_th,      # 信心度閾值
                verbose=False,          # 不顯示詳細 log
                imgsz=self.input_size,  # 輸入尺寸
                half=self.device=='cuda' # GPU 使用半精度加速
            )
            result = results[0]
            
            # 2. 繪製結果 (YOLO 內建最快)
            annotated_frame = result.plot()
            
            # 3. 計算控制指令
            v, ang_w = self.decide_control(result, w_img, h)
            
            # 4. 整理偵測資訊
            detections = []
            if result.boxes:
                for box in result.boxes:
                    try:
                        cls_id = int(box.cls[0].item())
                        conf = float(box.conf[0].item())
                        
                        # 安全獲取類別名稱
                        if hasattr(self.model, 'names') and cls_id in self.model.names:
                            cls_name = self.model.names[cls_id]
                        else:
                            cls_name = f"class_{cls_id}"
                        
                        detections.append({
                            "class": cls_name,
                            "confidence": conf,
                            "id": int(box.id[0].item()) if box.id is not None else -1
                        })
                    except Exception as e:
                        print(f"[AI] 解析偵測結果錯誤: {e}")
            
            # 5. 效能統計
            inference_time = time.time() - start_time
            self.frame_count += 1
            self.total_inference_time += inference_time
            
            fps = 1.0 / inference_time if inference_time > 0 else 0
            avg_fps = self.frame_count / self.total_inference_time if self.total_inference_time > 0 else 0
            
            # 6. 顯示 HUD
            info_lines = [
                f"FPS: {fps:.1f} (Avg: {avg_fps:.1f})",
                f"Device: {self.device.upper()}",
                f"Objects: {len(detections)}",
                f"Control: v={v:.2f} w={ang_w:.2f}"
            ]
            
            y_offset = 30
            for line in info_lines:
                cv2.putText(
                    annotated_frame, line, 
                    (10, y_offset), 
                    cv2.FONT_HERSHEY_SIMPLEX, 
                    0.6, (0, 255, 0), 2
                )
                y_offset += 25
            
            return annotated_frame, detections, (v, ang_w)
            
        except Exception as e:
            print(f"[AI] 推論錯誤: {e}")
            import traceback
            traceback.print_exc()
            return frame, [], (0.0, 0.0)

    def set_target_class(self, class_name):
        """設定追蹤目標類別"""
        if self.model and hasattr(self.model, 'names'):
            for idx, name in self.model.names.items():
                if name.lower() == class_name.lower():
                    self.target_class = idx
                    print(f"[AI] 目標設定為: {name} (ID: {idx})")
                    return True
        print(f"[AI] 找不到類別: {class_name}")
        return False
    
    def reset_target(self):
        """清除目標限制"""
        self.target_class = None
        print("[AI] 偵測所有類別")

    def get_stats(self):
        """獲取效能統計"""
        if self.frame_count == 0:
            return {"fps": 0, "frames": 0}
        
        avg_fps = self.frame_count / self.total_inference_time if self.total_inference_time > 0 else 0
        
        stats = {
            "fps": avg_fps,
            "frames": self.frame_count,
            "device": self.device,
            "model": str(self.model.model_name) if hasattr(self.model, 'model_name') else "unknown"
        }
        
        # GPU 專屬資訊
        if self.device == 'cuda' and torch.cuda.is_available():
            stats.update({
                "gpu_name": torch.cuda.get_device_name(0),
                "gpu_memory_allocated": f"{torch.cuda.memory_allocated(0) / 1024**2:.1f} MB",
                "gpu_memory_reserved": f"{torch.cuda.memory_reserved(0) / 1024**2:.1f} MB",
                "cudnn_benchmark": torch.backends.cudnn.benchmark
            })
        
        return stats
    
    def optimize_for_speed(self):
        """極速模式優化"""
        print("[AI] 🚀 啟用極速模式...")
        self.conf_th = 0.5  # 提高閾值減少誤檢
        self.input_size = 320  # 降低輸入解析度
        self.process_every_n = 1  # 不跳幀
        
        if self.device == 'cuda':
            torch.backends.cudnn.benchmark = True
            torch.backends.cudnn.deterministic = False
            print("[AI] ✅ CUDA 加速優化完成")
    
    def optimize_for_accuracy(self):
        """精確模式優化"""
        print("[AI] 🎯 啟用精確模式...")
        self.conf_th = 0.3  # 降低閾值提高召回率
        self.input_size = 640  # 提高輸入解析度
        self.process_every_n = 1  # 不跳幀
        print("[AI] ✅ 精確模式設定完成")