import json

print("\n" + "=" * 60)
print("PWM Calculation Diagnostics")
print("=" * 60 + "\n")

# Load config
with open('config.json', 'r') as f:
    config = json.load(f)

def map_value(x, in_min, in_max, out_min, out_max):
    return (x - in_min) * (out_max - out_min) / (in_max - in_min) + out_min

def calculate_duty(joint_name, q_angle):
    cfg = config['servos'][joint_name]
    cal = cfg['calib']
    k = cal['k']
    b = cal['b']
    
    # Step 1: Apply calibration
    hw_angle = (q_angle * k) + b
    print("  Step 1: Calibration")
    print("    q_angle = " + str(q_angle))
    print("    k = " + str(k) + ", b = " + str(b))
    print("    hw_angle = " + str(q_angle) + " * " + str(k) + " + " + str(b) + " = " + str(hw_angle))
    
    # Step 2: Clamp to limits
    limits = cfg['limits']
    hw_angle_clamped = max(limits[0], min(limits[1], hw_angle))
    if hw_angle != hw_angle_clamped:
        print("  Step 2: Clamping (limits: " + str(limits) + ")")
        print("    hw_angle clamped: " + str(hw_angle) + " -> " + str(hw_angle_clamped))
    else:
        print("  Step 2: No clamping needed (limits: " + str(limits) + ")")
    hw_angle = hw_angle_clamped
    
    # Step 3: Convert to microseconds
    pwm_range = cfg['pwm_range']
    us = map_value(hw_angle, 0, 180, pwm_range[0], pwm_range[1])
    print("  Step 3: Convert to microseconds")
    print("    PWM range: " + str(pwm_range) + " us")
    print("    us = map(" + str(hw_angle) + ", 0, 180, " + str(pwm_range[0]) + ", " + str(pwm_range[1]) + ")")
    print("    us = " + str(us))
    
    # Step 4: Convert to duty cycle
    duty = int((us / 20000.0) * 1023)
    duty = max(0, min(1023, duty))
    print("  Step 4: Convert to duty cycle (0-1023)")
    print("    duty = (" + str(us) + " / 20000) * 1023 = " + str(duty))
    
    return duty

# Test each joint
joints = ['base', 'shoulder', 'elbow', 'gripper']
test_angles = [0, 45, 90, 135, 180]

for joint in joints:
    print("\n" + "-" * 60)
    print("Joint: " + joint.upper())
    print("Pin: GPIO" + str(config['servos'][joint]['pin']))
    print("-" * 60)
    
    for angle in test_angles:
        print("\nLogical Angle: " + str(angle) + " deg")
        duty = calculate_duty(joint, angle)
        print("  FINAL DUTY: " + str(duty))

print("\n" + "=" * 60)
print("Analysis:")
print("=" * 60)
print("For MG90S servos:")
print("  500us (duty ~25)  = 0 degrees")
print("  1500us (duty ~76) = 90 degrees")
print("  2500us (duty ~127) = 180 degrees")
print("\nIf duty values are outside this range, check calibration!")