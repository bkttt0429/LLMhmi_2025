# ============================================ 
# PC_Client/video_process.py Optimized Version
# Compatible with ESP32-S3 Optimized API
# ============================================ 
 
import cv2 
import time 
import requests 
import numpy as np 
from queue import Empty 

# Commands (Restored for compatibility with web_server.py)
CMD_SET_URL = "SET_URL"
CMD_SET_AI = "SET_AI"
CMD_EXIT = "EXIT"
 
# Improved MJPEG Reader (Supports Reconnect & Stats)
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
        """Establish stream connection (with retry logic)""" 
        try: 
            # Add Keep-Alive Header
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
        """Get single frame (non-blocking)""" 
        if not self.connected or not self.stream: 
            self._connect() 
            if not self.connected: 
                return None 
 
        try: 
            # Use iter_content instead of raw.read (More stable)
            for chunk in self.stream.iter_content(chunk_size=1024): 
                if not chunk: 
                    break 
                 
                self.bytes += chunk 
                 
                # Find JPEG Boundary
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
                         
                        # Show stats every 100 frames
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
 
 
# New: Query Status from ESP32
def query_esp32_status(ip): 
    """Query ESP32-S3 Real-time Status""" 
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
 
 
# New: Dynamic ESP32 Settings Adjustment
def adjust_esp32_settings(ip, quality=None, framesize=None): 
    """ 
    Dynamically adjust ESP32 Camera Settings 
     
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
 
 
# Main Process Function (Optimized)
def video_process_target(cmd_queue, frame_queue, log_queue, initial_config): 
    """ 
    Video Process Main Loop (Optimized for ESP32-S3) 
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
     
    # Init AI Detector (if needed)
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
        # Process Commands
        try:
            while not cmd_queue.empty():
                cmd, data = cmd_queue.get_nowait()
                if cmd == CMD_EXIT:
                    if stream_reader: stream_reader.close()
                    return
                elif cmd == CMD_SET_URL:
                    new_url = data.get('url', '') if isinstance(data, dict) else data
                    if new_url != last_url:
                        last_url = new_url
                        if stream_reader:
                            stream_reader.close()
                            stream_reader = None
                elif cmd == CMD_SET_AI:
                    if detector: detector.enabled = bool(data)
        except Empty:
            pass

        # Periodically Query ESP32 Status (Every 10s) 
        if time.time() - last_status_check > 10: 
            # If we know the IP, or can derive it from URL
            if '192.168' in last_url:
                 try:
                     ip = last_url.split('//')[1].split(':')[0]
                     query_esp32_status(ip)
                 except:
                     query_esp32_status(esp32_ip)
            last_status_check = time.time() 
         
        # Init Stream Reader 
        if not stream_reader and last_url: 
            stream_reader = MJPEGStreamReader(last_url) 
         
        # Acquire Frame 
        frame = None 
        if stream_reader: 
            frame = stream_reader.get_frame() 
         
        if frame is not None: 
            final_frame = frame 
             
            # AI Processing 
            if detector and detector.enabled: 
                try: 
                    annotated_frame, detections, control = detector.detect(frame) 
                    final_frame = annotated_frame 
                except Exception as e: 
                    log(f"AI Error: {e}") 
             
            # Encode and Send 
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
# Usage Example 
# ============================================ 
if __name__ == "__main__": 
    # Query Status 
    query_esp32_status("192.168.4.1") 
     
    # Switch to High Quality Mode 
    adjust_esp32_settings("192.168.4.1", quality=10, framesize=10) 
     
    # Switch to High Speed Mode 
    adjust_esp32_settings("192.168.4.1", quality=15, framesize=5)