import socket
import struct
import time
import numpy as np
import cv2

# === CONFIG ===
IP = "10.28.14.129" # Adjust as needed
PORT = 4211
HEADER = b'RM'
CMD_MOVE = 0x01

# === PROTOCOL ===
def calculate_crc(data):
    crc = 0xFFFF
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            if crc & 0x8000:
                crc = (crc << 1) ^ 0x1021
            else:
                crc <<= 1
            crc &= 0xFFFF
    return crc

def send_move(sock, x, y, z):
    # Pack Payload: 3 Floats (Little Endian)
    payload = struct.pack('<fff', x, y, z)
    
    # Construct Packet to calc CRC: Header + Cmd + Payload
    packet_body = HEADER + struct.pack('B', CMD_MOVE) + payload
    
    # Calc CRC
    crc = calculate_crc(packet_body)
    
    # Final Packet with CRC
    packet = packet_body + struct.pack('<H', crc)
    
    sock.sendto(packet, (IP, PORT))
    print(f"[TX] Move: {x},{y},{z} | Len: {len(packet)}")

# === VISION ===
def detect_marker(cap):
    """
    Returns (u, v) center of detected ArUco marker.
    """
    ret, frame = cap.read()
    if not ret: return None
    
    # OpenCV ArUco (Skeleton)
    # dictionary = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
    # parameters = cv2.aruco.DetectorParameters()
    # detector = cv2.aruco.ArucoDetector(dictionary, parameters)
    # corners, ids, rejected = detector.detectMarkers(frame)
    
    # if ids is not None:
    #     c = corners[0][0] # First marker
    #     cx = int((c[0][0] + c[2][0]) / 2)
    #     cy = int((c[0][1] + c[2][1]) / 2)
    #     return (cx, cy)
    
    return (0, 0) # Mock

# === MAIN CALIBRATION LOOP ===
def run_calibration():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    cap = cv2.VideoCapture(0) # Open Camera
    
    data_points = [] # List of (q_theoretical, q_measured)
    
    # Generate random test poses (Logical Angles or Cartesian?)
    # Firmware accepts Cartesian. We send Cartesian targets.
    # We want to Calibrate: q_logical -> PWM.
    # But we can only measure PHYSICAL Angle/Pos.
    
    targets = [
        (100, 0, 50),
        (120, 20, 50),
        (100, -20, 80),
        # ... more points covering workspace
    ]
    
    print("Starting Auto-Calibration Sequence...")
    
    for (tx, ty, tz) in targets:
        # 1. Send Command
        send_move(sock, tx, ty, tz)
        
        # 2. Wait for Motion (Estimate 2s)
        time.sleep(2.0)
        
        # 3. Capture Truth
        uv = detect_marker(cap)
        if uv:
            # Here you would:
            # - Convert UV (pixels) to Physical Angles 
            # - OR use a generic dataset: (PWM_sent, Angle_measured)
            # This requires 'SetPWM' generic command usually.
            # But in this v2.0, we send Cartesian.
            # Strategy: We assume IK is correct. We compare Expected Pos vs Real Pos?
            # Or simpler:
            # We want to find k, b for `angle = k*q + b`.
            # We need to send 'q' and measure 'angle'.
            pass
            
    # 4. Solvers
    # A * x = B
    # A = [ [q1, 1], [q2, 1] ... ]
    # x = [k, b]
    # B = [ real_angle1, real_angle2 ... ]
    
    # k, b = np.linalg.lstsq(A, B, rcond=None)[0]
    # print(f"Calibrated: k={k:.4f}, b={b:.4f}")
    
    # 5. Generate config.json and upload?
    # (Requires implementing FTP upload or 'CMD_SET_CONFIG' binary command)

if __name__ == "__main__":
    run_calibration()
