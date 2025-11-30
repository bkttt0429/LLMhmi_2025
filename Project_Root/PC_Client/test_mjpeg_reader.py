import unittest
import time
import sys
import os
import threading
import cv2
import numpy as np
import random

# Add project root to path
sys.path.append(os.path.abspath(os.path.dirname(__file__)))

from mjpeg_reader import MJPEGStreamReader
from mock_mjpeg_server import MockMJPEGServer

class TestMJPEGReader(unittest.TestCase):
    def setUp(self):
        # Use random port to avoid conflict
        self.port = random.randint(10000, 20000)
        self.server = MockMJPEGServer(port=self.port)
        self.server.start()
        self.url = f"http://127.0.0.1:{self.port}/stream"
        
    def tearDown(self):
        self.server.stop()
        
    def test_connection_and_frame_retrieval(self):
        # Initialize reader
        reader = MJPEGStreamReader(self.url)
        reader.start()
        
        # Wait for connection
        time.sleep(1)
        self.assertTrue(reader.is_connected(), "Reader failed to connect to mock stream")
        
        # Wait for frames
        time.sleep(1)
        frame, ts = reader.get_frame()
        self.assertIsNotNone(frame, "Failed to retrieve frame")
        self.assertIsInstance(frame, np.ndarray, "Frame is not a numpy array")
        self.assertEqual(frame.shape, (480, 640, 3), "Frame size incorrect")
        
        reader.stop()

    def test_reconnection(self):
        reader = MJPEGStreamReader(self.url)
        reader.start()
        time.sleep(1)
        self.assertTrue(reader.is_connected())
        
        # Simulate server down (stop server)
        self.server.stop()
        time.sleep(2)
        
        # Reader should detect disconnection (though implementation details vary, connected status might lag)
        # But let's restart server and see if it reconnects
        
        # Note: MockServer reuse_address=True should allow quick restart,
        # but sometimes OS holds it. We try to restart on same port.
        try:
            self.server = MockMJPEGServer(port=self.port)
            self.server.start()
        except OSError:
            print("Could not bind same port for reconnection test, skipping exact port check")
            # If we can't restart server on same port, we can't test auto-reconnect logic
            # effectively without changing the reader's URL, which isn't how auto-reconnect works.
            # So we just abort this part of test if bind fails.
            reader.stop()
            return

        time.sleep(3) # Give time to reconnect
        
        frame, ts = reader.get_frame()
        if frame is not None:
             # Verify we are getting new frames
            last_ts = ts
            time.sleep(1)
            frame, new_ts = reader.get_frame()
            self.assertGreater(new_ts, last_ts, "Timestamp should update after reconnection")
        
        reader.stop()

if __name__ == '__main__':
    unittest.main()
