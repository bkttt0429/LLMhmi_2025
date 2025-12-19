import machine
import time

class SonarOnePin:
    def __init__(self, pin_num):
        """
        初始化單腳超聲波感測器
        :param pin_num: 連接 SIG 的 GPIO 編號 (例如 ESP8266 D1=5, D2=4)
        """
        self.pin_num = pin_num
        # 這裡不預先設定 Pin 模式，因為需要在測量時動態切換

    def measure_cm(self):
        """
        執行測距並返回公分 (cm)
        :return: 距離(cm)，若超時或錯誤則返回 -1
        """
        # 1. 設定為輸出模式 (OUTPUT) 以發送觸發訊號
        # 注意：每次測量前都要重新建立 Pin 物件或重新設定模式
        sig_pin = machine.Pin(self.pin_num, machine.Pin.OUT)
        
        # 2. 發送 Trigger 脈衝
        # 先拉低確保乾淨的信號
        sig_pin.value(0)
        time.sleep_us(2)
        
        # 拉高 10us (標準觸發時間)
        sig_pin.value(1)
        time.sleep_us(10)
        
        # 拉低結束觸發
        sig_pin.value(0)
        
        # 3. 立即切換為輸入模式 (INPUT) 以讀取 Echo
        # 這一步必須非常快，以便捕捉感測器回傳的高電位訊號
        sig_pin.init(machine.Pin.IN)
        
        try:
            # 4. 測量脈衝寬度 (等待高電位 pulse)
            # timeout_us=30000 (30ms) 大約對應 5公尺距離，避免無限等待
            duration_us = machine.time_pulse_us(sig_pin, 1, 30000)
            
            # 處理超時 (time_pulse_us 在某些版本超時會返回負數)
            if duration_us < 0:
                return -1
                
            # 5. 計算距離
            # 聲速約 340m/s = 0.0343 cm/us
            # 距離 = (時間 * 聲速) / 2 (來回)
            distance_cm = (duration_us * 0.0343) / 2
            return distance_cm
            
        except OSError as e:
            # ESP8266 若 time_pulse_us 超時可能會拋出 OSError: [Errno 110] ETIMEDOUT
            return -1

class VibrationSensor:
    def __init__(self, pin_num):
        """
        Vibration/Shake Sensor (e.g. SW-420)
        DIGITAL OUTPUT
        """
        self.pin = machine.Pin(pin_num, machine.Pin.IN)

    def is_vibrating(self):
        """Returns True if vibration currently detected"""
        return self.pin.value() == 1
