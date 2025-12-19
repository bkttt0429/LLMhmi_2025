from robot import RobotArm
import time

robot = RobotArm()

print("=== Base Servo Limit Test ===\n")

# 逐步測試
test_angles = [90, 95, 100, 105, 110, 115, 120]

for angle in test_angles:
    print(f"Testing {angle} deg...")
    robot.move_angles(angle, 90, 90, 50)
    time.sleep(2)
    
    # In MicroPython input() might not work well if not connected via Serial.
    # Assuming user runs this via REPL/Serial Monitor manually.
    print("  Moved to " + str(angle))

print("\n=== Reverse Test ===\n")
test_angles_reverse = [90, 85, 80, 75, 70, 65, 60]

for angle in test_angles_reverse:
    print(f"Testing {angle} deg...")
    robot.move_angles(angle, 90, 90, 50)
    time.sleep(2)
    print("  Moved to " + str(angle))

print("\n=== Test Complete ===")
