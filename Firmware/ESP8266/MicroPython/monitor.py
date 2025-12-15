import serial
import serial.tools.list_ports
import time
import sys

def detect_port():
    """
    Multi-Strategy Port Detection
    優先級：已知設備 > USB關鍵字 > 排除內建 > 用戶確認
    """
    ports = list(serial.tools.list_ports.comports())
    if not ports:
        print("❌ No COM ports found!")
        return None
    
    # === 策略 1: 已知設備 VID/PID ===
    KNOWN_DEVICES = [
        (0x1A86, 0x7523),  # CH340 (常見於 ESP8266/NodeMCU)
        (0x10C4, 0xEA60),  # CP2102 (常見於 ESP32)
        (0x0403, 0x6001),  # FT232 (FTDI)
    ]
    
    for p in ports:
        if hasattr(p, 'vid') and hasattr(p, 'pid'):
            if (p.vid, p.pid) in KNOWN_DEVICES:
                print(f"✅ Matched Known Device: {p.device} ({p.description})")
                return p.device
    
    # === 策略 2: 關鍵字匹配（多個關鍵字） ===
    USB_KEYWORDS = ['USB', 'Serial', 'CH340', 'CP210', 'FTDI', 'UART']
    
    for p in ports:
        desc_upper = p.description.upper()
        if any(kw.upper() in desc_upper for kw in USB_KEYWORDS):
            print(f"✅ Keyword Match: {p.device} ({p.description})")
            return p.device
    
    # === 策略 3: 排除已知內建設備 ===
    EXCLUDE_KEYWORDS = ['Bluetooth', 'Virtual', 'Communications Port']
    
    filtered_ports = [
        p for p in ports 
        if not any(ex in p.description for ex in EXCLUDE_KEYWORDS)
    ]
    
    if filtered_ports:
        # 取最後一個（通常是最近插入的）
        selected = filtered_ports[-1]
        print(f"⚠️ Fallback Selection: {selected.device} ({selected.description})")
        return selected.device
    
    # === 策略 4: 交互式選擇 ===
    print("\n⚠️ Could not auto-detect. Available ports:")
    for i, p in enumerate(ports):
        print(f"  [{i}] {p.device} - {p.description}")
    
    try:
        choice = int(input("Select port number: "))
        if 0 <= choice < len(ports):
            return ports[choice].device
    except:
        pass
    
    return None
target_port = detect_port()
if not target_port:
    target_port = 'COM12' # Default Fallback

print(f"Auto-Detected Port: {target_port}")
print("Monitoring... Press Ctrl+C to exit")
print("=" * 50)

try:
    ser = serial.Serial(target_port, 115200, timeout=1)
except Exception as e:
    print(f"Error opening {target_port}: {e}")
    sys.exit(1)

try:
    # 發送 Ctrl+D 來軟重啟
    ser.write(b'\x04')
    time.sleep(0.5)
    
    while True:
        if ser.in_waiting:
            data = ser.read(ser.in_waiting)
            try:
                print(data.decode('utf-8'), end='')
            except:
                print(data)
except KeyboardInterrupt:
    print("\n\nStopped.")
finally:
    ser.close()