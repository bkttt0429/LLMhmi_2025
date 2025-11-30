import unittest
import time
import sys
import os
import threading
import cv2
import numpy as np

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../Project_Root/PC_Client')))

from PC_Client.mjpeg_reader import MJPEGStreamReader
from tests.mock_mjpeg_server import MockMJPEGServer

class TestMJPEGReader(unittest.TestCase):
    def setUp(self):
        self.server = MockMJPEGServer(port=8082)
        self.server.start()
        self.url = "http://127.0.0.1:8082/stream"
        
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
        self.server = MockMJPEGServer(port=8082)
        self.server.start()
        
        time.sleep(3) # Give time to reconnect
        
        frame, ts = reader.get_frame()
        # Verify we are getting new frames
        last_ts = ts
        time.sleep(1)
        frame, new_ts = reader.get_frame()
        self.assertGreater(new_ts, last_ts, "Timestamp should update after reconnection")
        
        reader.stop()

if __name__ == '__main__':
    unittest.main()
