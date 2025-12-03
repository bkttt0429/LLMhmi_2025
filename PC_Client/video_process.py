# ============================================
# PC_Client/video_process.py Optimized Version
# Adapted for ESP32-S3 Optimized API
# ============================================

import cv2
import time
import requests
import numpy as np
from queue import Empty

# Improved MJPEG Reader (Supports Reconnection and Performance Monitoring)
class MJPEGStreamReader:
    def __init__(self, url, timeout=10):  # Increased timeout
        self.url = url
        self.timeout = timeout
        self.stream = None
        self.bytes = b''
        self.connected = False
        self.frame_count = 0
        self.last_stats_time = time.time()
        self.retry_count = 0
        self.max_retries = 3
        self._connect()

    def _connect(self):
        """Establish stream connection (with retry logic)"""
        try:
            # Fix 1: Correct Headers
            headers = {
                'Connection': 'keep-alive',
                'User-Agent': 'Python-MJPEG-Client/1.0',
                'Accept': 'multipart/x-mixed-replace',
                'Cache-Control': 'no-cache'
            }

            print(f"[STREAM] Connecting to {self.url}...")

            # Fix 2: Use stream=True and increased timeout
            self.stream = requests.get(
                self.url,
                stream=True,
                timeout=self.timeout,
                headers=headers,
                allow_redirects=True
            )

            if self.stream.status_code == 200:
                self.connected = True
                self.retry_count = 0
                print(f"[STREAM] ✅ Connected (Status: {self.stream.status_code})")
                print(f"[STREAM] Content-Type: {self.stream.headers.get('Content-Type', 'Unknown')}")
            else:
                self.connected = False
                print(f"[STREAM] ❌ HTTP {self.stream.status_code}")

        except requests.exceptions.Timeout:
            self.connected = False
            print(f"[STREAM] ⏱️ Connection timeout")

        except requests.exceptions.ConnectionError as e:
            self.connected = False
            print(f"[STREAM] ❌ Connection error: {e}")

        except Exception as e:
            self.connected = False
            print(f"[STREAM] ❌ Unexpected error: {e}")

    def get_frame(self):
        """Get single frame (improved)"""
        if not self.connected or not self.stream:
            # Retry connection
            if self.retry_count < self.max_retries:
                self.retry_count += 1
                print(f"[STREAM] Retry {self.retry_count}/{self.max_retries}...")
                time.sleep(1)
                self._connect()

            if not self.connected:
                return None

        try:
            # Fix 3: Use smaller chunk_size to reduce latency
            chunk_size = 1024

            for chunk in self.stream.iter_content(chunk_size=chunk_size):
                if not chunk:
                    print("[STREAM] Empty chunk received")
                    self.connected = False
                    return None

                self.bytes += chunk

                # Find JPEG boundary (looser matching)
                a = self.bytes.find(b'\xff\xd8')  # SOI
                b = self.bytes.find(b'\xff\xd9')  # EOI

                if a != -1 and b != -1 and b > a:
                    jpg = self.bytes[a:b+2]
                    self.bytes = self.bytes[b+2:]

                    # Decode
                    frame = cv2.imdecode(
                        np.frombuffer(jpg, dtype=np.uint8),
                        cv2.IMREAD_COLOR
                    )

                    if frame is not None:
                        self.frame_count += 1
                        self.retry_count = 0  # Reset retry count

                        # Show stats every 100 frames
                        if self.frame_count % 100 == 0:
                            elapsed = time.time() - self.last_stats_time
                            fps = 100 / elapsed if elapsed > 0 else 0
                            print(f"[STREAM] FPS: {fps:.1f} | Frames: {self.frame_count}")
                            self.last_stats_time = time.time()

                        return frame
                    else:
                        print("[STREAM] Failed to decode JPEG")

                # Fix 4: Limit buffer size to prevent memory overflow
                if len(self.bytes) > 1024 * 1024:  # 1MB
                    print("[STREAM] Buffer overflow, resetting...")
                    self.bytes = self.bytes[-1024:]  # Keep only last 1KB

            # If iter_content ends, connection closed
            print("[STREAM] Stream ended by server")
            self.connected = False
            return None

        except requests.exceptions.ChunkedEncodingError:
            print("[STREAM] Chunked encoding error, reconnecting...")
            self.connected = False
            return None

        except Exception as e:
            print(f"[STREAM] Error: {e}")
            self.connected = False
            return None

    def close(self):
        if self.stream:
            try:
                self.stream.close()
                print("[STREAM] Connection closed")
            except:
                pass
            self.stream = None
        self.connected = False


# Query ESP32 Status
def query_esp32_status(ip):
    """Query ESP32-S3 real-time status"""
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


# Dynamic ESP32 Settings Adjustment
def adjust_esp32_settings(ip, quality=None, framesize=None):
    """
    Dynamically adjust ESP32 camera settings

    quality: 10-63 (10=Best)
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


# Fix 5: Improved video_process_target
def video_process_target(cmd_queue, frame_queue, log_queue, initial_config):
    def log(msg):
        try:
            log_queue.put(f"[VideoProcess] {msg}")
        except:
            pass

    log("Started (Optimized for ESP32-S3 N16R8)")

    video_url = initial_config.get('video_url', '')
    ai_enabled = initial_config.get('ai_enabled', False)

    # AI Detector (Optional)
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
    last_url = video_url
    consecutive_failures = 0
    max_failures = 10

    while True:
        # Process commands
        try:
            while not cmd_queue.empty():
                cmd, data = cmd_queue.get_nowait()
                if cmd == 'EXIT':
                    if stream_reader:
                        stream_reader.close()
                    return
                elif cmd == 'SET_URL':
                    new_url = data.get('url', '') if isinstance(data, dict) else data
                    if new_url != last_url:
                        log(f"URL changed to {new_url}")
                        last_url = new_url
                        if stream_reader:
                            stream_reader.close()
                            stream_reader = None
                        consecutive_failures = 0
                elif cmd == 'SET_AI':
                    if detector:
                        detector.enabled = bool(data)
        except:
            pass

        # Initialize stream reader
        if not stream_reader and last_url:
            log(f"Creating stream reader for {last_url}")
            stream_reader = MJPEGStreamReader(last_url, timeout=10)

        # Get frame
        frame = None
        if stream_reader:
            frame = stream_reader.get_frame()

            if frame is None:
                consecutive_failures += 1
                if consecutive_failures >= max_failures:
                    log(f"Too many failures ({max_failures}), restarting stream...")
                    stream_reader.close()
                    stream_reader = None
                    consecutive_failures = 0
                    time.sleep(2)  # Wait before retry
                else:
                    time.sleep(0.1)
                continue
            else:
                consecutive_failures = 0

        if frame is not None:
            final_frame = frame

            # AI Processing
            if detector and detector.enabled:
                try:
                    annotated_frame, detections, control = detector.detect(frame)
                    final_frame = annotated_frame
                except Exception as e:
                    log(f"AI Error: {e}")

            # Encode and send
            try:
                ret, buffer = cv2.imencode('.jpg', final_frame,
                                          [cv2.IMWRITE_JPEG_QUALITY, 80])
                if ret:
                    # Clear old frames
                    while not frame_queue.empty():
                        try:
                            frame_queue.get_nowait()
                        except:
                            break

                    frame_queue.put(buffer.tobytes())
            except Exception as e:
                log(f"Encode error: {e}")
        else:
            time.sleep(0.01)


# ============================================
# Usage Example
# ============================================
if __name__ == "__main__":
    # Query Status
    query_esp32_status("192.168.4.1")

    # Switch to High Quality Mode
    adjust_esp32_settings("192.168.4.1", quality=10, framesize=10)

    # Switch to High Speed Mode
    adjust_esp32_settings("192.168.4.1", quality=15, framesize=5)
