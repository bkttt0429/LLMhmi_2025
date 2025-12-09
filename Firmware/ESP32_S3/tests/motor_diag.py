"""
Motor Diagnosis Script (motor_diag.py)
用于诊断 ESP32 遥控车的电机接线和极性问题
"""
import requests
import time
import sys

# Default IP - can be changed
ESP32_IP = "10.243.115.133"
API_URL = f"http://{ESP32_IP}/motor"

def send_pwm(left, right, duration=1.0):
    """发送 PWM 指令，等待一段时间，然后停止"""
    try:
        # 1. Send Command
        print(f"   >>> 发送: Left={left}, Right={right} ... ", end="", flush=True)
        requests.get(API_URL, params={"left": left, "right": right}, timeout=1.0)
        print("OK")
        
        # 2. Wait for motor to move
        time.sleep(duration)
        
        # 3. Stop
        # print("   >>> 自动停止")
        requests.get(API_URL, params={"left": 0, "right": 0}, timeout=1.0)
        
    except Exception as e:
        print(f"\n❌ 通信错误: {e}")
        print("请检查 ESP32 是否在线，IP 是否正确。")
        sys.exit(1)

def ask_choice(prompt, options):
    """询问用户选择"""
    while True:
        try:
            val = input(f"{prompt} ({'/'.join(options)}): ").strip().upper()
            if val in options:
                return val
        except KeyboardInterrupt:
            sys.exit(0)

def main():
    global ESP32_IP, API_URL
    print("="*60)
    print("🛠️  ESP32 遥控车电机诊断工具 (Motor Diag)")
    print("="*60)
    
    ip_in = input(f"请输入 ESP32 IP [{ESP32_IP}]: ").strip()
    if ip_in:
        ESP32_IP = ip_in
        API_URL = f"http://{ESP32_IP}/motor"

    print("\n⚠️  注意：测试即将开始。车子将会转动 1-2 秒。")
    print("请确保车轮悬空或有足够空间。\n")
    input("按 Enter 开始测试...")

    # Lookups for logic
    # We assume the user wants:
    # app_motor_set_pwm(left_val, right_val) ->
    #   Left val controls Left Wheel Forward
    #   Right val controls Right Wheel Forward

    # === Test 1: Send LEFT Control ===
    print("\n" + "-"*40)
    print("测试 1: 發送左通道指令 (Left=200, Right=0)")
    print("-" * 40)
    send_pwm(200, 0, duration=1.5)
    
    t1_wheel = ask_choice("❓ 哪一個輪子在轉？ [L=左輪, R=右輪, N=沒反應]", ['L', 'R', 'N'])
    if t1_wheel == 'N':
        print("❌ 錯誤：馬達沒反應，請檢查電源或接線。")
        return

    t1_dir = ask_choice("❓ 轉動方向？ [F=前進, B=後退]", ['F', 'B'])

    # === Test 2: Send RIGHT Control ===
    print("\n" + "-"*40)
    print("測試 2: 發送右通道指令 (Left=0, Right=200)")
    print("-" * 40)
    send_pwm(0, 200, duration=1.5)
    
    t2_wheel = ask_choice("❓ 哪一個輪子在轉？ [L=左輪, R=右輪, N=沒反應]", ['L', 'R', 'N'])
    if t2_wheel == 'N':
        print("❌ 錯誤：馬達沒反應，請檢查電源或接線。")
        return
        
    t2_dir = ask_choice("❓ 轉動方向？ [F=前進, B=後退]", ['F', 'B'])
    
    # === Analysis ===
    print("\n" + "="*60)
    print("📊 診斷結果分析")
    print("="*60)
    
    # Logic:
    # We want Left_Input -> Left_Wheel (Forward)
    # We want Right_Input -> Right_Wheel (Forward)
    
    # Determine SWAP needed?
    # Sent Left -> Moved t1_wheel
    # Sent Right -> Moved t2_wheel
    
    swap_needed = False
    
    if t1_wheel == 'L' and t2_wheel == 'R':
        print("✅ 接線順序正確 (左指令->左輪, 右指令->右輪)")
        swap_needed = False
    elif t1_wheel == 'R' and t2_wheel == 'L':
        print("⚠️ 接線順序相反 (左指令->右輪, 右指令->左輪)")
        print("   -> 需要在代碼中交換通道 (SWAP)")
        swap_needed = True
    else:
        print(f"❌ 接線異常：左指令->{t1_wheel}, 右指令->{t2_wheel}")
        print("   無法自動生成修復代碼，請檢查硬體。")
        return

    # Determine Inversion needed?
    # We need to look at the direction relative to the corrected channel
    
    invert_left = False
    invert_right = False
    
    # If swap is needed, it means Left Input maps to Right Hardware Channel (physically Left Wheel)
    # But let's simplify:
    # If I sent "Forward(200)", did it go "Forward"?
    
    if t1_dir == 'B': # Left Input produced Backward motion
        print("⚠️ 左通道極性反轉 (需要修正方向)")
        invert_left = True
    else:
        print("✅ 左通道方向正確")

    if t2_dir == 'B': # Right Input produced Backward motion
        print("⚠️ 右通道極性反轉 (需要修正方向)")
        invert_right = True
    else:
        print("✅ 右通道方向正確")

    # === Generate Code ===
    print("\n" + "="*60)
    print("🛠️  建議修復代碼 (app_motor.c)")
    print("="*60)
    print("請將 app_motor_set_pwm 函數替換為以下內容：\n")
    
    code = "void app_motor_set_pwm(int left_val, int right_val)\n{\n"
    code += "    // Input range: -255 to 255\n"
    code += "    // Map to 1000..2000\n\n"
    code += "    // [Diagnostic Fix]\n"
    
    # Logic construction
    # We are defining l_us and r_us.
    # Standard: l_us uses left_val, r_us uses right_val
    # Swap: l_us uses right_val, r_us uses left_val
    
    src_l = "left_val"
    src_r = "right_val"
    
    if swap_needed:
        src_l = "right_val"
        src_r = "left_val"
        code += "    // Swap applied due to crossed wiring\n"
    else:
        code += "    // No swap needed\n"
        
    # Mapping
    # Standard: map_range(val, -255, 255, MIN, MAX)
    # Invert: map_range(val, -255, 255, MAX, MIN)
    
    # Left Channel Logic
    # Note: If swapped, src_l is right_val. This goes to LEFT_CHANNEL.
    # Does 'invert_left' mean we invert the LEFT COMMAND or the LEFT CHANNEL?
    # Our test was: "Left Command produced Backward". We want "Left Command produces Forward".
    # So we must invert the MAPPING of the Left Command.
    
    # Wait. If SWAPPED:
    # Left Command -> Right Wheel (Backwards).
    # We want Left Command -> Left Wheel (Forwards).
    # 1. Swap: Route Left Command to Left Wheel (which is connected to 'Right Channel' in current firmware... wait).
    
    # Let's rely on the inputs again.
    # Current Firmware State (CFS).
    # CFS_L = Map(R_in) [based on step 569]
    # CFS_R = Map(L_in)
    
    # User runs test on CFS.
    # Send L_in=200, R_in=0.
    # CFS sets CFS_R = Map(200) = Mid+?
    # CFS sets RIGHT_CHANNEL to 200-mapped.
    # Result: t1_wheel moved.
    
    # This is getting complicated because we don't know if user updated firmware.
    # BUT, the script generates code for *app_motor.c* which defines the MAPPING.
    # The generated code will define the transformation from (left_val, right_val) to (LEFT_CHANNEL_PWM, RIGHT_CHANNEL_PWM).
    
    # Let's abstract:
    # We want: left_val > 0  => Left Wheel Forward.
    # We want: right_val > 0 => Right Wheel Forward.
    
    # Test 1 result: left_val > 0 => t1_wheel t1_dir.
    # If t1_wheel is 'R': Left CMD currently moves Right Wheel.
    #   To move Left Wheel, we likely need to touch the OTHER channel. 
    #   So 'Left Input' should go to 'The Channel that drives Left Wheel'.
    #   Since Left Cmd drove Right Wheel, the *Current Channel for Left Cmd* is wrong.
    #   Wait, assuming "One channel per wheel".
    #   If L_cmd -> R_wheel. Then R_cmd MUST -> L_wheel (unless wiring is really weird).
    #   Let's check t2_wheel.
    #   If t1=R and t2=L. SWAP needed.
    #   This implies: Left_Input should go to the Channel that R_Input was using.
    #   Right_Input should go to the Channel that L_Input was using.
    
    #   Current Code (CC):
    #   CC maps L_Input to Channel_A.
    #   CC maps R_Input to Channel_B.
    #   Result: Channel_A drives R_wheel. Channel_B drives L_wheel.
    #   Goal: Drive L_wheel with L_Input.
    #   Since Channel_B drives L_wheel, we want L_Input -> Channel_B.
    #   So we want to assign L_Input to the variable for Channel_B.
    
    #   Let's assume the generated code uses variables 'l_us' (for LEFT_CHANNEL) and 'r_us' (for RIGHT_CHANNEL).
    #   If Swap Needed:
    #       l_us needs R_Input? No. 
    #       Channel B (Right Channel) drives Left Wheel.
    #       We want Left Input to drive Left Wheel.
    #       So Left Input -> Channel B.
    #       So r_us = map(left_val...)
    #       And l_us = map(right_val...)
    #   This matches my "swap_needed" logic above.
    
    # Inversion:
    #   We routed L_Input to Channel_B (Left Wheel).
    #   Previous test: R_Input -> Channel_B -> Left Wheel. Dir = t2_dir.
    #   So "Positive Input to Channel B" produces motion "t2_dir".
    #   We want "Forward".
    #   If t2_dir == 'B' (Backward), then Channel B is inverted.
    #   So we must Invert the mapping to Channel B.
    #   Channel B corresponds to `r_us` in my variable naming (RIGHT_CHANNEL).
    #   So `r_us` mapping must be inverted.
    
    #   Similarly for Channel A (Right Wheel).
    #   L_Input -> Channel_A -> Right Wheel. Dir = t1_dir.
    #   If t1_dir == 'B', Channel A is inverted.
    #   Channel A is `l_us` (LEFT_CHANNEL).
    #   So `l_us` mapping must be inverted.

    # Re-evaluating logic based on t1/t2 results:
    
    # Case 1: L_in -> L_wheel (t1=L).
    #   No swap.
    #   L_Input -> Channel_A (l_us).
    #   Dir = t1_dir.
    #   If t1_dir == B, Invert l_us.
    
    # Case 2: L_in -> R_wheel (t1=R).
    #   Swap.
    #   L_Input -> Channel_B (r_us).  (Because Channel B is the one driving Left Wheel? No!)
    #   Wait. L_Input drove R_Wheel via Channel_A (presumably).
    #   R_Input drove L_Wheel via Channel_B (presumably).
    #   So Channel_A = R_Wheel. Channel_B = L_Wheel.
    #   We want L_Input -> L_Wheel (Channel_B). So r_us = map(L_Input).
    #   We want R_Input -> R_Wheel (Channel_A). So l_us = map(R_Input).
    
    #   Check Direction:
    #   R_Input -> Channel_B -> L_Wheel. Result was t2_dir.
    #   We want L_Input -> Channel_B to be Forward.
    #   If t2_dir == B, then Channel_B needs Invert. 
    #   So r_us mapping (now taking L_Input) needs Invert.
    
    #   L_Input -> Channel_A -> R_Wheel. Result was t1_dir.
    #   We want R_Input -> Channel_A to be Forward.
    #   If t1_dir == B, then Channel_A needs Invert.
    #   So l_us mapping (now taking R_Input) needs Invert.
    
    # Summary of Generation Logic:
    
    target_l_us_input = "" # Input variable name for l_us
    target_r_us_input = "" # Input variable name for r_us
    
    inv_l_us = False # Whether to invert l_us map
    inv_r_us = False # Whether to invert r_us map
    
    if t1_wheel == 'L': # No Swap. Channel A = Left, Channel B = Right
        target_l_us_input = "left_val"
        target_r_us_input = "right_val"
        if t1_dir == 'B': inv_l_us = True # L_in->L_wheel was Back
        if t2_dir == 'B': inv_r_us = True # R_in->R_wheel was Back
        
    else: # Swap. Channel A = Right, Channel B = Left
        # We need l_us (Channel A, Right Wheel) to take Right Input
        target_l_us_input = "right_val"
        # We need r_us (Channel B, Left Wheel) to take Left Input
        target_r_us_input = "left_val"
        
        # Polarity?
        # Channel A (Right Wheel) was driven by Left Cmd (test 1). Result t1_dir.
        # We want meaningful Forward.
        if t1_dir == 'B': inv_l_us = True
        
        # Channel B (Left Wheel) was driven by Right Cmd (test 2). Result t2_dir.
        if t2_dir == 'B': inv_r_us = True
    
    # Generate C lines
    
    # l_us block
    min_s, max_s = "SERVO_MIN_US", "SERVO_MAX_US"
    if inv_l_us:
        code += f"    int l_us = map_range({target_l_us_input}, -255, 255, {max_s}, {min_s}); // Inverted\n"
    else:
        code += f"    int l_us = map_range({target_l_us_input}, -255, 255, {min_s}, {max_s});\n"
        
    # r_us block
    if inv_r_us:
        code += f"    int r_us = map_range({target_r_us_input}, -255, 255, {max_s}, {min_s}); // Inverted\n"
    else:
        code += f"    int r_us = map_range({target_r_us_input}, -255, 255, {min_s}, {max_s});\n"

    code += "\n    ledc_set_duty(PWM_MODE, LEFT_CHANNEL, us_to_duty(l_us));\n"
    code += "    ledc_update_duty(PWM_MODE, LEFT_CHANNEL);\n\n"
    code += "    ledc_set_duty(PWM_MODE, RIGHT_CHANNEL, us_to_duty(r_us));\n"
    code += "    ledc_update_duty(PWM_MODE, RIGHT_CHANNEL);\n"
    code += "}\n"
    
    print(code)
    print("="*60)

if __name__ == "__main__":
    main()
