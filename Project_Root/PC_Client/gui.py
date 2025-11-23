import re
import time
import math
import random
from PySide6.QtGui import (QTextCursor, QPixmap, QKeyEvent, QPainter, QColor, 
                           QPen, QBrush, QRadialGradient, QConicalGradient, QFont)
from PySide6.QtCore import QTimer, Qt, QCoreApplication, QSize, QPointF, QRectF
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, 
    QLabel, QPushButton, QPlainTextEdit, QMessageBox, QComboBox, 
    QGroupBox, QLineEdit, QSizePolicy, QApplication, QProgressBar, QDialog, QFormLayout
)

import config
from video_thread import VideoThread
from serial_worker import SerialManager, prepare_sketch, compile_and_upload

# ==========================================
#  自定義元件：戰術雷達 (Tactical Radar)
# ==========================================
class RadarWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(220, 220)
        self.angle = 0
        self.blips = [] # 儲存掃描到的點: (x, y, opacity, timestamp)
        
        # 雷達動畫 Timer (60 FPS)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_scan)
        self.timer.start(16) 

    def update_scan(self):
        # 掃描線旋轉速度
        self.angle = (self.angle + 2) % 360
        
        # 更新光點 (淡出效果)
        current_time = time.time()
        new_blips = []
        for x, y, op, ts in self.blips:
            # 讓光點隨時間慢慢變透明
            if op > 5:
                new_blips.append((x, y, op - 2, ts))
        self.blips = new_blips
        
        self.update() # 觸發 paintEvent 重繪

    def add_blip(self, distance_cm):
        # 將距離數據轉換為雷達上的座標
        if distance_cm > 50 or distance_cm <= 0: return
        
        # 畫布中心與半徑
        w, h = self.width(), self.height()
        cx, cy = w / 2, h / 2
        max_radius = min(w, h) / 2 - 15
        
        # 計算光點位置 (距離越近，越靠近圓心)
        # 這裡模擬前方扇形區域 (240度 ~ 300度之間隨機)
        # 因為只有一個超聲波，無法得知確切角度，故做視覺模擬
        r = (distance_cm / 50.0) * max_radius
        theta = random.uniform(250, 290) # 上方隨機角度
        rad = math.radians(theta)
        
        x = cx + r * math.cos(rad)
        y = cy + r * math.sin(rad)
        
        # 加入新光點 (透明度 255)
        self.blips.append((x, y, 255, time.time()))

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        w, h = self.width(), self.height()
        cx, cy = w / 2, h / 2
        radius = min(w, h) / 2 - 10

        # 1. 背景 (深色雷達盤)
        painter.setBrush(QColor(15, 23, 42)) # #0f172a
        painter.setPen(QPen(QColor(34, 211, 238), 2)) # 外框 Cyan
        painter.drawEllipse(QPointF(cx, cy), radius, radius)

        # 2. 網格圈圈 (同心圓)
        pen_grid = QPen(QColor(56, 189, 248, 80)) # 淡藍色，半透明
        pen_grid.setWidth(1)
        pen_grid.setStyle(Qt.DashLine)
        painter.setPen(pen_grid)
        painter.setBrush(Qt.NoBrush)
        
        painter.drawEllipse(QPointF(cx, cy), radius * 0.33, radius * 0.33)
        painter.drawEllipse(QPointF(cx, cy), radius * 0.66, radius * 0.66)
        
        # 3. 十字瞄準線
        painter.drawLine(cx, cy - radius, cx, cy + radius)
        painter.drawLine(cx - radius, cy, cx + radius, cy)

        # 4. 掃描線 (漸層扇形)
        # QConicalGradient 能夠畫出雷達掃描拖影效果
        gradient = QConicalGradient(cx, cy, -self.angle)
        # 0.0 是起始角度顏色，0.1 是拖影尾巴，其他透明
        gradient.setColorAt(0.0, QColor(34, 211, 238, 180)) # 掃描頭 (亮青色)
        gradient.setColorAt(0.15, QColor(34, 211, 238, 0))  # 尾巴漸層透明
        gradient.setColorAt(1.0, QColor(34, 211, 238, 0))
        
        painter.setBrush(QBrush(gradient))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(QPointF(cx, cy), radius, radius)

        # 5. 繪製偵測點 (Blips)
        for bx, by, opacity, ts in self.blips:
            # 光點主體 (紅色)
            painter.setBrush(QColor(239, 68, 68, int(opacity)))
            painter.setPen(Qt.NoPen)
            painter.drawEllipse(QPointF(bx, by), 6, 6)
            
            # 光點擴散圈 (動畫效果)
            glow_radius = 6 + (255 - opacity) * 0.1
            painter.setBrush(Qt.NoBrush)
            painter.setPen(QPen(QColor(239, 68, 68, int(opacity/2)), 1))
            painter.drawEllipse(QPointF(bx, by), glow_radius, glow_radius)

# ==========================================
#  設定視窗 (Settings Dialog)
# ==========================================
class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("SYSTEM CONFIG // 系統設定")
        self.resize(400, 250)
        # 這裡可以再次套用 config.DARK_STYLESHEET 確保風格一致
        self.setStyleSheet(config.DARK_STYLESHEET)
        
        layout = QFormLayout()
        layout.setLabelAlignment(Qt.AlignRight)
        
        self.input_baud = QLineEdit(str(config.BAUD_RATE))
        self.input_cmd_f = QLineEdit(config.CMD_FORWARD)
        self.input_cmd_b = QLineEdit(config.CMD_BACKWARD)
        
        layout.addRow("BAUD RATE:", self.input_baud)
        layout.addRow("CMD FORWARD:", self.input_cmd_f)
        layout.addRow("CMD BACKWARD:", self.input_cmd_b)
        
        btn_save = QPushButton("SAVE CONFIG")
        btn_save.clicked.connect(self.accept)
        layout.addRow(btn_save)
        
        self.setLayout(layout)

# ==========================================
#  主視窗 (Main Window)
# ==========================================
class Esp32CamWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.video_thread = None
        self.serial_manager = SerialManager()
        self.current_port = None
        self.serial_enabled = True
        self.last_key_cmd = None
        
        self.init_ui()
        self.refresh_ports()
        self.init_timer()

    def init_ui(self):
        self.setWindowTitle("TACTICAL DASHBOARD v10.0")
        self.resize(config.DEFAULT_WIDTH, config.DEFAULT_HEIGHT)
        
        # 套用設定檔中的暗黑樣式
        self.setStyleSheet(config.DARK_STYLESHEET)

        # 中心容器
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # 主佈局：水平分割 (左：影像 / 右：儀表板)
        main_layout = QHBoxLayout()
        main_layout.setSpacing(20)
        main_layout.setContentsMargins(20, 20, 20, 20)
        central_widget.setLayout(main_layout)

        # ------------------------------------------------
        # [左側面板] 影像監控區 (佔寬度 70%)
        # ------------------------------------------------
        left_panel = QVBoxLayout()
        
        # 1. 頂部資訊列 (Header)
        header_layout = QHBoxLayout()
        self.lbl_title = QLabel("SYSTEM STATUS: ONLINE")
        self.lbl_title.setObjectName("HeaderTitle") # 對應 CSS ID
        
        self.lbl_clock = QLabel("00:00:00")
        self.lbl_clock.setObjectName("HeaderClock") # 對應 CSS ID
        self.lbl_clock.setAlignment(Qt.AlignRight | Qt.AlignBottom)
        
        header_layout.addWidget(self.lbl_title)
        header_layout.addStretch()
        header_layout.addWidget(self.lbl_clock)
        left_panel.addLayout(header_layout)

        # 2. 影像顯示區 (Video Feed)
        self.video_label = QLabel("NO SIGNAL INPUT")
        self.video_label.setObjectName("VideoLabel") # 對應 CSS ID
        self.video_label.setAlignment(Qt.AlignCenter)
        self.video_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.video_label.setScaledContents(True)
        self.video_label.setMinimumSize(640, 480)
        # 預設樣式：灰色文字，虛線邊框
        self.video_label.setStyleSheet("color: #475569; font-size: 24px; font-weight: bold; border: 2px dashed #334155;")
        left_panel.addWidget(self.video_label)
        
        # 3. 系統日誌 (Log)
        self.text_log = QPlainTextEdit()
        self.text_log.setReadOnly(True)
        self.text_log.setMaximumHeight(150)
        self.text_log.setPlaceholderText("Initializing System Logs...")
        left_panel.addWidget(self.text_log)

        main_layout.addLayout(left_panel, 7) # 權重 7

        # ------------------------------------------------
        # [右側面板] 戰術儀表板 (佔寬度 30%)
        # ------------------------------------------------
        right_panel = QVBoxLayout()
        right_panel.setSpacing(15)

        # 1. 雷達與感測器 (Radar & Sensors)
        group_radar = QGroupBox("RADAR // SENSORS")
        layout_radar = QVBoxLayout()
        layout_radar.setAlignment(Qt.AlignCenter)
        
        # 加入我們自定義的 RadarWidget
        self.radar_widget = RadarWidget()
        layout_radar.addWidget(self.radar_widget)
        
        # 距離數值顯示
        self.lbl_dist = QLabel("DIST: --.-- CM")
        self.lbl_dist.setStyleSheet("font-size: 18px; font-weight: bold; color: #22d3ee; margin-top: 10px; font-family: Consolas;")
        self.lbl_dist.setAlignment(Qt.AlignCenter)
        layout_radar.addWidget(self.lbl_dist)
        
        group_radar.setLayout(layout_radar)
        right_panel.addWidget(group_radar)

        # 2. 連線控制 (Network)
        group_conn = QGroupBox("NETWORK // CONNECTION")
        layout_conn = QVBoxLayout()
        
        h_port = QHBoxLayout()
        self.combo_ports = QComboBox()
        self.combo_ports.currentIndexChanged.connect(self.on_port_changed)
        
        btn_refresh = QPushButton("R") # 重新整理
        btn_refresh.setFixedWidth(40)
        btn_refresh.setToolTip("Refresh Ports")
        btn_refresh.clicked.connect(self.refresh_ports)
        
        h_port.addWidget(self.combo_ports)
        h_port.addWidget(btn_refresh)
        
        self.input_ip = QLineEdit()
        self.input_ip.setPlaceholderText("192.168.X.X")
        
        self.btn_connect = QPushButton("ESTABLISH LINK")
        self.btn_connect.clicked.connect(self.start_video)
        
        layout_conn.addLayout(h_port)
        layout_conn.addWidget(self.input_ip)
        layout_conn.addWidget(self.btn_connect)
        group_conn.setLayout(layout_conn)
        right_panel.addWidget(group_conn)

        # 3. 載具控制 (Manual Control)
        group_control = QGroupBox("MANUAL OVERRIDE")
        layout_control = QGridLayout()
        layout_control.setSpacing(8)

        # 建立 WASD 按鈕
        self.btn_up = self.create_nav_btn("W", config.CMD_FORWARD)
        self.btn_left = self.create_nav_btn("A", config.CMD_LEFT)
        self.btn_stop = self.create_nav_btn("S", config.CMD_STOP)
        self.btn_right = self.create_nav_btn("D", config.CMD_RIGHT)
        self.btn_down = self.create_nav_btn("X", config.CMD_BACKWARD)

        # Grid 排列：
        #   W
        # A S D
        #   X
        layout_control.addWidget(self.btn_up, 0, 1)
        layout_control.addWidget(self.btn_left, 1, 0)
        layout_control.addWidget(self.btn_stop, 1, 1)
        layout_control.addWidget(self.btn_right, 1, 2)
        layout_control.addWidget(self.btn_down, 2, 1)
        
        # 額外功能鍵 (車燈)
        self.btn_light = QPushButton("TOGGLE LIGHTS")
        self.btn_light.setCheckable(True)
        self.btn_light.clicked.connect(self.toggle_light)
        layout_control.addWidget(self.btn_light, 3, 0, 1, 3) # 跨欄

        group_control.setLayout(layout_control)
        right_panel.addWidget(group_control)

        # 4. 系統工具 (System Tools)
        group_sys = QGroupBox("SYSTEM TOOLS")
        layout_sys = QHBoxLayout()
        
        btn_settings = QPushButton("CONFIG")
        btn_settings.clicked.connect(self.open_settings)
        
        btn_upload = QPushButton("FLASH FW")
        btn_upload.clicked.connect(self.on_upload_clicked)
        
        layout_sys.addWidget(btn_settings)
        layout_sys.addWidget(btn_upload)
        group_sys.setLayout(layout_sys)
        right_panel.addWidget(group_sys)

        main_layout.addLayout(right_panel, 3) # 權重 3

        # 啟動時鐘 Timer (每秒更新)
        self.clock_timer = QTimer(self)
        self.clock_timer.timeout.connect(self.update_clock)
        self.clock_timer.start(1000)

    # ==========================================
    #  邏輯功能實作
    # ==========================================
    
    def update_clock(self):
        current_time = time.strftime("%H:%M:%S")
        self.lbl_clock.setText(f"TIME: {current_time}")

    def create_nav_btn(self, text, command):
        btn = QPushButton(text)
        btn.setObjectName("NavBtn") # 對應 CSS ID (config.py)
        btn.setFixedSize(50, 50)
        # 按下時發送指令
        btn.pressed.connect(lambda: self.send_command(command))
        # 放開時停止 (若不需要自動停止可註解掉下面這行)
        btn.released.connect(lambda: self.send_command(config.CMD_STOP))
        return btn

    def open_settings(self):
        dlg = SettingsDialog(self)
        dlg.exec()

    # --- 鍵盤控制 (WASD) ---
    def keyPressEvent(self, event: QKeyEvent):
        if event.isAutoRepeat(): return
        key = event.key()
        cmd = None
        
        # 映射按鍵
        if key == Qt.Key_W or key == Qt.Key_Up: cmd = config.CMD_FORWARD
        elif key == Qt.Key_X or key == Qt.Key_Down: cmd = config.CMD_BACKWARD
        elif key == Qt.Key_S: cmd = config.CMD_STOP
        elif key == Qt.Key_A or key == Qt.Key_Left: cmd = config.CMD_LEFT
        elif key == Qt.Key_D or key == Qt.Key_Right: cmd = config.CMD_RIGHT
        elif key == Qt.Key_Space: cmd = config.CMD_STOP
        
        if cmd: 
            self.send_command(cmd)
            self.update_btn_style(cmd, True)

    def keyReleaseEvent(self, event: QKeyEvent):
        if event.isAutoRepeat(): return
        key = event.key()
        move_keys = [Qt.Key_W, Qt.Key_X, Qt.Key_S, Qt.Key_A, Qt.Key_D, 
                     Qt.Key_Up, Qt.Key_Down, Qt.Key_Left, Qt.Key_Right]
        if key in move_keys:
            self.send_command(config.CMD_STOP)
            self.update_btn_style(config.CMD_STOP, False)

    def update_btn_style(self, cmd, pressed):
        btn = None
        if cmd == config.CMD_FORWARD: btn = self.btn_up
        elif cmd == config.CMD_BACKWARD: btn = self.btn_down
        elif cmd == config.CMD_LEFT: btn = self.btn_left
        elif cmd == config.CMD_RIGHT: btn = self.btn_right
        
        if btn: btn.setDown(pressed)

    def send_command(self, cmd):
        if self.last_key_cmd == cmd: return
        
        if self.serial_manager.ser and self.serial_manager.ser.is_open:
            try:
                self.serial_manager.ser.write(cmd.encode())
                self.last_key_cmd = cmd
                if cmd != config.CMD_STOP:
                    self.append_log(f"> CMD SENT: {cmd}")
            except: pass
        else:
            # 沒連線時的 Debug
            # self.append_log(f"[DEBUG] CMD: {cmd}")
            pass

    def toggle_light(self):
        if self.btn_light.isChecked():
            self.send_command(config.CMD_LIGHT_ON)
            self.btn_light.setText("LIGHTS OFF")
            # 燈亮時按鈕變亮青色
            self.btn_light.setStyleSheet("color: #000; background-color: #22d3ee; border-color: #22d3ee;")
        else:
            self.send_command(config.CMD_LIGHT_OFF)
            self.btn_light.setText("LIGHTS ON")
            self.btn_light.setStyleSheet("") # 回復預設

    # --- 核心連接與 Log ---
    def append_log(self, msg: str):
        self.text_log.appendPlainText(msg.rstrip("\n"))
        self.text_log.moveCursor(QTextCursor.End)
        
        # ★ 雷達數據解析 ★
        # 格式範例: "DIST: 20.5"
        if "DIST:" in msg:
            try:
                parts = msg.split(":")
                dist = float(parts[1].strip().split(" ")[0])
                self.lbl_dist.setText(f"DIST: {dist:.2f} CM")
                
                # 在雷達上新增光點
                self.radar_widget.add_blip(dist)
                
                # 距離警示 (小於 15cm 變紅)
                if dist < 15:
                    self.lbl_dist.setStyleSheet("font-size: 18px; font-weight: bold; color: #ef4444; margin-top: 10px; font-family: Consolas;")
                else:
                    self.lbl_dist.setStyleSheet("font-size: 18px; font-weight: bold; color: #22d3ee; margin-top: 10px; font-family: Consolas;")
            except: pass

    def start_video(self):
        ip = self.input_ip.text().strip()
        if not ip: 
            # 沒輸入 IP 時閃爍輸入框提示
            self.input_ip.setFocus()
            return
        
        # 處理 URL
        if not ip.startswith("http"): url = f"http://{ip}:81/stream" 
        elif ip.startswith("http://") and ":" not in ip[7:]: url = ip.rstrip('/') + ':81/stream' 
        else: url = ip.rstrip('/') + ('/stream' if not ip.endswith('/stream') else '')

        self.append_log(f"CONNECTING TO FEED: {url}")
        self.video_label.setText("CONNECTING...")
        self.video_label.setStyleSheet("color: #22d3ee; font-size: 24px; font-weight: bold; border: 2px solid #22d3ee;")
        
        if self.video_thread: self.video_thread.stop()
        self.video_thread = VideoThread(url)
        self.video_thread.change_pixmap_signal.connect(self.update_image)
        self.video_thread.status_signal.connect(self.update_video_status)
        self.video_thread.start()

    def update_image(self, img):
        self.video_label.setPixmap(QPixmap.fromImage(img))
        # 連線成功：實線青色邊框
        self.video_label.setStyleSheet("background-color: #000; border: 2px solid #22d3ee; border-radius: 4px;")

    def update_video_status(self, msg):
        self.append_log(msg)
        if "❌" in msg:
            self.video_label.clear()
            self.video_label.setText("SIGNAL LOST")
            # 斷線：紅色虛線邊框
            self.video_label.setStyleSheet("color: #ef4444; font-size: 24px; font-weight: bold; border: 2px dashed #ef4444;")

    def refresh_ports(self):
        self.serial_manager.disconnect()
        self.combo_ports.clear()
        ports = self.serial_manager.get_ports()
        for p in ports: self.combo_ports.addItem(f"{p.device}")
        if ports: self.on_port_changed()

    def on_port_changed(self):
        text = self.combo_ports.currentText()
        if text:
            self.current_port = text.split(" - ")[0]
            self.reopen_serial()

    def reopen_serial(self):
        if not self.current_port or not self.serial_enabled: return
        success, msg = self.serial_manager.connect(self.current_port)
        self.append_log(msg)

    def force_bootloader(self):
        if not self.current_port: return
        self.serial_manager.send_boot_signal(self.current_port)
        self.reopen_serial()

    def on_upload_clicked(self):
        if not self.current_port: return
        success, msg = prepare_sketch()
        if not success:
            self.append_log(msg)
            return
        self.serial_enabled = False
        self.serial_manager.disconnect()
        self.append_log(">>> UPLOADING FIRMWARE...")
        QApplication.processEvents()
        time.sleep(1)
        compile_and_upload(self.current_port, self.append_log)
        time.sleep(3)
        self.serial_enabled = True
        self.reopen_serial()

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
                if ip_match: self.input_ip.setText(ip_match.group())

    def closeEvent(self, event):
        if self.video_thread: self.video_thread.stop()
        self.serial_manager.disconnect()
        event.accept()