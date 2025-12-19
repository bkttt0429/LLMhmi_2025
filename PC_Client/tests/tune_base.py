import socket
import struct
import time

# IP of ESP8266 (Found in logs: 10.28.14.243? No, that's PC. ESP is usually 192.168.4.1 or similar)
# We will broadcast to be safe.
UDP_IP = '<broadcast>'
UDP_PORT = 4211

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)

def send_angle(base_angle):
    # CMD_MOVE_ANGLES = 0x03
    # Payload: Base, Shoulder, Elbow, Gripper (4 floats)
    # We keep S/E/G constant, only tune Base.
    shoulder = 90.0
    elbow = 90.0
    gripper = 50.0
    
    # Pack 4 floats
    payload = struct.pack('<ffff', float(base_angle), shoulder, elbow, gripper)
    
    # Header RM + Cmd 0x03 + Payload
    body = b'RM' + struct.pack('B', 0x03) + payload
    
    # CRC calculation
    crc = 0xFFFF
    for byte in body:
        crc ^= byte << 8
        for _ in range(8):
            if crc & 0x8000:
                crc = (crc << 1) ^ 0x1021
            else:
                crc <<= 1
            crc &= 0xFFFF
            
    packet = body + struct.pack('<H', crc)
    
    print(f"Sending Base: {base_angle}")
    sock.sendto(packet, (UDP_IP, UDP_PORT))

def main():
    print("=== MG90 Base Calibration Tool ===")
    print("Press 'a' to decrease (CW spin?)")
    print("Press 'd' to increase (CCW spin?)")
    print("Press 's' to set to 90 (Theoretical Stop)")
    print("Enter a number to jump directly.")
    print("Goal: Find the number where the motor STOPS spinning.")
    print("==================================")
    
    current_val = 90.0
    
    while True:
        user_input = input(f"Current: {current_val} > ").strip().lower()
        
        if user_input == 'a':
            current_val -= 1.0
        elif user_input == 'd':
            current_val += 1.0
        elif user_input == 's':
            current_val = 90.0
        elif user_input == 'q':
            break
        else:
            try:
                current_val = float(user_input)
            except:
                print("Invalid input")
                continue
                
        send_angle(current_val)

if __name__ == '__main__':
    main()
