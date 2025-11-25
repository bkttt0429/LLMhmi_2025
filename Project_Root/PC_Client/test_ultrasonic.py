import serial
import time
import sys
from serial.tools import list_ports

def get_esp32_port():
    """自動尋找 ESP32 的 COM Port"""
    ports = list_ports.comports()
    for p in ports:
        # 常見的 ESP32 驅動描述關鍵字
        if "USB" in p.description or "CP210" in p.description or "CH340" in p.description:
            return p.device
    return None

def main():
    print("🔍 正在尋找 ESP32...")
    port = get_esp32_port()

    if not port:
        print("❌ 找不到 ESP32！請確認 USB 是否連接，或是驅動程式是否安裝。")
        print("可用端口:", [p.device for p in list_ports.comports()])
        return

    print(f"✅ 找到裝置：{port}")
    
    try:
        # 設定 Baud Rate 為 115200 (必須與 ESP32 的 Serial.begin 一致)
        ser = serial.Serial(port, 115200, timeout=1)
        time.sleep(2) # 等待連線穩定
        print("📡 開始讀取超音波數據 (按 Ctrl+C 離開)...\n")
        print("-" * 30)

        while True:
            if ser.in_waiting:
                try:
                    # 讀取一行並解碼
                    line = ser.readline().decode('utf-8', errors='ignore').strip()
                    
                    # 篩選並顯示距離資訊
                    if "DIST:" in line:
                        # 解析格式 "DIST:15.5"
                        parts = line.split(":")
                        if len(parts) > 1:
                            dist_str = parts[1]
                            dist = float(dist_str)
                            
                            # 簡單的視覺化條圖
                            bar = "█" * int(dist / 5) 
                            print(f"📏 距離: {dist:>6.1f} cm  |{bar}")
                            
                    elif "WARNING" in line:
                        print(f"⚠️  {line}")
                    
                except ValueError:
                    continue
                except Exception as e:
                    print(f"讀取錯誤: {e}")

            time.sleep(0.01)

    except serial.SerialException as e:
        print(f"❌ 無法開啟 Serial Port: {e}")
        print("提示：請確認沒有其他程式 (如 Arduino IDE 或 web_server.py) 佔用此 Port")
    except KeyboardInterrupt:
        print("\n👋 程式已停止")
    finally:
        if 'ser' in locals() and ser.is_open:
            ser.close()

if __name__ == "__main__":
    main()