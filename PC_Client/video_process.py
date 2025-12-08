# ============================================ 
# PC_Client/video_process.py - MJPEG Optimized
# Uses custom MJPEGStreamReader for ESP32-CAM streams
# ============================================ 

import cv2 
import time 
import numpy as np 
from queue import Empty 
import sys
import os
import threading

# Import custom MJPEG reader and network utils
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mjpeg_reader import MJPEGStreamReader
from network_utils import SourceAddressAdapter

# Commands
CMD_SET_URL = "SET_URL"
CMD_SET_AI = "SET_AI"
CMD_SET_MODEL = "SET_MODEL"
CMD_EXIT = "EXIT"


def start_esp32_stream(esp32_ip):
    """Send command to ESP32 to start the stream server."""
    import requests
    try:
        url = f"http://{esp32_ip}/control"
        params = {'var': 'stream', 'val': '1'}
        resp = requests.get(url, params=params, timeout=3)
        if resp.status_code == 200:
            return True
    except Exception as e:
        pass
    return False

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
 
    # === CRITICAL: 在 multiprocessing 子進程中初始化 CUDA ===
    # Windows 使用 spawn 模式，子進程需要重新初始化 CUDA
    import torch
    if torch.cuda.is_available():
        try:
            torch.cuda.init()
            torch.cuda.set_device(0)
            log(f"✅ CUDA initialized in subprocess (Device: {torch.cuda.get_device_name(0)})")
        except Exception as e:
            log(f"⚠️ CUDA init failed in subprocess: {e}")
    else:
        log("⚠️ CUDA not available in subprocess")
    
    log("Started (MJPEG Optimized)")
     
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
     
    # Start MJPEG Stream Reader
    reader = None
    frame_count = 0
    last_stats_time = time.time()
    ai_frame_skip_counter = 0  # [OPTIMIZATION] Counter for AI frame skipping
    AI_PROCESS_EVERY_N_FRAMES = 5  # Process AI on 1 out of every 5 frames
    last_ai_result = None  # Cache last AI result (JPEG bytes)
    
    if video_url:
        try:
            # Create MJPEG reader optimized for ESP32-CAM
            reader = MJPEGStreamReader(
                url=video_url,
                source_ip=source_ip,  # Bind to specific network interface
                frame_queue_size=2,   # Small buffer = low latency
                chunk_size=16384,     # 16KB for better efficiency
                reconnect_delay=1.0,  # Faster initial reconnect
                max_reconnect_delay=30.0,
                connection_timeout=30,  # Longer timeout for ESP32
                log_callback=log
            )
            reader.start()
            log(f"✅ MJPEG Reader started: {video_url}")
        except Exception as e:
            log(f"❌ Failed to start reader: {e}")
            reader = None

    last_status_check = 0
    
    try:
        while True: 
            # 1. Process Commands (Non-blocking)
            try:
                while not cmd_queue.empty():
                    cmd, data = cmd_queue.get_nowait()

                    if cmd == CMD_EXIT:
                        if stream: stream.stop()
                        log("Video process exiting (CMD_EXIT)")
                        return

                    elif cmd == CMD_SET_URL:
                        new_url = data.get('url', '') if isinstance(data, dict) else data
                        video_url = new_url  # Update global url for reconnection logic
                        
                        # Restart reader with new URL
                        if reader:
                            reader.stop()
                        
                        try:
                            reader = MJPEGStreamReader(
                                url=new_url,
                                source_ip=source_ip,
                                frame_queue_size=2,
                                chunk_size=8192,
                                reconnect_delay=2.0,
                                max_reconnect_delay=30.0,
                                log_callback=log
                            )
                            reader.start()
                            log(f"Switched stream to {new_url}")
                        except Exception as e:
                            log(f"Failed to switch stream: {e}")
                            reader = None
                                
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
                            if enable_ai:
                                log(f"✅ AI enabled (processing 1/{AI_PROCESS_EVERY_N_FRAMES} frames)")
                            else:
                                log("AI disabled")

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
              
            # 3. Get Latest Frame from MJPEG Reader
            frame = None
            frame_bytes = None
            
            if reader:
                # Read JPEG bytes from reader (non-blocking)
                frame_bytes = reader.read(timeout=0.1)
                
                if frame_bytes:
                    # Decode JPEG bytes to numpy array
                    try:
                        nparr = np.frombuffer(frame_bytes, np.uint8)
                        frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                    except Exception as e:
                        log(f"Frame decode error: {e}")
                        frame = None
                    
                    # FPS Statistics
                    if frame is not None:
                        frame_count += 1
                        if frame_count % 100 == 0:
                            elapsed = time.time() - last_stats_time
                            fps = 100 / elapsed if elapsed > 0 else 0
                            log(f"📊 Stream FPS: {fps:.1f}")
                            last_stats_time = time.time()

            if frame is not None:
                final_frame = frame
                  
                # 4. AI Processing (Optimized with frame skipping)
                if detector and detector.enabled: 
                    ai_frame_skip_counter += 1
                    
                    # Only process AI on every Nth frame
                    if ai_frame_skip_counter >= AI_PROCESS_EVERY_N_FRAMES:
                        ai_frame_skip_counter = 0
                        try: 
                            # Process AI detection
                            annotated_frame, detections, control = detector.detect(frame) 
                            final_frame = annotated_frame 
                            
                            # 快取編碼後的 JPEG bytes（避免重複編碼）
                            ret, buffer = cv2.imencode('.jpg', annotated_frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
                            if ret:
                                last_ai_result = buffer.tobytes()
                        except Exception as e: 
                            log(f"AI Error: {e}") 
                    else:
                        # Use cached AI result (JPEG bytes) for frames we skip
                        if last_ai_result is not None:
                            # Send cached JPEG bytes directly - avoid re-encoding!
                            try:
                                if frame_queue.full():
                                    try: frame_queue.get_nowait()
                                    except Empty: pass
                                frame_queue.put(last_ai_result)
                                continue  # Skip normal encoding path
                            except:
                                pass
                  
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
    
    except KeyboardInterrupt:
        # Graceful shutdown on Ctrl+C
        log("Video process interrupted by user (Ctrl+C)")
        if reader:
            reader.stop()
        return