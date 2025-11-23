import re
import time
from PySide6.QtGui import QTextCursor, QPixmap
from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, 
    QPlainTextEdit, QMessageBox, QComboBox, QGroupBox, QLineEdit, QSizePolicy, QApplication
)

# 匯入我們拆分好的模組
import config
from video_thread import VideoThread
from serial_worker import SerialManager, prepare_sketch, compile_and_upload

class Esp32CamWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.video_thread = None
        self.serial_manager = SerialManager() # 實例化 Serial 管理器
        self.current_port = None
        self.serial_enabled = True
        
        self.init_ui()
        self.refresh_ports()
        self.init_timer()

    def init_ui(self):
        self.setWindowTitle("ESP32-S3-CAM 模組化控制中心 v8.0")
        layout = QVBoxLayout()

        # 1. Port 選擇區
        port_group = QGroupBox("1. 硬體連線")
        port_layout = QHBoxLayout()
        self.combo_ports = QComboBox()
        self.combo_ports.currentIndexChanged.connect(self.on_port_changed)
        self.btn_refresh = QPushButton("🔄 重新整理")
        self.btn_refresh.clicked.connect(self.refresh_ports)
        port_layout.addWidget(self.combo_ports, 1)
        port_layout.addWidget(self.btn_refresh)
        port_group.setLayout(port_layout)

        # 2. 燒錄控制區
        upload_group = QGroupBox("2. 韌體燒錄")
        upload_layout = QHBoxLayout()
        self.btn_reset = QPushButton("⚡ 強制 Boot")
        self.btn_reset.clicked.connect(self.force_bootloader)
        self.btn_upload = QPushButton("🔥 上傳韌體")
        self.btn_upload.setStyleSheet("background-color: #d9534f; color: white; font-weight: bold;")
        self.btn_upload.clicked.connect(self.on_upload_clicked)
        upload_layout.addWidget(self.btn_reset)
        upload_layout.addWidget(self.btn_upload)
        upload_group.setLayout(upload_layout)

        # 3. 影像顯示區
        video_group = QGroupBox("3. 即時影像 (支援未來 AI 擴充)")
        video_layout = QVBoxLayout()
        
        ip_layout = QHBoxLayout()
        self.input_ip = QLineEdit()
        self.input_ip.setPlaceholderText("等待 Serial 自動抓取 IP...")
        self.btn_connect = QPushButton("📺 連線影像")
        self.btn_connect.setStyleSheet("background-color: #5bc0de; color: white; font-weight: bold;")
        self.btn_connect.clicked.connect(self.start_video)
        ip_layout.addWidget(QLabel("IP:"))
        ip_layout.addWidget(self.input_ip)
        ip_layout.addWidget(self.btn_connect)

        self.video_label = QLabel("等待影像...")
        self.video_label.setAlignment(Qt.AlignCenter)
        self.video_label.setStyleSheet("background-color: #222; color: #aaa; border: 2px solid #555;")
        self.video_label.setScaledContents(True)
        self.video_label.setMinimumSize(320, 240)
        self.video_label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored)

        video_layout.addLayout(ip_layout)
        video_layout.addWidget(self.video_label, 1)
        video_group.setLayout(video_layout)

        # 4. Log 區
        self.label_status = QLabel("狀態：就緒")
        self.text_log = QPlainTextEdit()
        self.text_log.setReadOnly(True)
        self.text_log.setMaximumHeight(150)

        layout.addWidget(port_group)
        layout.addWidget(upload_group)
        layout.addWidget(video_group, 1)
        layout.addWidget(self.label_status)
        layout.addWidget(self.text_log)
        self.setLayout(layout)
        self.resize(800, 750)

    # === 邏輯處理 ===
    def append_log(self, msg: str):
        self.text_log.appendPlainText(msg.rstrip("\n"))
        self.text_log.moveCursor(QTextCursor.End)

    def refresh_ports(self):
        self.serial_manager.disconnect()
        self.combo_ports.blockSignals(True)
        self.combo_ports.clear()
        
        ports = self.serial_manager.get_ports()
        best_index = -1
        for i, p in enumerate(ports):
            self.combo_ports.addItem(f"{p.device} - {p.description}")
            if "COM7" in p.device: best_index = i # 針對您的環境優化
            elif best_index == -1 and ("ESP32" in p.description.upper() or "CP210" in p.description): best_index = i
        
        self.combo_ports.blockSignals(False)
        if ports:
            self.combo_ports.setCurrentIndex(best_index if best_index != -1 else 0)
            self.on_port_changed()
        else:
            self.label_status.setText("狀態：未偵測到 Port")

    def on_port_changed(self):
        text = self.combo_ports.currentText()
        if text:
            self.current_port = text.split(" - ")[0]
            self.label_status.setText(f"已選擇 {self.current_port}")
            self.reopen_serial()

    def reopen_serial(self):
        if not self.current_port or not self.serial_enabled: return
        success, msg = self.serial_manager.connect(self.current_port)
        self.append_log(msg)

    def force_bootloader(self):
        if not self.current_port: return
        success, msg = self.serial_manager.send_boot_signal(self.current_port)
        self.append_log(msg)
        time.sleep(0.5)
        self.reopen_serial()

    def on_upload_clicked(self):
        if not self.current_port: return
        
        # 準備檔案
        success, msg = prepare_sketch()
        if not success:
            self.append_log(msg)
            return

        # 暫停 Serial 監控
        self.serial_enabled = False
        self.serial_manager.disconnect()
        self.append_log("🔒 釋放 Serial，開始上傳...")
        
        QApplication.processEvents() # 讓 UI 更新
        time.sleep(1.0)

        # 執行上傳 (Blocking)
        ok = compile_and_upload(self.current_port, self.append_log)
        
        # 恢復 Serial
        time.sleep(3.0)
        self.serial_enabled = True
        self.reopen_serial()
        
        if ok:
            QMessageBox.information(self, "成功", "✅ 上傳成功！\nESP32 正在重啟中...")
        else:
            self.label_status.setText("❌ 上傳失敗")

    def start_video(self):
        ip = self.input_ip.text().strip()
        if not ip: return
        url = ip if ip.startswith("http") else f"http://{ip}:81/stream"
        
        if self.video_thread: self.video_thread.stop()
        
        self.video_thread = VideoThread(url)
        self.video_thread.change_pixmap_signal.connect(self.update_image)
        self.video_thread.status_signal.connect(self.append_log)
        self.video_thread.start()

    def update_image(self, img):
        self.video_label.setPixmap(QPixmap.fromImage(img))

    def init_timer(self):
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.read_serial_loop)
        self.timer.start(100)

    def read_serial_loop(self):
        if not self.serial_enabled: return
        line = self.serial_manager.read_line()
        if line:
            self.append_log(f"[ESP]: {line}")
            # 自動抓 IP
            if "IP" in line and ("192." in line or "10." in line):
                ip_match = re.search(r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}', line)
                if ip_match:
                    ip = ip_match.group()
                    self.input_ip.setText(ip)
                    self.append_log(f"✅ 自動偵測 IP: {ip}")

    def closeEvent(self, event):
        if self.video_thread: self.video_thread.stop()
        self.serial_manager.disconnect()
        event.accept()