import machine
import time

print("\n=== MG90S Servo Test ===\n")

# Test Configuration
TEST_PIN = 5  # GPIO5 (Base servo)
FREQ = 50     # 50Hz for servos
MIN_US = 500
MAX_US = 2500

# Initialize PWM
pin = machine.Pin(TEST_PIN)
pwm = machine.PWM(pin)
pwm.freq(FREQ)

print("Testing GPIO" + str(TEST_PIN) + " at " + str(FREQ) + "Hz")
print("MG90S Specs: " + str(MIN_US) + "us - " + str(MAX_US) + "us")
print()

def set_angle(angle):
    """Set servo angle (0-180 degrees)"""
    # Map 0-180 to MIN_US-MAX_US
    us = MIN_US + (angle / 180.0) * (MAX_US - MIN_US)
    
    # Convert to duty cycle (0-1023)
    # Period = 20000us (50Hz)
    duty = int((us / 20000.0) * 1023)
    
    print("Angle: " + str(angle) + "deg -> " + str(int(us)) + "us -> Duty: " + str(duty))
    pwm.duty(duty)

try:
    # Test sequence
    print("Test 1: Center position (90deg)")
    set_angle(90)
    time.sleep(2)
    
    print("\nTest 2: Minimum position (0deg)")
    set_angle(0)
    time.sleep(2)
    
    print("\nTest 3: Maximum position (180deg)")
    set_angle(180)
    time.sleep(2)
    
    print("\nTest 4: Back to center (90deg)")
    set_angle(90)
    time.sleep(2)
    
    print("\nTest 5: Sweep 0-180")
    for angle in range(0, 181, 10):
        set_angle(angle)
        time.sleep(0.3)
    
    print("\nTest 6: Sweep 180-0")
    for angle in range(180, -1, -10):
        set_angle(angle)
        time.sleep(0.3)
    
    print("\n=== Test Complete ===")
    print("If servo didn't move, check:")
    print("1. Power supply (4.8-6V, sufficient current)")
    print("2. Wiring: Signal -> GPIO5, VCC -> 5V, GND -> GND")
    print("3. Servo is functional")
    
except KeyboardInterrupt:
    print("\n\nTest stopped by user")
finally:
    # Return to center
    set_angle(90)
    print("Servo at center position")