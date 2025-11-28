import serial
import time
import sys
import serial.tools.list_ports

def get_esp32_port():
    """
    自動尋找可能的 ESP32 COM Port
    """
    ports = list(serial.tools.list_ports.comports())
    
    # 列出所有找到的端口，方便除錯
    print("📋 掃描到的端口:")
    for p in ports:
        print(f"   - {p.device}: {p.description}")

    # 嘗試自動辨識常見的 USB 轉 Serial 晶片
    for p in ports:
        # 常見關鍵字: CP210x, CH340, USB Serial, JTAG
        if any(k in p.description for k in ["CP210", "CH340", "USB", "Serial"]):
            return p.device
            
    # 如果找不到明顯的，就回傳第一個，或者讓使用者手動輸入
    if len(ports) > 0:
        return ports[0].device
    return None

def main():
    print("\n🔍 正在尋找 ESP32...")
    port = get_esp32_port()

    if not port:
        print("❌ 找不到 ESP32，請確認 USB 是否連接！")
        return

    print(f"✅ 嘗試連線至: {port}")
    print("📡 按下 Ctrl + C 可以停止程式\n")

    try:
        # 建立連線 (Baud rate 需與 ESP32 程式中的 Serial.begin(115200) 一致)
        ser = serial.Serial(port, 115200, timeout=1)
        time.sleep(2)  # 等待連線穩定

        print(f"{'距離 (cm)':<15} | {'視覺化 (每格 2cm)':<30}")
        print("-" * 60)

        while True:
            if ser.in_waiting:
                try:
                    # 讀取一行數據並解碼
                    # errors='replace' 防止收到亂碼導致程式崩潰
                    line = ser.readline().decode('utf-8', errors='replace').strip()
                    
                    # 對應 ESP32 輸出的格式: "Distance: 25.00 cm"
                    if "Distance:" in line:
                        # 解析數字部分
                        parts = line.split(" ")
                        # parts 通常是 ['Distance:', '25.00', 'cm']
                        for part in parts:
                            try:
                                dist = float(part)
                                # 製作長條圖
                                bar_length = int(dist / 2)  # 每 2cm 一格
                                bar = "█" * bar_length
                                
                                # 變色警示 (如果在終端機支援 ANSI code)
                                # 近距離 (<10cm) 顯示驚嘆號
                                alert = " ⚠️ 靠太近了!" if dist < 10 else ""
                                
                                print(f"{dist:>8.2f} cm      | {bar}{alert}")
                                break # 找到數字就跳出迴圈
                            except ValueError:
                                continue
                    
                    elif "Error" in line:
                        print(f"❌ 感測器錯誤: {line}")
                    
                    # 顯示其他除錯訊息 (可選)
                    # else:
                    #     print(f"ESP32 Raw: {line}")

                except UnicodeDecodeError:
                    pass # 忽略解碼錯誤
            
            # 短暫暫停避免 CPU 佔用過高
            time.sleep(0.01)

    except serial.SerialException as e:
        print(f"\n❌ 無法開啟 Port {port}。")
        print("常見原因：")
        print("1. Arduino IDE 的序列埠監控視窗沒關閉 (佔用中)。")
        print("2. 驅動程式未安裝。")
        print(f"錯誤訊息: {e}")
    except KeyboardInterrupt:
        print("\n👋 程式已停止。")
    finally:
        if 'ser' in locals() and ser.is_open:
            ser.close()
            print("🔒 連線已關閉。")

if __name__ == "__main__":
    main()