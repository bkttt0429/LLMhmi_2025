# ============================================ 
# PC_Client/video_process.py Threaded Version
# Decouples Frame Reading (Thread) from AI (Main Loop)
# ============================================ 

import cv2 
import time 
import requests 
import numpy as np 
from queue import Empty 
import sys
import os
import threading

# Import the SourceAddressAdapter from network_utils
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from network_utils import SourceAddressAdapter

# Commands
CMD_SET_URL = "SET_URL"
CMD_SET_AI = "SET_AI"
CMD_SET_MODEL = "SET_MODEL"
CMD_EXIT = "EXIT"

class MJPEGStreamReader:
    def __init__(self, url, timeout=10, source_ip=None):
        """
        Threaded MJPEG Stream Reader
        
        Args:
            url: Stream URL (e.g., http://10.243.115.133:81/stream)
            timeout: Connection timeout in seconds
            source_ip: Source IP address to bind the connection to
        """
        self.url = url
        self.timeout = timeout
        self.source_ip = source_ip
        self.stream = None
        self.bytes = b''
        self.connected = False
        self.frame_count = 0
        self.last_stats_time = time.time()
        self.connection_attempts = 0
        self.max_reconnect_attempts = 5
        self.reconnect_delay = 2.0
        
        # Threading
        self.running = False
        self.thread = None
        self.lock = threading.Lock()
        self.latest_frame = None
        self.new_frame_event = threading.Event()

        # Session
        self.session = requests.Session()
        # if self.source_ip:
        #     self.session.mount('http://', SourceAddressAdapter(self.source_ip))
        #     self.session.mount('https://', SourceAddressAdapter(self.source_ip))
        #     print(f"[STREAM] Binding to source interface: {self.source_ip}")

        self.start()

    def start(self):
        if self.running: return
        self.running = True
        self.thread = threading.Thread(target=self._update_loop, daemon=True)
        self.thread.start()
        print(f"[STREAM] Background reader started for {self.url}")

    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join(timeout=2.0)
        self._close_stream()
        print("[STREAM] Background reader stopped")

    def _close_stream(self):
        if self.stream:
            try:
                self.stream.close()
            except:
                pass
            self.stream = None
        self.connected = False

    def _connect(self):
        """Establish stream connection"""
        self.connection_attempts += 1
        if self.connection_attempts > self.max_reconnect_attempts:
            time.sleep(self.reconnect_delay)
            self.connection_attempts = 0

        try:
            headers = {
                'Connection': 'keep-alive',
                'User-Agent': 'Python-MJPEG-Client/Threaded',
                'Accept': 'multipart/x-mixed-replace',
                'Cache-Control': 'no-cache'
            }

            # Close old stream if exists
            self._close_stream()

            print(f"[STREAM] Connecting to {self.url}...")
            self.stream = self.session.get(
                self.url,
                stream=True,
                timeout=self.timeout,
                headers=headers,
                allow_redirects=True,
                verify=False
            )

            if self.stream.status_code == 200:
                self.connected = True
                self.connection_attempts = 0
                print(f"[STREAM] ✅ Connected to {self.url}")
                return self.stream.iter_content(chunk_size=4096)
            else:
                print(f"[STREAM] ❌ HTTP {self.stream.status_code}")
                self.connected = False
                return None

        except Exception as e:
            print(f"[STREAM] Connection error: {e}")
            self.connected = False
            return None

    def _update_loop(self):
        """Background thread loop to continuously read frames"""
        iterator = None

        while self.running:
            if not self.connected or iterator is None:
                iterator = self._connect()
                if not self.connected:
                    time.sleep(1.0)
                    continue

            try:
                # Read chunk
                try:
                    chunk = next(iterator)
                    self.bytes += chunk
                except StopIteration:
                    print("[STREAM] Stream ended, reconnecting...")
                    self.connected = False
                    iterator = None
                    continue
                except Exception as e:
                    print(f"[STREAM] Read error: {e}")
                    self.connected = False
                    iterator = None
                    continue

                # Find JPEG markers
                while True:
                    a = self.bytes.find(b'\xff\xd8')
                    if a == -1:
                        # No start marker, keep last few bytes just in case, discard rest to save memory
                        if len(self.bytes) > 65536:
                            self.bytes = self.bytes[-4096:]
                        break
                    
                    # Discard data before start marker
                    if a > 0:
                        self.bytes = self.bytes[a:]
                        a = 0
                    
                    b = self.bytes.find(b'\xff\xd9')
                    if b == -1:
                        # Start found but no end yet, wait for more data
                        break
                        
                    # We have a full frame candidate
                    jpg = self.bytes[a:b+2]
                    self.bytes = self.bytes[b+2:]
                    
                    # Decode
                    try:
                        frame = cv2.imdecode(np.frombuffer(jpg, dtype=np.uint8), cv2.IMREAD_COLOR)
                        if frame is not None:
                            with self.lock:
                                self.latest_frame = frame
                            self.new_frame_event.set()

                            self.frame_count += 1
                            if self.frame_count % 100 == 0:
                                elapsed = time.time() - self.last_stats_time
                                fps = 100 / elapsed if elapsed > 0 else 0
                                print(f"[STREAM] 📊 Cam FPS: {fps:.1f}")
                                self.last_stats_time = time.time()
                    except Exception as e:
                        print(f"[STREAM] Decode error: {e}")

            except Exception as e:
                print(f"[STREAM] Critical loop error: {e}")
                time.sleep(1.0)

    def read(self):
        """Get the latest frame (Non-blocking)"""
        with self.lock:
            return self.latest_frame if self.latest_frame is not None else None

    def is_connected(self):
        return self.connected


def query_esp32_status(ip): 
    """Query ESP32-S3 Real-time Status""" 
    try: 
        resp = requests.get(f"http://{ip}/status", timeout=2) 
        if resp.status_code == 200: 
            data = resp.json() 
            # Simplified log to avoid clutter
            return data 
    except: 
        pass 
    return None 
 
 
def adjust_esp32_settings(ip, quality=None, framesize=None): 
    settings = {}
    if quality is not None: settings['quality'] = quality
    if framesize is not None: settings['framesize'] = framesize
    for var, val in settings.items():
        try:
            requests.get(f"http://{ip}/control", params={'var': var, 'val': val}, timeout=2)
        except:
            pass
    return True
 
 
def video_process_target(cmd_queue, frame_queue, log_queue, initial_config):
    """ 
    Video Process Main Loop (Threaded Reader + AI)
    """ 
    def log(msg): 
        try: log_queue.put(f"[VideoProcess] {msg}")
        except: pass
 
    log("Started (Optimized: Threaded Reader + Async AI)")
     
    video_url = initial_config.get('url', '')
    ai_enabled = initial_config.get('ai_enabled', False) 
    esp32_ip = initial_config.get('camera_ip', '192.168.4.1')
    source_ip = initial_config.get('camera_net_ip', None)
    
    # Init AI
    detector = None 
    if ai_enabled: 
        try: 
            from ai_detector import ObjectDetector 
            detector = ObjectDetector() 
            detector.enabled = True 
            log("AI Detector loaded") 
        except Exception as e: 
            log(f"AI init failed: {e}") 
     
    # Start Reader Thread
    stream_reader = None
    if video_url:
        stream_reader = MJPEGStreamReader(video_url, source_ip=source_ip)

    last_status_check = 0
    
    while True: 
        # 1. Process Commands (Non-blocking)
        try:
            while not cmd_queue.empty():
                cmd, data = cmd_queue.get_nowait()

                if cmd == CMD_EXIT:
                    if stream_reader: stream_reader.stop()
                    return

                elif cmd == CMD_SET_URL:
                    new_url = data.get('url', '') if isinstance(data, dict) else data
                    new_source = data.get('source_ip', None) if isinstance(data, dict) else None
                    
                    if stream_reader:
                        stream_reader.stop()
                    stream_reader = MJPEGStreamReader(new_url, source_ip=new_source)
                    log(f"Switched stream to {new_url}")
                            
                elif cmd == CMD_SET_AI:
                    enable_ai = bool(data)
                    if enable_ai and detector is None:
                        try:
                            from ai_detector import ObjectDetector
                            detector = ObjectDetector()
                            log("AI Detector lazy loaded")
                        except Exception as e:
                            log(f"AI lazy load failed: {e}")
                            detector = None
                    if detector:
                        detector.enabled = enable_ai

                elif cmd == CMD_SET_MODEL:
                    # data should be {'model': 'path/to/model.pt'}
                    model_path = data.get('model')
                    if detector and model_path:
                        log(f"Switching AI model to: {model_path}")
                        detector.load_model(model_path)
                    elif not detector and model_path:
                        # Init detector if not exists
                        try:
                            from ai_detector import ObjectDetector
                            detector = ObjectDetector(model_path=model_path)
                            detector.enabled = True
                            log(f"AI Detector initialized with {model_path}")
                        except Exception as e:
                            log(f"AI init failed: {e}")

        except Empty:
            pass

        # 2. Status Check (Removed to prevent blocking video loop)
        # if time.time() - last_status_check > 10: 
        #     target_ip = esp32_ip
        #     if stream_reader and stream_reader.url:
        #          try:
        #              parsed = stream_reader.url.split('//')[1].split(':')[0]
        #              if parsed: target_ip = parsed
        #          except: pass
        #     # query_esp32_status(target_ip) # This was blocking!
        #     last_status_check = time.time() 
         
        # 3. Get Latest Frame (Instant)
        frame = None
        if stream_reader:
            frame = stream_reader.read()

        if frame is not None:
            final_frame = frame
             
            # 4. AI Processing (May take time, but reader thread keeps buffer empty)
            if detector and detector.enabled: 
                try: 
                    # Note: detector.detect() is synchronous and might slow down THIS loop,
                    # but the reader thread continues to drain the socket, preventing "lag/corruption".
                    annotated_frame, detections, control = detector.detect(frame) 
                    final_frame = annotated_frame 
                except Exception as e: 
                    log(f"AI Error: {e}") 
             
            # 5. Send to Web (Queue)
            try: 
                ret, buffer = cv2.imencode('.jpg', final_frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
                if ret: 
                    if frame_queue.full(): 
                        try: frame_queue.get_nowait()
                        except Empty: pass
                    frame_queue.put(buffer.tobytes()) 
            except:
                pass
        else:
            time.sleep(0.01) # Prevent CPU spin if no frame yet