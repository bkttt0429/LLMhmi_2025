import serial
import time

ser = serial.Serial('COM12', 115200, timeout=1)
print("Monitoring COM12... Press Ctrl+C to exit")
print("=" * 50)

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