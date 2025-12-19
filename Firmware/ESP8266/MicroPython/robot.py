import machine
import time
import json
import math
import gc
from kinematics import InverseKinematics

class RobotArm:
    def __init__(self, config_file='config.json'):
        print("[Robot] Initializing v2.1 (Advanced Control)...")
        with open(config_file, 'r') as f:
            self.config = json.load(f)
        
        # Hardware Setup
        self.servos = {}
        self.pwm_objs = {}
        servo_cfg = self.config['servos']
        
        # 1. Setup State (Pass 1)
        # We must populate self.servos BEFORE hardware init because 'elbow' depends on 'shoulder' state for coupling.
        for name, cfg in servo_cfg.items():
            # Initial State
            # Base (Continuous): 90 means STOP (1500us)
            # Others (Position): 90 means 90 degrees
            init_angle = 90.0 
            if name == 'gripper': init_angle = 50.0
            
            self.servos[name] = {
                'cfg': cfg,
                'q_current': init_angle,
                'q_target': init_angle,
                'mode': 'velocity' if name == 'base' else 'position',
                'velocity': 0.0 # Only for velocity mode
            }
            print(f"[Robot] State {name} prepared")

        # 2. Setup Hardware & Apply Limit (Pass 2)
        for name, cfg in servo_cfg.items():
            pin = machine.Pin(cfg['pin'])
            pwm = machine.PWM(pin)
            pwm.freq(self.config['settings']['pwm_freq'])
            self.pwm_objs[name] = pwm
            
            # Apply Initial State (Safety: Stop Base, Center Others)
            init_angle = self.servos[name]['q_current']
            self._write_servo(name, init_angle)
            print(f"[Robot] {name} hardware initialized")
            
        # Kinematics
        geo = self.config['geometry']
        self.ik = InverseKinematics(geo['l1'], geo['l2'])
        
        # Motion State
        self.motion_generators = {}
        self.is_moving = False
        self.max_speed = self.config['settings'].get('max_speed', 100.0)
        
        print("[Robot] Ready.")
        gc.collect()

    def _map(self, x, in_min, in_max, out_min, out_max):
        return (x - in_min) * (out_max - out_min) / (in_max - in_min) + out_min

    def _write_servo(self, name, param_value):
        """
        Writes PWM to servo using calibrated logic.
        """
        if name not in self.pwm_objs:
            return
            
        duty = self._apply_calibration(name, param_value)
        self.pwm_objs[name].duty(duty)

    def _apply_calibration(self, joint_name, q_angle):
        """Convert logical angle to PWM duty cycle with Debugging"""
        cfg = self.servos[joint_name]['cfg']
        cal = cfg['calib']
        k = cal.get('k', 1.0)
        b = cal.get('b', 0.0)
        
        # [NEW] Debug Print - Step 1: Input
        if joint_name == 'base':
            print("[PWM-DEBUG] Input: q_angle = " + str(q_angle))
        
        # Apply calibration
        hw_angle = (q_angle * k) + b
        
        # [NEW] Debug Print - Step 2: Calibration
        if joint_name == 'base':
            print("[PWM-DEBUG] Calibrated: hw_angle = " + str(hw_angle))
        
        # Coupling logic for MK1
        if joint_name == 'elbow' and self.config['settings'].get('coupling_mk1', False):
            shoulder_q = self.servos['shoulder']['q_current']
            hw_angle += (shoulder_q - 90.0)
        
        # Clamp to limits
        limits = cfg['limits']
        hw_angle_clamped = max(limits[0], min(limits[1], hw_angle))
        
        # [NEW] Debug Print - Step 3: Clamping
        if joint_name == 'base' and hw_angle != hw_angle_clamped:
            print("[PWM-DEBUG] Clamped: " + str(hw_angle) + " -> " + str(hw_angle_clamped))
        
        hw_angle = hw_angle_clamped
        
        # Convert to microseconds
        pwm_range = cfg['pwm_range']
        us = self._map(hw_angle, 0, 180, pwm_range[0], pwm_range[1])
        
        # [NEW] Debug Print - Step 4: Microseconds
        if joint_name == 'base':
            print("[PWM-DEBUG] Pulse Width: " + str(int(us)) + " us")
        
        # Convert to duty cycle
        duty = int((us / 20000.0) * 1023)
        duty = max(0, min(1023, duty))
        
        # [NEW] Debug Print - Step 5: Final Duty
        if joint_name == 'base':
            print("[PWM-DEBUG] Duty Cycle: " + str(duty) + " (0-1023)")
            
            # [NEW] Check Near Limit
            if hw_angle < 72 or hw_angle > 108:
                print("[PWM-WARN] Base near limit: " + str(hw_angle) + " deg")
                
            print("-" * 40)
        
        return duty

    def _cubic_ease_generator(self, start_val, end_val, duration_ms):
        """Yields values following a Cubic In-Out easing curve"""
        start_time = time.ticks_ms()
        change = end_val - start_val
        
        while True:
            now = time.ticks_ms()
            elapsed = time.ticks_diff(now, start_time)
            
            if elapsed >= duration_ms:
                yield end_val
                return
            
            # Normalized time (0.0 to 1.0)
            t = elapsed / duration_ms
            
            # Cubic Easing Formula: t^2 * (3 - 2t)
            # This creates a S-Curve (Smooth Step)
            ease = t * t * (3 - 2 * t)
            
            current_val = start_val + (change * ease)
            yield current_val

    def move_angles(self, base, shoulder, elbow, gripper=None):
        """
        Main Control Interface.
        Base: Treated as Velocity Request (if mode=velocity) or Position (if mode=position).
              **User Request**: Base is Continuous Rotation.
              We interpret 'base' arg as Target Speed if we want, OR we can interpret it as Target Angle 
              but since we lack feedback, we can only do Open Loop Velocity.
              
              However, the packet format sends 4 Angles (0-180).
              Let's re-interpret the 'Base' float from packet:
              - If Base is around 90 -> Stop.
              - If Base > 90 -> Spin CCW.
              - If Base < 90 -> Spin CW.
              This basically maps "Angle" to "Speed" for the Continuous servo directly.
        """
        gc.collect()
        
        # 1. Base (Velocity Control)
        # We pass the raw angle (0-180) directly to _write_servo.
        # _write_servo will interpret it as Speed Mapping if configured, 
        # BUT since we want compatibility, let's treat the incoming "90" as "Stop".
        # If the user sends 100, _write_servo(100) -> 100 deg PWM -> Slow CCW.
        # So we just update 'q_current' to this value (it's actually speed state).
        
        # S-Curve for Velocity Ramp?
        # Yes, let's ramp the "Speed Command" to avoid jerky starts.
        base_speed_target = base # 0-180
        
        # 2. Others (Position Control)
        targets = {
            'base': base_speed_target, 
            'shoulder': shoulder, 
            'elbow': elbow,
            'gripper': gripper if gripper is not None else self.servos['gripper']['q_current']
        }
        
        # Determine Duration (Max Speed Logic)
        max_duration = 0
        for name, target in targets.items():
            start = self.servos[name]['q_current']
            diff = abs(target - start)
            
            # Speed Factor: 60 deg / sec?
            # 100 Speed unit ~ 1000ms
            dur = (diff / self.max_speed) * 1000
            if dur > max_duration: max_duration = dur
            
        if max_duration < 50: max_duration = 50
        
        # Generate Motion Profiles
        self.motion_generators = {}
        for name, target in targets.items():
            start = self.servos[name]['q_current']
            self.motion_generators[name] = self._cubic_ease_generator(start, target, max_duration)
            self.servos[name]['q_target'] = target # Update target
            
        self.is_moving = True
        return True

    def update(self):
        """Called periodically (e.g. 20ms)"""
        if not self.is_moving:
            return

        active_count = 0
        for name, gen in self.motion_generators.items():
            try:
                val = next(gen)
                self.servos[name]['q_current'] = val
                
                if name == 'base':
                    # For Base, 'val' is the current Speed Command (0-180)
                    # We send this directly to the Continuous Servo
                    self._write_servo(name, val) 
                else:
                    # For Others, 'val' is the current Angle
                    self._write_servo(name, val)
                    
                active_count += 1
            except StopIteration:
                pass
                
        if active_count == 0:
            self.is_moving = False
            # print("[Robot] Motion Complete") (Silence for async)
