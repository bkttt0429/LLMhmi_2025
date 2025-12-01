import cv2
import time
import queue
import logging
import multiprocessing
import numpy as np
import requests
import traceback
from queue import Empty, Full

# Assuming ai_detector.py is in the same directory and ObjectDetector class is available
# We need to import it here to use it in the process, but we must be careful about imports
# if this file is run directly.
try:
    from ai_detector import ObjectDetector
except ImportError:
    ObjectDetector = None

logger = logging.getLogger("VideoProcess")

def video_process_target(frame_queue, result_queue, control_queue, event_stop, camera_ip, ai_enabled_flag):
    """
    Main loop for the Video Processing Process.

    Args:
        frame_queue (multiprocessing.Queue): Queue to send display frames to Flask.
        result_queue (multiprocessing.Queue): Queue to send detection results/commands to Flask.
        control_queue (multiprocessing.Queue): Queue to receive settings from Flask.
        event_stop (multiprocessing.Event): Event to signal process termination.
        camera_ip (str): Initial Camera IP.
        ai_enabled_flag (multiprocessing.Value): Shared boolean for AI state.
    """
    logging.basicConfig(level=logging.INFO)
    logger.info("Video Process Started")

    stream_url = f"http://{camera_ip}:81/stream"
    cap = None
    detector = None

    # Initialize Object Detector if AI is enabled or available
    if ObjectDetector:
        try:
            detector = ObjectDetector()
            logger.info("YOLO Detector Initialized in Video Process")
        except Exception as e:
            logger.error(f"Failed to initialize YOLO: {e}")
            detector = None
    else:
        logger.warning("ObjectDetector class not found.")

    retry_count = 0
    max_retries = 5

    while not event_stop.is_set():
        # 1. Check control queue for updates (e.g., IP change)
        try:
            while not control_queue.empty():
                msg = control_queue.get_nowait()
                if msg.get('type') == 'set_ip':
                    new_ip = msg.get('ip')
                    if new_ip and new_ip != camera_ip:
                        camera_ip = new_ip
                        stream_url = f"http://{camera_ip}:81/stream"
                        logger.info(f"Switching Camera IP to {camera_ip}")
                        if cap:
                            cap.release()
                        cap = None
        except Exception:
            pass

        # 2. Connect to Camera if needed
        if cap is None or not cap.isOpened():
            logger.info(f"Connecting to stream: {stream_url}")
            try:
                # Use standard VideoCapture.
                # Note: In a real dual-NIC setup, we might need to bind to the specific interface.
                # However, OpenCV doesn't natively support binding to an interface easily.
                # Since the routing table should handle 192.168.4.x traffic, we rely on OS routing.
                cap = cv2.VideoCapture(stream_url, cv2.CAP_FFMPEG)
                if cap.isOpened():
                    logger.info("Stream Connected")
                    retry_count = 0
                else:
                    logger.warning("Stream connection failed")
                    retry_count += 1
                    time.sleep(2)
                    continue
            except Exception as e:
                logger.error(f"Connection error: {e}")
                time.sleep(2)
                continue

        # 3. Read Frame
        success, frame = cap.read()
        if not success:
            logger.warning("Failed to read frame")
            cap.release()
            cap = None
            time.sleep(1)
            continue

        # 4. AI Detection
        display_frame = frame.copy()
        cmd_result = None

        # Check shared value for AI State
        if ai_enabled_flag.value and detector and detector.enabled:
            try:
                # Assuming detect returns (annotated_frame, detections, control_cmd)
                # We need to verify what ObjectDetector.detect actually returns from ai_detector.py
                # Based on web_server.py memory: "frame, detections, control_cmd = result"
                result = detector.detect(frame)
                if isinstance(result, tuple) and len(result) == 3:
                    display_frame, detections, cmd_result = result

                    if cmd_result:
                        # Send command to Flask
                        try:
                            result_queue.put_nowait({"type": "command", "cmd": cmd_result})
                        except Full:
                            pass
            except Exception as e:
                logger.error(f"AI Detection Error: {e}")
                traceback.print_exc()

        # 5. Send Frame to Flask (for display)
        # We assume MJPEG, so we might want to encode it here to save bandwidth over IPC?
        # Or send raw frame. Raw frame (640x480x3 uint8) is ~900KB.
        # queue.put might be slow. Let's try sending raw for now.
        try:
            # Clear old frames if queue is full to reduce latency
            while not frame_queue.empty():
                try:
                    frame_queue.get_nowait()
                except Empty:
                    break

            frame_queue.put_nowait(display_frame)
        except Full:
            pass

        # Small sleep to yield? Not needed if blocking on read, but good practice.
        # cv2.VideoCapture.read() blocks until a frame is available.

    # Cleanup
    if cap:
        cap.release()
    logger.info("Video Process Terminated")
