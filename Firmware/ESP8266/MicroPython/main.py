import socket
import struct
import machine
import time
import gc
from robot import RobotArm

# === CONFIG ===
UDP_PORT = 4211
HEADER = b'RM'
CMD_MOVE = 0x01
CMD_CALIB = 0x02

# === CRC16-CCITT (Simplified for MicroPython) ===
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

# === SETUP ===
print("Booting v2.0 Controller...")
robot = RobotArm()

udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
udp.bind(('0.0.0.0', UDP_PORT))
udp.settimeout(0.0) # Non-blocking

# Watchdog State
last_packet = time.ticks_ms()
WATCHDOG_TIMEOUT = 2000
last_beacon = time.ticks_ms()

print("System Ready. Listening on UDP 4211.")

# === MAIN LOOP ===
while True:
    now = time.ticks_ms()
    
    # 1. Robot Motion Update (High Priority)
    robot.update()
    
    # 2. Network Handling
    try:
        data, addr = udp.recvfrom(32) # Small buffer for Binary Packet
        
        # Packet Validation (Min Size: 2+1+12+2 = 17 bytes)
        if len(data) >= 17 and data[0:2] == HEADER:
            
            # Extract Components
            cmd_id = data[2]
            payload = data[3:15] # 12 Bytes
            rx_crc = struct.unpack('<H', data[15:17])[0]
            
            # Verify CRC (Calc over Header+Cmd+Payload)
            calc_crc = calculate_crc(data[0:15])
            
            if calc_crc == rx_crc:
                last_packet = now
                
                # Command Dispatch
                if cmd_id == CMD_MOVE:
                    # Unpack X, Y, Z (3 Floats)
                    x, y, z = struct.unpack('<fff', payload)
                    robot.move_to(x, y, z)
                    
                elif cmd_id == 0x03: # CMD_MOVE_ANGLES
                    # Unpack B, S, E (3 Floats)
                    b, s, e = struct.unpack('<fff', payload)
                    print(f"CMD ANGLES: {b:.1f}, {s:.1f}, {e:.1f}")
                    robot.move_angles(b, s, e)

                elif cmd_id == CMD_CALIB:
                    # Placeholder for Calibration Parameter Updates
                    pass
            else:
                print("CRC Fail")
                
    except OSError:
        pass # No Data
    except Exception as e:
        print("Net Error:", e)

    # 3. Safety Watchdog
    if time.ticks_diff(now, last_packet) > WATCHDOG_TIMEOUT:
        if robot.is_moving:
            print("[Watchdog] Timeout! Stopping.")
            robot.stop()
            last_packet = now # Reset to avoid spam loop

    # 4. Discovery Beacon (Every 1s)
    # Using a simple counter or checking ticks
    if time.ticks_diff(now, last_beacon) > 1000:
        last_beacon = now
        try:
            # Broadcast to 255.255.255.255 port UDP_PORT
            # Note: MicroPython might need active station interface for broadcast
            udp.sendto(b'ESP8266_ARM', ('255.255.255.255', UDP_PORT))
        except:
            pass

    # 4. Maintenance
    # gc.collect() # Don't call every loop, maybe every 1s or if memory low
    # However, robot.py calls it after move.
