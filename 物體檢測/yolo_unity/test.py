import socket
import struct
import cv2
import numpy as np
from ultralytics import YOLO
import time
from datetime import datetime

# === 模型設定 ===
MODEL_PATH = "./yolov13s.pt"
DEVICE = "cuda"
#DEVICE = "cpu" 

# === 通訊設定 ===
HOST = "127.0.0.1"
PORT = 5000

# === 控制參數 ===
BASE_V = 0.6
MAX_W = 2.0
CONF_TH = 0.4
TARGET_CLASS = None

# === 優化參數 ===
ENABLE_DISPLAY = True
DISPLAY_INTERVAL = 3
USE_TRACKING = True
SHOW_FPS = True

# === 錄影參數 ===
ENABLE_RECORDING = True
RECORDING_FPS = 20
VIDEO_CODEC = 'mp4v'
VIDEO_EXT = '.mp4'
RECORD_WITH_ANNOTATIONS = True  # True=錄製標註框, False=錄製原始畫面

print("載入模型中...")
model = YOLO(MODEL_PATH)
print("模型載入完成。等待 Unity 連線...")

def recv_bytes(conn, n):
    data = b""
    while len(data) < n:
        packet = conn.recv(n - len(data))
        if not packet:
            return None
        data += packet
    return data

def decide_control(result, img_w, img_h):
    boxes = result.boxes
    if boxes is None or boxes.shape[0] == 0:
        return 0.3, 0.0

    xyxy = boxes.xyxy.cpu().numpy()
    cls = boxes.cls.cpu().numpy()
    conf = boxes.conf.cpu().numpy()

    best_box = None
    best_score = -1

    for (x1, y1, x2, y2), c, s in zip(xyxy, cls, conf):
        if s < CONF_TH:
            continue
        if TARGET_CLASS is not None and int(c) != TARGET_CLASS:
            continue

        area = (x2 - x1) * (y2 - y1)
        if area > best_score:
            best_score = area
            best_box = (x1, y1, x2, y2)

    if best_box is None:
        return 0.3, 0.0

    x1, y1, x2, y2 = best_box
    cx = 0.5 * (x1 + x2)
    cy = 0.5 * (y1 + y2)
    h = y2 - y1

    x_offset = (cx - img_w / 2) / (img_w / 2)
    size_ratio = h / img_h

    w = -x_offset * MAX_W
    v = BASE_V * max(0.0, 1.0 - size_ratio)

    if size_ratio > 0.6:
        v = 0.0

    return v, w


def main():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind((HOST, PORT))
    s.listen(1)

    conn, addr = s.accept()
    print("✅ Unity 已連線：", addr)

    # 初始化錄影
    video_writer = None
    video_filename = None
    video_initialized = False
    
    if ENABLE_RECORDING:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        video_filename = f"recording_{timestamp}{VIDEO_EXT}"
        print(f"📹 準備錄影：{video_filename}")

    # FPS 監控
    fps_time = time.time()
    fps_count = 0
    frame_count = 0

    try:
        while True:
            # 1) 收長度
            raw_len = recv_bytes(conn, 4)
            if not raw_len:
                print("連線中斷。")
                break
            frame_len = struct.unpack("I", raw_len)[0]

            # 2) 收影像
            jpg = recv_bytes(conn, frame_len)
            if jpg is None:
                print("影像接收失敗，中止。")
                break

            img = cv2.imdecode(np.frombuffer(jpg, dtype=np.uint8), cv2.IMREAD_COLOR)
            if img is None:
                print("解碼失敗，略過一幀。")
                continue

            h, w = img.shape[:2]

            # 3) 初始化錄影器（第一幀時）
            if ENABLE_RECORDING and not video_initialized:
                try:
                    fourcc = cv2.VideoWriter_fourcc(*VIDEO_CODEC)
                    video_writer = cv2.VideoWriter(video_filename, fourcc, RECORDING_FPS, (w, h))
                    if video_writer.isOpened():
                        print(f"✅ 錄影開始：{w}x{h} @ {RECORDING_FPS}fps")
                    else:
                        print("❌ 錄影器初始化失敗")
                        video_writer = None
                except Exception as e:
                    print(f"❌ 錄影器錯誤：{e}")
                    video_writer = None
                video_initialized = True

            # 4) YOLO 推論
            if USE_TRACKING:
                results = model.track(img, device=DEVICE, persist=True, conf=CONF_TH, verbose=False)
            else:
                results = model(img, device=DEVICE, conf=CONF_TH, verbose=False)
            result = results[0]

            # 5) 計算控制
            v, w_ang = decide_control(result, w, h)

            # 6) 準備顯示/錄影畫面
            frame_count += 1
            annotated = None
            
            # 如果需要顯示或錄製標註畫面，就生成標註
            if ENABLE_DISPLAY or (ENABLE_RECORDING and RECORD_WITH_ANNOTATIONS):
                if frame_count % DISPLAY_INTERVAL == 0 or (ENABLE_RECORDING and RECORD_WITH_ANNOTATIONS):
                    annotated = result.plot()
                    # 添加資訊文字
                    info_text = f"FPS: {fps_count} | v={v:.2f} w={w_ang:.2f}"
                    if ENABLE_RECORDING and video_writer is not None and video_writer.isOpened():
                        info_text += " | [REC]"
                    cv2.putText(annotated, info_text, 
                               (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)

            # 7) 錄影
            if ENABLE_RECORDING and video_writer is not None and video_writer.isOpened():
                if RECORD_WITH_ANNOTATIONS and annotated is not None:
                    video_writer.write(annotated)  # 錄製標註畫面
                else:
                    video_writer.write(img)  # 錄製原始畫面

            # 8) 顯示
            if ENABLE_DISPLAY and annotated is not None:
                cv2.imshow("YOLO Unity View", annotated)
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    break

            # 8) 傳回控制
            cmd = f"{v:.3f} {w_ang:.3f}\n"
            conn.sendall(cmd.encode("utf-8"))

            # 9) FPS 計算
            if SHOW_FPS:
                fps_count += 1
                if time.time() - fps_time >= 1.0:
                    print(f"FPS: {fps_count} | 控制: v={v:.2f}, w={w_ang:.2f}")
                    fps_count = 0
                    fps_time = time.time()

    except KeyboardInterrupt:
        print("\n⏹ 使用者中斷")
    except Exception as e:
        print(f"❌ 發生錯誤：{e}")
    finally:
        # 清理資源
        conn.close()
        s.close()
        
        # 釋放錄影器
        if video_writer is not None and video_writer.isOpened():
            video_writer.release()
            print(f"✅ 錄影已儲存：{video_filename}")
        
        if ENABLE_DISPLAY:
            cv2.destroyAllWindows()
        
        print("程式結束。")


if __name__ == "__main__":
    main()