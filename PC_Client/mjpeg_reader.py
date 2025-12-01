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
        
        bytes_buffer = b''
        MAX_BUFFER_SIZE = 1024 * 1024 * 2  # 2MB Buffer Limit
        
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
                        
                        # Prevent buffer overflow
                        if len(bytes_buffer) > MAX_BUFFER_SIZE:
                            # Too much garbage, reset buffer
                            bytes_buffer = b'' 
                            continue

                        # === Robust Parsing Logic ===
                        while True:
                            # 1. Find Start of Image (SOI)
                            start = bytes_buffer.find(b'\xff\xd8')
                            if start == -1:
                                # No start marker found.
                                # Keep the last few bytes just in case split happens exactly at the boundary
                                if len(bytes_buffer) > 2:
                                    bytes_buffer = bytes_buffer[-2:] 
                                break # Wait for more data
                            
                            # Discard junk before SOI
                            bytes_buffer = bytes_buffer[start:]
                            
                            # 2. Find End of Image (EOI)
                            end = bytes_buffer.find(b'\xff\xd9')
                            if end == -1:
                                break # Wait for more data (SOI found, but no EOI yet)
                            
                            # We have a candidate frame: bytes_buffer[0 : end+2]
                            
                            # Check if there are *multiple* frames in the buffer.
                            # To reduce latency ("Always Fresh"), we only care about the *last* complete frame.
                            
                            # Look for the LAST EOI in the buffer
                            last_end = bytes_buffer.rfind(b'\xff\xd9')
                            
                            if last_end != end:
                                # There is more than one EOI. We might have multiple frames.
                                # Let's try to extract the LAST frame.
                                
                                # Search backwards for the SOI corresponding to this last EOI
                                last_start = bytes_buffer.rfind(b'\xff\xd8', 0, last_end)
                                
                                if last_start != -1:
                                    # We found a pair (last_start, last_end)
                                    # This is the most recent frame available.
                                    # Discard everything before it.
                                    jpg = bytes_buffer[last_start : last_end + 2]
                                    bytes_buffer = bytes_buffer[last_end + 2:]
                                    
                                    # Decode this fresh frame
                                    self._decode_and_store(jpg)
                                    continue # Check loop again (buffer might still have partial data)
                            
                            # If we are here, we either have:
                            # A) Single frame at the start [0 : end+2]
                            # B) Multiple frames but we decided to process sequential (if logic above wasn't triggered)
                            # Actually, the logic above handles the skip.
                            # So here we process the standard single frame found at start.
                            
                            jpg = bytes_buffer[0 : end + 2]
                            bytes_buffer = bytes_buffer[end + 2:]
                            
                            self._decode_and_store(jpg)
                                
            except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
                print(f"[MJPEG] Connection error: {e}")
                self.connected = False
                time.sleep(2)
            except Exception as e:
                print(f"[MJPEG] Unexpected error: {e}")
                self.connected = False
                time.sleep(2)
        
        print("[MJPEG] Thread stopped")

    def _decode_and_store(self, jpg_data):
        if not jpg_data: 
            return

        try:
            # Verify basic JPEG structure (simple check)
            if not (jpg_data.startswith(b'\xff\xd8') and jpg_data.endswith(b'\xff\xd9')):
                return 

            # Decode
            frame = cv2.imdecode(np.frombuffer(jpg_data, dtype=np.uint8), cv2.IMREAD_COLOR)
            
            if frame is not None:
                with self.lock:
                    self.current_frame = frame
                    self.last_frame_time = time.time()
            else:
                # If decode fails, just ignore it. Do NOT print error to avoid spamming logs.
                pass
        except Exception:
            # Swallow exceptions to maintain stability and silence
            pass
