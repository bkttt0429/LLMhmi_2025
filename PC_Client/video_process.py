# ============================================
# PC_Client/video_process.py 優化版本
# 配合 ESP32-S3 優化後的 API
# ============================================

import cv2
import time
import requests
import numpy as np
from queue import Empty

# ⭐ 改進的 MJPEG 讀取器（支援重連與性能監控）
class MJPEGStreamReader:
    def __init__(self, url, timeout=5):
        self.url = url
        self.timeout = timeout
        self.stream = None
        self.bytes = b''
        self.connected = False
        self.frame_count = 0
        self.last_stats_time = time.time()
        self._connect()

    def _connect(self):
        """建立串流連線（含重試邏輯）"""
        try:
            # ⭐ 加入 Keep-Alive Header
            headers = {
                'Connection': 'keep-alive',
                'User-Agent': 'Python-Client/1.0'
            }
            self.stream = requests.get(
                self.url,
                stream=True,
                timeout=self.timeout,
                headers=headers
            )
            if self.stream.status_code == 200:
                self.connected = True
                print(f"[STREAM] Connected to {self.url}")
            else:
                self.connected = False
                print(f"[STREAM] HTTP {self.stream.status_code}")
        except Exception as e:
            self.connected = False
            print(f"[STREAM] Connection failed: {e}")

    def get_frame(self):
        """取得單幀（非阻塞）"""
        if not self.connected or not self.stream:
            self._connect()
            if not self.connected:
                return None

        try:
            # ⭐ 使用 iter_content 取代 raw.read（更穩定）
            for chunk in self.stream.iter_content(chunk_size=1024):
                if not chunk:
                    break

                self.bytes += chunk

                # 尋找 JPEG 邊界
                a = self.bytes.find(b'\xff\xd8')  # SOI
                b = self.bytes.find(b'\xff\xd9')  # EOI

                if a != -1 and b != -1 and b > a:
                    jpg = self.bytes[a:b+2]
                    self.bytes = self.bytes[b+2:]

                    # 解碼
                    frame = cv2.imdecode(
                        np.frombuffer(jpg, dtype=np.uint8),
                        cv2.IMREAD_COLOR
                    )

                    if frame is not None:
                        self.frame_count += 1

                        # 每 100 幀顯示統計
                        if self.frame_count % 100 == 0:
                            elapsed = time.time() - self.last_stats_time
                            fps = 100 / elapsed if elapsed > 0 else 0
                            print(f"[STREAM] FPS: {fps:.1f} | Frames: {self.frame_count}")
                            self.last_stats_time = time.time()

                        return frame

            return None

        except Exception as e:
            print(f"[STREAM] Error: {e}")
            self.connected = False
            return None

    def close(self):
        if self.stream:
            try:
                self.stream.close()
            except:
                pass
            self.stream = None


# ⭐ 新增：從 ESP32 查詢狀態
def query_esp32_status(ip):
    """查詢 ESP32-S3 的即時狀態"""
    try:
        resp = requests.get(f"http://{ip}/status", timeout=2)
        if resp.status_code == 200:
            data = resp.json()
            print(f"[ESP32] FPS: {data.get('fps', 0):.1f} | "
                  f"Heap: {data.get('heap', 0)} KB | "
                  f"PSRAM: {data.get('psram', 0)} KB")
            return data
    except:
        pass
    return None


# ⭐ 新增：動態調整 ESP32 設定
def adjust_esp32_settings(ip, quality=None, framesize=None):
    """
    動態調整 ESP32 相機設定

    quality: 10-63 (10=最佳)
    framesize:
        - 5  = FRAMESIZE_VGA (640x480)
        - 7  = FRAMESIZE_SVGA (800x600)
        - 10 = FRAMESIZE_XGA (1024x768)
    """
    params = {}
    if quality is not None:
        params['quality'] = quality
    if framesize is not None:
        params['framesize'] = framesize

    try:
        resp = requests.get(f"http://{ip}/settings", params=params, timeout=2)
        if resp.status_code == 200:
            print(f"[ESP32] Settings updated: {params}")
            return True
    except Exception as e:
        print(f"[ESP32] Settings update failed: {e}")
    return False


# ⭐ 優化後的主處理函數
def video_process_target(cmd_queue, frame_queue, log_queue, initial_config):
    """
    影像處理主程序（配合 ESP32-S3 優化）
    """
    def log(msg):
        try:
            log_queue.put(f"[VideoProcess] {msg}")
        except:
            pass

    log("Started (Optimized for ESP32-S3 N16R8)")

    video_url = initial_config.get('video_url', '')
    ai_enabled = initial_config.get('ai_enabled', False)
    esp32_ip = initial_config.get('camera_ip', '192.168.4.1')

    # 初始化 AI 偵測器（若需要）
    detector = None
    if ai_enabled:
        try:
            from ai_detector import ObjectDetector
            detector = ObjectDetector()
            detector.enabled = True
            log("AI Detector loaded")
        except Exception as e:
            log(f"AI init failed: {e}")

    stream_reader = None
    last_status_check = 0
    
    # State
    last_url = video_url

    while True:
        # 處理命令
        try:
            while not cmd_queue.empty():
                cmd, data = cmd_queue.get_nowait()
                if cmd == 'EXIT':
                    if stream_reader: stream_reader.close()
                    return
                elif cmd == 'SET_URL':
                    new_url = data.get('url', '') if isinstance(data, dict) else data
                    if new_url != last_url:
                        last_url = new_url
                        if stream_reader:
                            stream_reader.close()
                            stream_reader = None
                elif cmd == 'SET_AI':
                    if detector: detector.enabled = bool(data)
        except Empty:
            pass

        # 定期查詢 ESP32 狀態（每 10 秒）
        if time.time() - last_status_check > 10:
            # If we know the IP, or can derive it from URL
            if '192.168' in last_url:
                 try:
                     ip = last_url.split('//')[1].split(':')[0]
                     query_esp32_status(ip)
                 except:
                     query_esp32_status(esp32_ip)
            last_status_check = time.time()

        # 初始化串流讀取器
        if not stream_reader and last_url:
            stream_reader = MJPEGStreamReader(last_url)

        # 取得影像
        frame = None
        if stream_reader:
            frame = stream_reader.get_frame()

        if frame is not None:
            final_frame = frame

            # AI 處理
            if detector and detector.enabled:
                try:
                    annotated_frame, detections, control = detector.detect(frame)
                    final_frame = annotated_frame
                except Exception as e:
                    log(f"AI Error: {e}")

            # 編碼並發送
            try:
                ret, buffer = cv2.imencode('.jpg', final_frame,
                                          [cv2.IMWRITE_JPEG_QUALITY, 80])
                if ret:
                    if frame_queue.full():
                        try:
                            frame_queue.get_nowait()
                        except Empty:
                            pass
                    frame_queue.put(buffer.tobytes())
            except:
                pass
        else:
            time.sleep(0.01)


# ============================================
# 使用範例
# ============================================
if __name__ == "__main__":
    # 查詢狀態
    query_esp32_status("192.168.4.1")

    # 切換至高品質模式
    adjust_esp32_settings("192.168.4.1", quality=10, framesize=10)

    # 切換至高速模式
    adjust_esp32_settings("192.168.4.1", quality=15, framesize=5)