# ============================================ 
# PC_Client/video_process.py - VidGear Optimized
# Uses VidGear CamGear for high-performance streaming
# ============================================ 

import cv2 
import time 
from vidgear.gears import CamGear
import numpy as np 
from queue import Empty 
import sys
import os
import threading

# Import the SourceAddressAdapter from network_utils (kept for control requests)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from network_utils import SourceAddressAdapter

# Commands
CMD_SET_URL = "SET_URL"
CMD_SET_AI = "SET_AI"
CMD_SET_MODEL = "SET_MODEL"
CMD_EXIT = "EXIT"


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
 
    log("Started (VidGear Optimized)")
     
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
     
    # Start VidGear CamGear stream
    stream = None
    frame_count = 0
    last_stats_time = time.time()
    
    if video_url:
        try:
            # VidGear options for optimal performance
            options = {
                "THREADED_QUEUE_MODE": True,  # Enable threaded queue mode for better performance
            }
            stream = CamGear(source=video_url, logging=True, **options).start()
            log(f"VidGear stream started: {video_url}")
        except Exception as e:
            log(f"Failed to start VidGear stream: {e}")

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
                        
                        if stream:
                            stream.stop()
                        
                        try:
                            stream = CamGear(source=new_url, logging=True, **options).start()
                            log(f"Switched stream to {new_url}")
                        except Exception as e:
                            log(f"Failed to switch stream: {e}")
                                
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
              
            # 3. Get Latest Frame from VidGear
            frame = None
            if stream:
                frame = stream.read()
                
                # VidGear returns None when stream ends - try to reconnect
                if frame is None and video_url:
                    log("Stream ended, attempting reconnect...")
                    try:
                        stream.stop()
                        time.sleep(2)
                        stream = CamGear(source=video_url, logging=True, **options).start()
                        log("Reconnected successfully")
                    except Exception as e:
                        log(f"Reconnection failed: {e}")
                        time.sleep(5)  # Wait before next attempt
                    continue
                
                # FPS Statistics
                frame_count += 1
                if frame_count % 100 == 0:
                    elapsed = time.time() - last_stats_time
                    fps = 100 / elapsed if elapsed > 0 else 0
                    log(f"📊 Stream FPS: {fps:.1f}")
                    last_stats_time = time.time()

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
    
    except KeyboardInterrupt:
        # Graceful shutdown on Ctrl+C
        log("Video process interrupted by user (Ctrl+C)")
        if stream:
            stream.stop()
        return