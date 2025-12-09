"""
Motor Direction Test Script
测试电机方向映射，确定是否需要反转左轮或右轮
"""
import requests
import time

ESP32_IP = "10.243.115.133"  # 根据终端日志中的IP

def test_motor(left, right, description):
    """发送电机命令并等待"""
    url = f"http://{ESP32_IP}/motor"
    params = {"left": left, "right": right}
    
    print(f"\n{'='*60}")
    print(f"测试: {description}")
    print(f"发送: Left={left}, Right={right}")
    print(f"URL: {url}")
    print(f"{'='*60}")
    
    try:
        resp = requests.get(url, params=params, timeout=2.0)
        if resp.status_code == 200:
            print(f"✅ ESP32 回应: {resp.text}")
        else:
            print(f"❌ ESP32 错误: {resp.status_code}")
    except Exception as e:
        print(f"❌ 连接错误: {e}")
    
    print(f"请观察车子的动作，然后按 Enter 继续...")
    input()

if __name__ == "__main__":
    print("=" * 60)
    print("ESP32 电机方向测试")
    print("=" * 60)
    print(f"目标 ESP32: {ESP32_IP}")
    print("\n请确保：")
    print("1. ESP32 已连接并可访问")
    print("2. 车子放在安全的地方，可以自由移动")
    print("3. 准备好观察车子的动作")
    input("\n准备好后按 Enter 开始测试...")
    
    # 测试序列
    print("\n\n开始测试序列...")
    
    # Test 1: Forward
    test_motor(200, 200, "前进测试 (Forward) - 两轮都应该向前转")
    
    # Test 2: Backward
    test_motor(-200, -200, "后退测试 (Backward) - 两轮都应该向后转")
    
    # Test 3: Turn Right
    test_motor(200, -200, "右转测试 (Turn Right) - 左轮前进，右轮后退")
    
    # Test 4: Turn Left  
    test_motor(-200, 200, "左转测试 (Turn Left) - 左轮后退，右轮前进")
    
    # Test 5: Stop
    test_motor(0, 0, "停止测试 (Stop)")
    
    print("\n" + "=" * 60)
    print("测试完成！")
    print("=" * 60)
    print("\n请回答以下问题：")
    print("1. 前进测试：车子是向前还是向后？ (前/后)")
    print("2. 右转测试：车子是向右转还是向左转？ (右/左)")
    print("\n如果：")
    print("- 前进变后退 → 需要反转两个轮子")
    print("- 右转变左转 → 需要交换左右轮或反转转向")
    print("=" * 60)
