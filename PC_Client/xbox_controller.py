import pygame
import time

# Xbox 手把按鈕和搖桿的對應編號 (可能因作業系統有些微差異)
# 可透過執行此腳本並操作手把來驗證
AXIS_LEFT_STICK_X = 0
AXIS_LEFT_STICK_Y = 1
AXIS_RIGHT_STICK_X = 2
AXIS_RIGHT_STICK_Y = 3
AXIS_LEFT_TRIGGER = 4
AXIS_RIGHT_TRIGGER = 5

BUTTON_A = 0
BUTTON_B = 1
BUTTON_X = 2
BUTTON_Y = 3
BUTTON_LEFT_BUMPER = 4
BUTTON_RIGHT_BUMPER = 5
BUTTON_BACK = 6
BUTTON_START = 7
BUTTON_LEFT_STICK = 8
BUTTON_RIGHT_STICK = 9

# 搖桿的「死區」(deadzone) 設定，避免輕微晃動造成的誤判
JOYSTICK_DEADZONE = 0.15

class XboxController:
    """
    用於處理 Xbox 手把輸入的類別。
    """
    def __init__(self):
        pygame.init()
        pygame.joystick.init()

        joystick_count = pygame.joystick.get_count()
        if joystick_count == 0:
            print("錯誤：未偵測到任何手把。")
            self.joystick = None
            return

        # 初始化第一個偵測到的手把
        self.joystick = pygame.joystick.Joystick(0)
        self.joystick.init()
        print(f"成功初始化手把: {self.joystick.get_name()}")

    def get_input(self):
        """
        處理手把事件並回傳當前狀態。
        回傳一個字典，包含搖桿和按鈕的狀態。
        """
        if not self.joystick:
            return None

        for event in pygame.event.get():
            # 處理關閉事件
            if event.type == pygame.QUIT:
                return "QUIT"

        # 讀取搖桿軸心數值
        left_stick_x = self.joystick.get_axis(AXIS_LEFT_STICK_X)
        left_stick_y = self.joystick.get_axis(AXIS_LEFT_STICK_Y)

        if abs(left_stick_x) < JOYSTICK_DEADZONE:
            left_stick_x = 0.0
        if abs(left_stick_y) < JOYSTICK_DEADZONE:
            left_stick_y = 0.0

        # 讀取按鈕狀態
        button_a_pressed = self.joystick.get_button(BUTTON_A)
        button_b_pressed = self.joystick.get_button(BUTTON_B)

        # 讀取方向鍵 (hat)
        hat_x, hat_y = self.joystick.get_hat(0)

        return {
            "left_stick_x": left_stick_x,
            "left_stick_y": -left_stick_y,  # Pygame Y軸是反的，通常向上為正
            "button_a": button_a_pressed,
            "button_b": button_b_pressed,
            "dpad_x": hat_x,
            "dpad_y": hat_y
        }

def main():
    """
    主執行函數，用於測試手把輸入。
    """
    controller = XboxController()
    if not controller.joystick:
        return

    running = True
    while running:
        controller_state = controller.get_input()

        if controller_state == "QUIT":
            running = False
            continue

        if controller_state:
            # --- 在這裡將手把狀態轉換為具體指令 ---
            # 範例：將左搖桿 Y 軸轉換為馬達速度
            motor_speed = int(controller_state["left_stick_y"] * 100)

            # 範例：將左搖桿 X 軸轉換為轉向
            steering = int(controller_state["left_stick_x"] * 100)

            # 範例：將 A 按鈕作為一個觸發器
            action_triggered = controller_state["button_a"] == 1

            # TODO: 將這些指令發送到你的 serial_worker 或其他邏輯中
            # 例如: serial_worker.send_command(f"M:{motor_speed},S:{steering}")
            # if action_triggered:
            #     serial_worker.send_command("ACTION:FIRE")

            # 為了方便測試，我們先印出來
            print(f"左搖桿 X: {steering:4d}, 左搖桿 Y: {motor_speed:4d}, 按鈕A: {action_triggered}", end='\r')


        # 控制迴圈更新頻率，避免 CPU 佔用過高
        time.sleep(0.02)

    pygame.quit()
    print("\n程式結束。")


if __name__ == '__main__':
    main()