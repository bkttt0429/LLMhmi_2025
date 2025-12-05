
import unittest
import sys
import os
import cv2
import numpy as np
from unittest.mock import MagicMock, patch

# Adjust path to import PC_Client modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'PC_Client')))

# We DO NOT mock sys.modules['requests'] here globally because video_process needs the real one
# to import other submodules like requests.exceptions or network_utils.
from video_process import MJPEGStreamReader

class TestMJPEGStreamReader(unittest.TestCase):
    def test_get_frame_large_fragmentation(self):
        """
        Test that get_frame can handle a frame split into many chunks
        without returning None prematurely.
        """
        # 1. Create a dummy JPEG frame
        img = np.zeros((100, 100, 3), dtype=np.uint8)
        _, jpeg_data = cv2.imencode('.jpg', img)
        jpeg_bytes = jpeg_data.tobytes()

        # 2. Simulate MJPEG stream format
        full_stream_data = b'some_headers' + jpeg_bytes + b'footer'

        # 3. Split this into 20 small chunks
        chunk_size = len(full_stream_data) // 20 + 1
        chunks = [full_stream_data[i:i+chunk_size] for i in range(0, len(full_stream_data), chunk_size)]

        # Pad with empty chunks to ensure we exceed the loop limit of 10 if we read one by one
        # Actually, let's just make sure len(chunks) > 10
        # In the bug, `max_chunks_per_call = 10`.
        # So we need at least 11 chunks to trigger the failure if each `next()` returns one chunk.
        while len(chunks) < 15:
             chunks.insert(0, b'junk')

        print(f"DEBUG: Created {len(chunks)} chunks for the mock stream.")

        # 4. Mock the requests session and response iterator
        mock_response = MagicMock()
        mock_response.status_code = 200
        # iter_content returns an iterator
        mock_response.iter_content.return_value = iter(chunks)

        # We patch requests.Session where it is used in video_process.py
        with patch('video_process.requests.Session') as mock_session_cls:
            mock_session = mock_session_cls.return_value
            mock_session.get.return_value = mock_response

            # Initialize reader
            # Note: We pass source_ip=None to avoid triggering SourceAddressAdapter logic which might be complex
            reader = MJPEGStreamReader("http://mock-url")

            # Force connection (usually happens in __init__ but let's be sure)
            # The __init__ calls _connect() which calls session.get()

            # 5. Call get_frame
            # In the buggy version, this loop:
            # while chunks_read < max_chunks_per_call:
            # runs 10 times, consumes 10 chunks.
            # If our frame is in chunk 15, it won't be found.
            # It returns None.

            print("Calling get_frame()...")
            frame = reader.get_frame()

            if frame is None:
                print("FAILURE: get_frame() returned None prematurely (Bug Reproduced)")
            else:
                print("SUCCESS: get_frame() returned the frame")

            self.assertIsNotNone(frame, "get_frame should return a frame, but returned None (stutter bug)")

if __name__ == '__main__':
    unittest.main()
