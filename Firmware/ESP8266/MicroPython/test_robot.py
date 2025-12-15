from robot import RobotArm
import time

print("\n" + "=" * 50)
print("Robot Arm Complete Test")
print("=" * 50 + "\n")

# Initialize robot
robot = RobotArm()
time.sleep(2)

print("\n--- Test 1: Direct Angle Control ---")
print("Testing Base servo (GPIO5)...")
robot.set_angle_direct('base', 0)
time.sleep(1)
robot.set_angle_direct('base', 90)
time.sleep(1)
robot.set_angle_direct('base', 180)
time.sleep(1)
robot.set_angle_direct('base', 90)
time.sleep(1)

print("\n--- Test 2: Shoulder servo (GPIO4) ---")
robot.set_angle_direct('shoulder', 45)
time.sleep(1)
robot.set_angle_direct('shoulder', 90)
time.sleep(1)
robot.set_angle_direct('shoulder', 135)
time.sleep(1)
robot.set_angle_direct('shoulder', 90)
time.sleep(1)

print("\n--- Test 3: Elbow servo (GPIO0) ---")
robot.set_angle_direct('elbow', 45)
time.sleep(1)
robot.set_angle_direct('elbow', 90)
time.sleep(1)
robot.set_angle_direct('elbow', 135)
time.sleep(1)
robot.set_angle_direct('elbow', 90)
time.sleep(1)

print("\n--- Test 4: Motion Planning (move_angles) ---")
robot.move_angles(45, 90, 90)

# Update loop
print("Updating motion...")
for i in range(100):
    robot.update()
    time.sleep(0.01)  # 10ms update rate
    
time.sleep(1)

print("\n--- Test 5: Return to Home ---")
robot.move_angles(0, 90, 90)
for i in range(100):
    robot.update()
    time.sleep(0.01)

print("\n" + "=" * 50)
print("Test Complete!")
print("=" * 50)
print("\nIf servos didn't move, check:")
print("1. Power supply: 4.8-6V, >1A")
print("2. Wiring:")
print("   Base (GPIO5)     - Orange wire")
print("   Shoulder (GPIO4) - Orange wire")
print("   Elbow (GPIO0)    - Orange wire")
print("3. Common GND between ESP8266 and servo power")
print("4. Servo power separate from ESP8266 power")