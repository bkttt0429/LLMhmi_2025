import machine
import time
import struct
import socket
import select
import gc
import uasyncio as asyncio
# from robot import RobotArm

# === Configuration ===
LED_PIN = 2  # Onboard LED (GPIO2)
led = machine.Pin(LED_PIN, machine.Pin.OUT)
led.value(1) # Off

# === Robot Instance ===
try:
    # robot = RobotArm()
    print("Robot Arm Disabled")
except Exception as e:
    print(f"Robot Init Error: {e}")
    # Blink fast to indicate error
    while True:
        led.value(not led.value())
        time.sleep(0.1)

# === CRC16-CCITT (Poly 0x1021) ===
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

# === Async Tasks ===

async def led_heartbeat():
    """Blinks LED to show system is alive"""
    print("[Task] LED Heartbeat started")
    while True:
        led.value(0) # On
        await asyncio.sleep(0.1)
        led.value(1) # Off
        await asyncio.sleep(1.9)

# async def motor_loop():
#     """Runs robot update loop at 50Hz (20ms)"""
#     print("[Task] Motor Loop started")
#     while True:
#         # robot.update()
#         await asyncio.sleep_ms(20)

async def network_listener():
    """Polls UDP and Serial for commands"""
    print("[Task] Network Listener started")
    
    # UDP Setup
    udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    udp.setblocking(False) 
    try:
        udp.bind(('0.0.0.0', 4211))
    except Exception as e:
        print(f"UDP Bind Error: {e}")
    
    uart = machine.UART(0, 115200)
    uart.init(115200, bits=8, parity=None, stop=1, timeout=0)
    
    while True:
        # 1. Poll UDP
        try:
            data, addr = udp.recvfrom(64)
            if data:
                process_packet(data)
        except OSError:
            pass 
            
        # 2. Check Serial
        if uart.any():
            raw = uart.read()
            if raw:
                process_packet(raw)

        await asyncio.sleep_ms(10)

def process_packet(data):
    """Parses incoming binary packet (RM header)"""
    if len(data) < 4: return
    
    try:
        idx = data.find(b'RM')
        if idx == -1: return
        
        pkt = data[idx:]
        if len(pkt) < 4: return
        
        cmd_id = pkt[2]
        pkt_len = 0
        if cmd_id == 0x01: pkt_len = 2 + 1 + 12 + 2 # 17 bytes
        elif cmd_id == 0x03: pkt_len = 2 + 1 + 16 + 2 # 21 bytes
        
        if pkt_len > 0 and len(pkt) >= pkt_len:
            # Verify CRC
            payload_with_header = pkt[0 : pkt_len-2]
            received_crc = struct.unpack('<H', pkt[pkt_len-2 : pkt_len])[0]
            calc = calculate_crc(payload_with_header)
            
            if calc == received_crc:
                payload = pkt[3 : pkt_len-2]
                if cmd_id == 0x03:
                    try:
                        b, s, e, g = struct.unpack('<ffff', payload)
                        # robot.move_angles(b, s, e, g)
                        pass
                    except: pass
                elif cmd_id == 0x01: # XYZ Support
                     try:
                        if len(payload) == 16:
                             x, y, z, g = struct.unpack('<ffff', payload)
                             # robot.move_to(x,y,z,g)
                             pass
                        else:
                             x, y, z = struct.unpack('<fff', payload)
                             # robot.move_to(x,y,z)
                             pass
                     except: pass

    except Exception as e:
        print(f"Packet Error: {e}")

# === Main Entry ===
async def main():
    print("=== ESP8266 Robot Arm Firmware v2.1 (Async) ===")
    
    import network
    wlan = network.WLAN(network.STA_IF)
    if wlan.isconnected():
        print(f"IP: {wlan.ifconfig()[0]}")
    
    asyncio.create_task(led_heartbeat())
    # asyncio.create_task(motor_loop())
    asyncio.create_task(sensor_loop()) # [NEW] Sensor Task
    asyncio.create_task(network_listener())
    
    while True:
        await asyncio.sleep(10)

# === Sensor Task ===
from sensors import SonarOnePin, VibrationSensor
import json

async def sensor_loop():
    """Reads sensors and broadcasts UDP data"""
    # NOTE: User requested D1 (GPIO5) for Sonar and D2 (GPIO4) for Vibration.
    # Check wiring to avoid conflict with Base/Shoulder Servos if connected.
    
    # [DISABLED ROBOT CONFIG]
    # sensor_cfg = robot.config.get('sensors', {})
    # sonar_pin = sensor_cfg.get('sonar', {}).get('pin', 5)
    # vib_pin = sensor_cfg.get('vibration', {}).get('pin', 4)
    sonar_pin = 5
    vib_pin = 4
    
    print(f"[Task] Sensor Loop started (Sonar: {sonar_pin}, Vib: {vib_pin})")
    
    sonar = SonarOnePin(sonar_pin) 
    vib = VibrationSensor(vib_pin)
    
    udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    
    # Calculate Subnet Broadcast (e.g. 10.28.14.72 -> 10.28.14.255)
    import network
    wlan = network.WLAN(network.STA_IF)
    try:
        ip = wlan.ifconfig()[0]
        parts = ip.split('.')
        # Assume /24 subnet (Standard for Home/Office)
        broadcast_ip = "{}.{}.{}.255".format(parts[0], parts[1], parts[2])
    except:
        broadcast_ip = '255.255.255.255' # Fallback
        
    dest_addr = (broadcast_ip, 4211)
    print(f"[Task] Broadcast Target: {broadcast_ip}")
    
    print("[Task] Sensor Loop started (Sonar: D1, Vib: D2)")
    
    while True:
        dist = sonar.measure_cm()
        is_vib = vib.is_vibrating()
        
        # Prepare Payload
        # Compact JSON: {"d": dist, "v": 0/1}
        payload = {"d": round(dist, 1), "v": 1 if is_vib else 0, "device": "esp8266-arm"}
        msg = json.dumps(payload)
        
        try:
            udp.sendto(msg.encode(), dest_addr)
        except:
            pass
            
        await asyncio.sleep(0.1) # 10Hz Update

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Stopped")
    except Exception as e:
        print(f"Crash: {e}")
