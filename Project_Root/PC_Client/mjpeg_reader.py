import time
import requests
import threading
import cv2
import numpy as np
from network_utils import SourceAddressAdapter

class MJPEGStreamReader:
    def __init__(self, url, source_ip=None, timeout=5.0):
        self.url = url
        self.source_ip = source_ip
        self.timeout = timeout
        self.running = False
        self.thread = None
        self.lock = threading.Lock()
        self.current_frame = None
        self.last_frame_time = 0
        self.connected = False
        self.session = requests.Session()
        
        # Configure the session to use the specific source IP if provided
        if self.source_ip:
            adapter = SourceAddressAdapter(self.source_ip)
            self.session.mount('http://', adapter)
            self.session.mount('https://', adapter)

    def start(self):
        if self.running:
            return
        self.running = True
        self.thread = threading.Thread(target=self._update_loop, daemon=True)
        self.thread.start()

    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join(timeout=1.0)

    def get_frame(self):
        with self.lock:
            return self.current_frame, self.last_frame_time

    def is_connected(self):
        return self.connected

    def _update_loop(self):
        print(f"[MJPEG] Starting stream reader for {self.url} via {self.source_ip or 'default interface'}")
        
        while self.running:
            try:
                # Establish connection
                with self.session.get(self.url, stream=True, timeout=self.timeout) as response:
                    if response.status_code != 200:
                        print(f"[MJPEG] Failed to connect, status: {response.status_code}")
                        self.connected = False
                        time.sleep(2)
                        continue

                    self.connected = True
                    bytes_buffer = b''
                    
                    # Iterate over chunks
                    for chunk in response.iter_content(chunk_size=1024*32):
                        if not self.running:
                            break
                        
                        bytes_buffer += chunk
                        
                        # Find JPEG start/end markers
                        a = bytes_buffer.find(b'\xff\xd8') # Start of Image
                        b = bytes_buffer.find(b'\xff\xd9') # End of Image
                        
                        if a != -1 and b != -1:
                            jpg = bytes_buffer[a:b+2]
                            bytes_buffer = bytes_buffer[b+2:]
                            
                            # Decode frame
                            try:
                                frame = cv2.imdecode(np.frombuffer(jpg, dtype=np.uint8), cv2.IMREAD_COLOR)
                                if frame is not None:
                                    with self.lock:
                                        self.current_frame = frame
                                        self.last_frame_time = time.time()
                            except Exception as e:
                                print(f"[MJPEG] Decode error: {e}")
                                
            except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
                print(f"[MJPEG] Connection error: {e}")
                self.connected = False
                time.sleep(2)
            except Exception as e:
                print(f"[MJPEG] Unexpected error: {e}")
                self.connected = False
                time.sleep(2)
        
        print("[MJPEG] Thread stopped")
