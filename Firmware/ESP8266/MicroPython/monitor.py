import serial
import serial.tools.list_ports
import time
import sys
import socket
import json
import threading
import datetime

# Configuration
UDP_PORT = 4211
BAUD_RATE = 115200

def detect_port():
    """Auto-detect ESP8266 COM port with Priority Matching"""
    ports = list(serial.tools.list_ports.comports())
    if not ports:
        return None
    
    # Priority 1: VID/PID Match (CH340)
    for p in ports:
        if hasattr(p, 'vid') and p.vid == 0x1A86:
            print(f"✅ Found CH340: {p.device} ({p.description})")
            return p.device
    
    # Priority 2: USB Keyword
    usb_ports = [p for p in ports if 'USB' in p.description.upper()]
    if usb_ports:
        return usb_ports[-1].device
    
    return ports[0].device

def udp_listener():
    """Listens for UDP Broadcasts from ESP8266"""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(('0.0.0.0', UDP_PORT))
        print(f"[UDP] Listening on port {UDP_PORT}...")
    except Exception as e:
        print(f"❌ [UDP] Bind failed: {e}")
        return

    sock.settimeout(2.0)
    while True:
        try:
            try:
                data, addr = sock.recvfrom(1024)
            except socket.timeout:
                print("⏳ [UDP] Waiting... (Stop web_server.py if no data)")
                continue

            msg = data.decode('utf-8', errors='ignore').strip()
            
            # Print Raw if needed
            # print(f"[UDP Raw] {msg}")

            if "{" in msg:
                try:
                    data = json.loads(msg)
                    if "d" in data:
                        dist = data.get("d", -1)
                        vib = data.get("v", 0)
                        
                        # Formatting
                        ts = datetime.datetime.now().strftime("%H:%M:%S")
                        
                        # Visual Indicator for Vibration
                        vib_str = "⚠️ SHAKE!" if vib else "Stable"
                        vib_color = "\033[91m" if vib else "\033[92m" # Red if Shake, Green if Stable
                        reset_color = "\033[0m"
                        
                        # Visual Indicator for Distance
                        dist_str = f"{dist:>5.1f} cm"
                        
                        print(f"[{ts}] 📡 [SENSOR] Dist: {dist_str} | Vib: {vib_color}{vib_str}{reset_color}")
                        
                except json.JSONDecodeError:
                    pass
        except Exception as e:
            print(f"[UDP Error] {e}")

# === MAIN ===
target_port = detect_port()
if not target_port:
    print("❌ No valid port found! (Only UDP will likely work)")
else:
    print(f"🔌 Opening {target_port} @ {BAUD_RATE} baud...")

# Start UDP Thread
udp_thread = threading.Thread(target=udp_listener, daemon=True)
udp_thread.start()

if target_port:
    try:
        ser = serial.Serial(target_port, BAUD_RATE, timeout=1)
        
        # Soft Reset to see Boot Logs
        print("[SYSTEM] Sending Ctrl+D (soft reset)...")
        ser.write(b'\x04')
        time.sleep(0.5)
        
        print("[MONITOR] Started. Press Ctrl+C to exit.\n")
        
        while True:
            if ser.in_waiting:
                try:
                    line = ser.readline().decode('utf-8', errors='replace').strip()
                    if line:
                        print(f"[SERIAL] {line}")
                except Exception as e:
                    print(f"[SERIAL ERROR] {e}")
            time.sleep(0.01)
            
    except serial.SerialException as e:
        print(f"❌ Serial Error: {e}")
        print("⚠️ Continuing in UDP-only mode...")
        # Keep main thread alive for UDP
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\n[MONITOR] Stopped by user.")
    finally:
        if 'ser' in locals() and ser.is_open:
            ser.close()
            print("[MONITOR] Serial port closed.")
else:
    # No Serial, just keep UDP running
    try:
        print("[MONITOR] Running in UDP-only mode (No Serial). Press Ctrl+C to exit.")
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass