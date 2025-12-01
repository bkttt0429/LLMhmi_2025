import time
import cv2
import queue
import traceback
from multiprocessing import Queue
from mjpeg_reader import MJPEGStreamReader
from ai_detector import ObjectDetector

# Commands
CMD_SET_URL = "SET_URL"
CMD_SET_AI = "SET_AI"
CMD_EXIT = "EXIT"

def video_process_target(cmd_queue, frame_queue, log_queue, initial_config):
    """
    Separate process for Video Streaming and AI Detection.
    """

    # Setup Logging helper
    def log(msg):
        try:
            log_queue.put(msg)
        except:
            pass

    log("[PROC] Video Process Started")

    # Initialize State
    video_url = initial_config.get('video_url', None)
    camera_net_ip = initial_config.get('camera_net_ip', None)
    ai_enabled = initial_config.get('ai_enabled', False)

    detector = None
    stream_reader = None

    # Placeholder frame
    placeholder_frame = None

    try:
        while True:
            # 1. Process Commands
            try:
                while not cmd_queue.empty():
                    cmd_type, cmd_data = cmd_queue.get_nowait()

                    if cmd_type == CMD_EXIT:
                        log("[PROC] Exiting...")
                        if stream_reader: stream_reader.stop()
                        return

                    elif cmd_type == CMD_SET_URL:
                        new_url = cmd_data.get('url')
                        new_src_ip = cmd_data.get('source_ip')

                        if new_url != video_url or new_src_ip != camera_net_ip:
                            log(f"[PROC] Updating URL: {new_url}")
                            video_url = new_url
                            camera_net_ip = new_src_ip

                            # Restart Stream Reader
                            if stream_reader:
                                stream_reader.stop()

                            if video_url:
                                stream_reader = MJPEGStreamReader(video_url, source_ip=camera_net_ip)
                                stream_reader.start()

                    elif cmd_type == CMD_SET_AI:
                        should_enable = cmd_data
                        if should_enable and not ai_enabled:
                            log("[PROC] Enabling AI...")
                            if detector is None:
                                try:
                                    detector = ObjectDetector()
                                    if not detector.enabled:
                                        log("[PROC] Failed to initialize AI")
                                        detector = None
                                    else:
                                        ai_enabled = True
                                        log("[PROC] AI Enabled")
                                except Exception as e:
                                    log(f"[PROC] AI Init Error: {e}")
                            else:
                                ai_enabled = True
                                log("[PROC] AI Enabled")
                        elif not should_enable and ai_enabled:
                            log("[PROC] Disabling AI")
                            ai_enabled = False

            except queue.Empty:
                pass

            # 2. Frame Processing
            frame = None
            if stream_reader and stream_reader.is_connected():
                frame, _ = stream_reader.get_frame()

            if frame is not None:
                # AI Detection
                if ai_enabled and detector:
                    try:
                        # detect returns: annotated_frame, detections, control_cmd
                        # We only care about the annotated frame for now
                        result = detector.detect(frame)
                        if isinstance(result, tuple) and len(result) >= 1:
                            frame = result[0]
                    except Exception as e:
                        log(f"[PROC] AI Error: {e}")

                # Encode to JPEG
                try:
                    # Quality 85 matches web_server.py
                    ret, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
                    if ret:
                        jpg_bytes = buffer.tobytes()

                        # Clear old frames if queue is backing up to ensure low latency
                        while not frame_queue.empty():
                            try:
                                frame_queue.get_nowait()
                            except queue.Empty:
                                break

                        frame_queue.put(jpg_bytes)
                except Exception as e:
                    log(f"[PROC] Encode Error: {e}")

            else:
                # No frame available, small sleep to prevent CPU spin
                time.sleep(0.01)

    except Exception as e:
        log(f"[PROC] Critical Error: {traceback.format_exc()}")
    finally:
        if stream_reader:
            stream_reader.stop()
