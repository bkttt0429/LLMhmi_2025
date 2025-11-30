import time
import threading
import http.server
import socketserver
import cv2
import numpy as np
import io

class MockMJPEGHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/stream':
            self.send_response(200)
            self.send_header('Content-Type', 'multipart/x-mixed-replace; boundary=frame')
            self.end_headers()
            
            # Create a dummy image
            img = np.zeros((480, 640, 3), dtype=np.uint8)
            cv2.putText(img, "MOCK STREAM", (50, 240), cv2.FONT_HERSHEY_SIMPLEX, 2, (255, 255, 255), 3)
            
            cnt = 0
            try:
                while True:
                    # Update image with counter
                    frame = img.copy()
                    cv2.putText(frame, f"Frame {cnt}", (50, 300), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
                    cnt += 1
                    
                    # Encode to JPEG
                    _, jpg_data = cv2.imencode('.jpg', frame)
                    jpg_bytes = jpg_data.tobytes()
                    
                    # Send boundaries and data
                    self.wfile.write(b'--frame\r\n')
                    self.wfile.write(b'Content-Type: image/jpeg\r\n\r\n')
                    self.wfile.write(jpg_bytes)
                    self.wfile.write(b'\r\n')
                    
                    # Simulate variable delay/jitter
                    time.sleep(0.05) 
            except (ConnectionResetError, BrokenPipeError):
                pass
        else:
            self.send_error(404)

class MockMJPEGServer:
    def __init__(self, host='127.0.0.1', port=8081):
        self.host = host
        self.port = port
        self.server = socketserver.ThreadingTCPServer((host, port), MockMJPEGHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def start(self):
        print(f"Mock MJPEG Server started at http://{self.host}:{self.port}/stream")
        self.thread.start()

    def stop(self):
        self.server.shutdown()
        self.server.server_close()

if __name__ == '__main__':
    server = MockMJPEGServer()
    server.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        server.stop()
