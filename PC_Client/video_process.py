import cv2
import time
import queue
import requests
import numpy as np
import traceback
from queue import Empty
from ai_detector import ObjectDetector

# Commands
CMD_SET_URL = "SET_URL"
CMD_SET_AI = "SET_AI"
CMD_EXIT = "EXIT"

class MJPEGStreamReader:
    def __init__(self, url, timeout=5):
        self.url = url
        self.timeout = timeout
        self.stream = None
        self.bytes = b''
        self.connected = False
        self._connect()

    def _connect(self):
        try:
            self.stream = requests.get(self.url, stream=True, timeout=self.timeout)
            if self.stream.status_code == 200:
                self.connected = True
            else:
                self.connected = False
        except:
            self.connected = False

    def get_frame(self):
        if not self.connected or not self.stream:
            self._connect()
            if not self.connected:
                return None

        try:
            # Read chunks until we have a full JPEG
            # This is a simplified parser; for robustness we look for JPEG headers
            # SOI: FF D8, EOI: FF D9
            
            # Simple buffer management
            chunk = self.stream.raw.read(1024)
            if not chunk:
                self.connected = False
                return None
            
            self.bytes += chunk
            a = self.bytes.find(b'\xff\xd8')
            b = self.bytes.find(b'\xff\xd9')
            
            if a != -1 and b != -1:
                jpg = self.bytes[a:b+2]
                self.bytes = self.bytes[b+2:]
                
                # Decode
                frame = cv2.imdecode(np.frombuffer(jpg, dtype=np.uint8), cv2.IMREAD_COLOR)
                return frame
                
            return None
        except Exception:
            self.connected = False
            return None

    def close(self):
        if self.stream:
            try:
                self.stream.close()
            except:
                pass
            self.stream = None

def video_process_target(cmd_queue, frame_queue, log_queue, initial_config):
    """
    Main function for the Video Process.
    """
    def log(msg):
        try:
            log_queue.put(f"[VideoProcess] {msg}")
        except:
            pass

    log("Started.")
    
    video_url = initial_config.get('video_url', '')
    ai_enabled = initial_config.get('ai_enabled', False)
    
    detector = None
    try:
        detector = ObjectDetector()
        if ai_enabled:
            detector.enabled = True
    except Exception as e:
        log(f"AI Detector Init Failed: {e}")

    cap = None # For cv2.VideoCapture if needed (not used for MJPEG stream usually)
    stream_reader = None
    
    # State
    last_url = ""
    
    while True:
        # 1. Process Commands
        try:
            while not cmd_queue.empty():
                cmd, data = cmd_queue.get_nowait()
                
                if cmd == CMD_EXIT:
                    log("Exiting...")
                    if stream_reader: stream_reader.close()
                    return
                
                elif cmd == CMD_SET_URL:
                    new_url = data.get('url', '') if isinstance(data, dict) else data
                    if new_url != last_url:
                        log(f"Setting URL to {new_url}")
                        last_url = new_url
                        if stream_reader:
                            stream_reader.close()
                            stream_reader = None
                        
                        # If URL is a digit, use cv2.VideoCapture
                        if str(new_url).isdigit():
                             if cap: cap.release()
                             cap = cv2.VideoCapture(int(new_url))
                        else:
                             if cap: 
                                 cap.release()
                                 cap = None
                             stream_reader = MJPEGStreamReader(new_url)

                elif cmd == CMD_SET_AI:
                    ai_state = bool(data)
                    log(f"Setting AI to {ai_state}")
                    if detector:
                        detector.enabled = ai_state

        except Empty:
            pass
        except Exception as e:
            log(f"Command Error: {e}")

        # 2. Acquire Frame
        frame = None
        try:
            if cap and cap.isOpened():
                ret, img = cap.read()
                if ret:
                    frame = img
            elif stream_reader:
                frame = stream_reader.get_frame()
                
                # If stream reader fails repeatedly, maybe try to reconnect or backoff?
                # The Reader handles basic reconnect logic in get_frame but minimal.
        except Exception as e:
            # log(f"Capture Error: {e}")
            pass

        # 3. Process Frame
        if frame is not None:
            final_frame = frame
            
            # AI Detection
            if detector and detector.enabled:
                try:
                    annotated_frame, detections, control = detector.detect(frame)
                    final_frame = annotated_frame
                    # Potentially send control back via log or another queue if needed
                except Exception as e:
                    log(f"AI Error: {e}")

            # 4. Encode and Send
            try:
                # Resize if too large to save bandwidth? 
                # keep original for now.
                
                ret, buffer = cv2.imencode('.jpg', final_frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
                if ret:
                    # Clear old frames if full to avoid lag
                    if frame_queue.full():
                        try:
                            frame_queue.get_nowait()
                        except Empty:
                            pass
                    
                    frame_queue.put(buffer.tobytes())
            except Exception as e:
                pass
        else:
            # No frame acquired, sleep briefly to avoid spin loop
            time.sleep(0.01)

