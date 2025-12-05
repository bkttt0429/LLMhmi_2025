
import unittest
import sys
import os
import cv2
import numpy as np
import time
import threading
from unittest.mock import MagicMock, patch

# Adjust path to import PC_Client modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'PC_Client')))

from video_process import MJPEGStreamReader

class TestMJPEGStreamReader(unittest.TestCase):
    def test_threaded_reader_fragmentation(self):
        """
        Test that the threaded MJPEGStreamReader can handle a frame split into many chunks.
        """
        # 1. Create a dummy JPEG frame
        img = np.zeros((100, 100, 3), dtype=np.uint8)
        _, jpeg_data = cv2.imencode('.jpg', img)
        jpeg_bytes = jpeg_data.tobytes()
        
        # 2. Simulate MJPEG stream format
        # Boundary: --123456789000000000000987654321
        boundary = b'--123456789000000000000987654321\r\n'
        header = b'Content-Type: image/jpeg\r\nContent-Length: ' + str(len(jpeg_bytes)).encode() + b'\r\n\r\n'
        full_stream_data = boundary + header + jpeg_bytes + b'\r\n'
        
        # 3. Split this into many small chunks to simulate fragmentation
        chunk_size = 10 # Very small chunks
        chunks = [full_stream_data[i:i+chunk_size] for i in range(0, len(full_stream_data), chunk_size)]
        
        # Add a second frame to ensure the loop continues
        chunks.extend(chunks) 
        
        print(f"DEBUG: Created {len(chunks)} chunks for the mock stream.")

        # 4. Mock the requests session and response iterator
        mock_response = MagicMock()
        mock_response.status_code = 200
        # iter_content returns an iterator
        # We use a generator to simulate network delay if needed, but here we just yield
        def chunk_generator():
            for c in chunks:
                time.sleep(0.001) # Slight delay to simulate network
                yield c
            # Keep yielding empty bytes or sleep to prevent StopIteration immediately if reader is fast
            while True:
                time.sleep(0.1)
                yield b''

        mock_response.iter_content.return_value = chunk_generator()
        
        # We patch requests.Session where it is used in video_process.py
        with patch('video_process.requests.Session') as mock_session_cls:
            mock_session = mock_session_cls.return_value
            mock_session.get.return_value = mock_response
            
            # Initialize reader
            reader = MJPEGStreamReader("http://mock-url")
            
            # Allow some time for the thread to read and decode
            start_time = time.time()
            frame = None
            while time.time() - start_time < 2.0:
                frame = reader.read()
                if frame is not None:
                    break
                time.sleep(0.1)
            
            reader.stop()
            
            if frame is None:
                print("FAILURE: Threaded reader did not produce a frame within timeout.")
            else:
                print("SUCCESS: Threaded reader successfully decoded the fragmented frame.")
                
            self.assertIsNotNone(frame, "Threaded reader should return a frame")

if __name__ == '__main__':
    unittest.main()
