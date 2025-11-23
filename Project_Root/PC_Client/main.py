import sys
from PySide6.QtWidgets import QApplication
from gui import Esp32CamWindow

if __name__ == "__main__":
    # 建立 Qt 應用程式實例
    app = QApplication.instance() or QApplication(sys.argv)
    
    # 顯示主視窗
    window = Esp32CamWindow()
    window.show()
    
    # 進入事件迴圈
    sys.exit(app.exec())