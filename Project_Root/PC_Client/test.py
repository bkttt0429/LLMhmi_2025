import cv2
import numpy as np
import sys
import os

# 確保可以匯入 ai_detector
sys.path.append(os.getcwd()) 

try:
    from ai_detector import ObjectDetector
except ImportError:
    print("❌ 找不到 ai_detector.py，請確保此測試檔案位於 PC_Client 資料夾內或與 ai_detector.py 同層級。")
    sys.exit(1)

def test_model():
    print("=== 開始 YOLO 模型測試 ===")
    
    # 1. 測試模型載入
    model_name = 'yolov13s.pt' # 使用您指定的模型名稱
    print(f"嘗試載入模型: {model_name}...")
    
    # 如果找不到 yolov13s.pt，會自動回退到 yolov8n.pt (根據您的 ai_detector.py 邏輯)
    detector = ObjectDetector(model_path=model_name)
    
    if not detector.enabled:
        print("❌ 模型載入失敗，測試終止。")
        return

    print(f"✅ 模型載入成功 (使用裝置: {detector.device})")

    # 2. 建立測試影像 (建立一個黑色背景的假影像)
    # 格式: (高度, 寬度, 通道數) -> (480, 640, 3)
    print("建立測試影像...")
    dummy_frame = np.zeros((480, 640, 3), dtype=np.uint8)
    
    # 畫一個白色矩形模擬物體，看能否避免全黑導致的異常 (雖然 YOLO 應該也能處理全黑)
    cv2.rectangle(dummy_frame, (100, 100), (300, 300), (255, 255, 255), -1)

    # 3. 執行偵測
    print("執行推論測試...")
    try:
        # detect 回傳: (影像, 偵測列表, (速度, 轉向))
        processed_frame, detections, (v, w) = detector.detect(dummy_frame)
        
        print("✅ 推論成功！")
        print(f"   - 偵測到的物體數量: {len(detections)}")
        print(f"   - 控制指令輸出: v={v:.2f}, w={w:.2f}")
        
        if len(detections) > 0:
            print("   - 偵測列表:", detections)
        else:
            print("   - (正常) 黑色測試影像中未偵測到標準物體")

    except Exception as e:
        print(f"❌ 推論執行時發生錯誤: {e}")
        import traceback
        traceback.print_exc()

    print("=== 測試結束 ===")

if __name__ == "__main__":
    test_model()