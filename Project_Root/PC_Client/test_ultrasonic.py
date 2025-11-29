import serial
import time
import serial.tools.list_ports
import sys

# 設定 BaudRate (必須與 ESP32 韌體中的 Serial.begin 一致)
BAUD_RATE = 115200

def select_serial_port():
    """
    列出並讓使用者選擇 COM Port
    """
    ports = serial.tools.list_ports.comports()
    
    if not ports:
        print("❌ 未偵測到任何 Serial Port！")
        print("   請檢查 USB 線是否連接，或驅動程式是否安裝。")
        return None

    print("\n🔍 偵測到以下連接埠：")
    print("-" * 40)
    for i, p in enumerate(ports):
        print(f"  [{i}] {p.device} ({p.description})")
    print("-" * 40)

    while True:
        try:
            selection = input("👉 請輸入編號 (例如 0) 並按 Enter: ")
            idx = int(selection)
            if 0 <= idx < len(ports):
                return ports[idx].device
            else:
                print("⚠️ 輸入無效，請輸入列表中的數字。")
        except ValueError:
            print("⚠️ 請輸入有效的整數。")

def print_bar_graph(dist):
    """
    在終端機繪製距離長條圖
    """
    # 限制顯示範圍 0 ~ 100cm (超過顯示滿格)
    max_disp = 100.0
    scale = 2.0 # 每 2cm 一格
    
    val = min(dist, max_disp)
    bar_len = int(val / scale)
    bar = "█" * bar_len
    space = " " * (int(max_disp / scale) - bar_len)
    
    # 顏色/圖示邏輯
    if dist < 5.0:
        status = "🛑 撞到了!" 
    elif dist < 15.0:
        status = "⚠️ 危險距離"
    elif dist > 400:
        status = "📡 超出範圍"
    else:
        status = ""

    # 使用 \r 讓游標回到行首 (但在大量 log 混合輸出時，直接 print 換行比較清晰)
    # 這裡採用直接 print 一行的方式
    print(f"📏 距離: {dist:>6.1f} cm |{bar}{space}| {status}")

def main():
    print("\n=== ESP32 超聲波傳感器測試工具 ===")
    
    # 1. 選擇 Port
    port = select_serial_port()
    if not port:
        return

    print(f"\n🚀 正在連線至 {port} ({BAUD_RATE})...")
    print("❌ 按下 Ctrl + C 可隨時停止程式\n")

    try:
        # 2. 建立連線
        ser = serial.Serial(port, BAUD_RATE, timeout=0.1)
        time.sleep(2) # 等待 ESP32 重啟初始化
        
        # 清空緩衝區，避免讀到舊資料
        ser.reset_input_buffer()

        print("📡 等待數據中...\n")

        while True:
            if ser.in_waiting:
                try:
                    # 讀取一行並解碼
                    # errors='replace' 會將無法解碼的字元變為 ?，防止程式崩潰
                    line = ser.readline().decode('utf-8', errors='replace').strip()
                    
                    if not line:
                        continue

                    # --- 解析邏輯 (對應 Arduino 的 Serial.printf("DIST:%.1f\n", dist)) ---
                    if "DIST:" in line:
                        try:
                            # 格式: "DIST:25.4" -> 分割後取第 1 個元素
                            dist_str = line.split(":")[1]
                            dist = float(dist_str)
                            
                            # 顯示視覺化圖表
                            print_bar_graph(dist)
                            
                        except (IndexError, ValueError):
                            print(f"⚠️ 解析錯誤: {line}")
                            
                    elif "[OK]" in line:
                        print(f"✅ 系統訊息: {line}")
                    elif "IP" in line:
                        print(f"🌐 網路資訊: {line}")
                    else:
                        # 顯示其他雜訊或 Debug 訊息
                        print(f"[RAW] {line}")

                except UnicodeDecodeError:
                    pass # 忽略解碼錯誤
            
            # 稍微休息，降低 CPU 使用率
            time.sleep(0.01)

    except serial.SerialException as e:
        print(f"\n❌ Serial 連線錯誤: {e}")
        print("💡 提示: 請確認沒有其他程式 (如 Arduino IDE) 正在佔用此 Port。")
    
    except KeyboardInterrupt:
        print("\n\n👋 程式已由使用者停止。")
    
    finally:
        if 'ser' in locals() and ser.is_open:
            ser.close()
            print("🔒 連線已關閉。")

if __name__ == "__main__":
    main()