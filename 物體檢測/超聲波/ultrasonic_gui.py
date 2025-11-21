import subprocess
import sys
import time
import serial
import os
import shutil
import re

from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout,
    QLabel, QProgressBar, QMessageBox
)

os.environ["PYTHONIOENCODING"] = "utf-8"

# ======== 參數設定 ========
BAUD_RATE = 115200          # ★ 要跟 code.ino 裡的 Serial.begin(...) 一樣
MAX_DISTANCE_CM = 200       # 進度條最大顯示距離
SKETCH_DIR = "mega_ultrasonic"
SKETCH_NAME = "mega_ultrasonic.ino"
SOURCE_INO = "code.ino"     # ★ 你的 .ino 檔名
#FQBN = "arduino:avr:mega:cpu=atmega2560"   # Arduino Mega 2560
FQBN = "arduino:avr:mega"   # 跟 board list 顯示的一模一樣

# ==========================


# --------- Step 1: 找 Arduino Mega 的 COM Port ---------
def get_mega_port():
    try:
        result = subprocess.run(
            ["arduino-cli", "board", "list"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="ignore"
        )
        lines = result.stdout.strip().split("\n")
        for line in lines:
            # 範例: "COM6  Arduino Mega or Mega 2560 ... arduino:avr:mega"
            if line.strip().startswith("COM") and ("Mega" in line or "mega" in line):
                return line.split()[0]  # 第一個欄位是 COM 名稱
        # 如果沒抓到 "Mega"，就退而求其次挑第一個 COM
        for line in lines:
            if line.strip().startswith("COM"):
                return line.split()[0]
    except Exception as e:
        print(f"Error detecting Mega: {e}")
    return None


# --------- Step 2: 準備 sketch：把 code.ino 複製成 mega_ultrasonic/mega_ultrasonic.ino ---------
def prepare_sketch():
    if not os.path.exists(SOURCE_INO):
        print(f"找不到 {SOURCE_INO}，請確認 .py 與 {SOURCE_INO} 在同一資料夾。")
        sys.exit(1)

    if not os.path.exists(SKETCH_DIR):
        os.makedirs(SKETCH_DIR, exist_ok=True)

    dest_path = os.path.join(SKETCH_DIR, SKETCH_NAME)
    shutil.copy(SOURCE_INO, dest_path)
    print(f"已將 {SOURCE_INO} 複製到 {dest_path}")


# --------- Step 3: compile + upload 到 Mega ---------
def upload_to_mega(port):
    try:
        # 先編譯
        print("=== Compile ===")
        compile_result = subprocess.run(
            ["arduino-cli", "compile", "--fqbn", FQBN, SKETCH_DIR],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="ignore"
        )
        print("compile stdout:\n", compile_result.stdout)
        print("compile stderr:\n", compile_result.stderr)
        if compile_result.returncode != 0:
            print("❌ compile 失敗")
            return False

        # 確保沒有其他程式占用 COM Port
        try:
            s = serial.Serial(port)
            s.close()
        except Exception:
            pass

        time.sleep(2)  # 給系統一點時間釋放 COM

        # 上傳
        print("=== Upload ===")
        upload_result = subprocess.run(
            ["arduino-cli", "upload", "-p", port, "--fqbn", FQBN, SKETCH_DIR],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="ignore"
        )
        print("upload stdout:\n", upload_result.stdout)
        print("upload stderr:\n", upload_result.stderr)

        if upload_result.returncode != 0:
            print("❌ upload 失敗")
            return False

        print("✅ Upload complete.")
        return True

    except Exception as e:
        print(f"Upload exception: {e}")
        return False


# --------- PySide6 GUI：顯示距離 ---------
class UltrasonicWindow(QWidget):
    def __init__(self, port):
        super().__init__()
        self.port = port
        self.ser = None

        self.init_serial()
        self.init_ui()
        self.init_timer()

    def init_serial(self):
        try:
            self.ser = serial.Serial(
                self.port,
                BAUD_RATE,
                timeout=0.1
            )
        except serial.SerialException as e:
            QMessageBox.critical(
                self,
                "連線錯誤",
                f"無法開啟序列埠 {self.port}\n\n{e}"
            )
            self.ser = None

    def init_ui(self):
        self.setWindowTitle(f"Mega 超聲波距離顯示 ({self.port})")

        layout = QVBoxLayout()

        self.label_title = QLabel("超聲波距離（cm）")
        self.label_title.setAlignment(Qt.AlignCenter)
        self.label_title.setStyleSheet("font-size: 20px;")

        self.label_value = QLabel("--.- cm")
        self.label_value.setAlignment(Qt.AlignCenter)
        self.label_value.setStyleSheet("font-size: 40px; font-weight: bold;")

        self.progress = QProgressBar()
        self.progress.setRange(0, MAX_DISTANCE_CM)
        self.progress.setValue(0)
        self.progress.setFormat("%v cm")
        self.progress.setAlignment(Qt.AlignCenter)
        self.progress.setStyleSheet("font-size: 18px;")

        layout.addWidget(self.label_title)
        layout.addWidget(self.label_value)
        layout.addWidget(self.progress)

        self.setLayout(layout)
        self.resize(400, 220)

    def init_timer(self):
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.read_serial)
        self.timer.start(100)  # 每 100ms 讀一次

    def read_serial(self):
        if self.ser is None or not self.ser.is_open:
            return

        try:
            line = self.ser.readline().decode(errors="ignore").strip()
        except serial.SerialException:
            return

        if not line:
            return

        # 嘗試直接轉 float
        distance = None
        try:
            distance = float(line)
        except ValueError:
            # 若是 "Distance: 23.4 cm" 類型，用正則抓數字
            match = re.search(r"(-?\d+(\.\d+)?)", line)
            if match:
                try:
                    distance = float(match.group(1))
                except ValueError:
                    distance = None

        if distance is None:
            # 無法解析就略過
            print(f"Raw: {line}")
            return

        if distance < 0:
            self.label_value.setText("超出量測範圍")
            self.progress.setValue(0)
        else:
            d_clamped = max(0, min(distance, MAX_DISTANCE_CM))
            self.label_value.setText(f"{distance:.1f} cm")
            self.progress.setValue(int(d_clamped))

    def closeEvent(self, event):
        if self.ser is not None and self.ser.is_open:
            self.ser.close()
        event.accept()


if __name__ == "__main__":
    port = get_mega_port()
    if not port:
        print("No Arduino Mega detected.")
        sys.exit(1)

    print(f"Detected Mega on {port}")

    prepare_sketch()
    ok = upload_to_mega(port)
    if not ok:
        print("上傳失敗，但如果板子上本來就有超聲波程式，還是可以試著開 GUI 讀資料。")

    time.sleep(3)  # 給 Mega 重啟 & Serial ready 的時間

    # ★★★ 這裡改：如果已經有 QApplication，就不要再 new 一個
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)

    window = UltrasonicWindow(port)
    window.show()

    # 在 Notebook 環境下，通常只需要執行一次 app.exec()
    # 第二次再跑這格時，不要再呼叫 exec()，不然會卡住
    if not hasattr(app, "_already_running"):
        app._already_running = True
        app.exec()


