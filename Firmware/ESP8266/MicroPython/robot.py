import machine
import time
import json
import math
import gc
from kinematics import InverseKinematics

class RobotArm:
    def __init__(self, config_file='config.json'):
        print("[Robot] Initializing v2.0...")
        with open(config_file, 'r') as f:
            self.config = json.load(f)
        
        # Hardware Setup
        self.servos = {}
        self.pwm_objs = {}
        servo_cfg = self.config['servos']
        
        for name, cfg in servo_cfg.items():
            pin = machine.Pin(cfg['pin'])
            pwm = machine.PWM(pin)
            pwm.freq(self.config['settings']['pwm_freq'])
            pwm.duty(0) # Start Disabled
            self.pwm_objs[name] = pwm
            self.servos[name] = {
                'cfg': cfg,
                'q_current': 0.0, # Logical Angle
                'q_target': 0.0
            }
            
        # Kinematics
        geo = self.config['geometry']
        self.ik = InverseKinematics(geo['l1'], geo['l2'])
        
        # Motion State
        self.motion_generators = {}
        self.is_moving = False
        self.max_speed = self.config['settings'].get('max_speed', 100.0) # deg/s
        
        gc.collect()

    def _map(self, x, in_min, in_max, out_min, out_max):
        return (x - in_min) * (out_max - out_min) / (in_max - in_min) + out_min

    def _apply_calibration(self, joint_name, q_angle):
        """
        L3 Layer: Convert Logical Angle q -> PWM Duty
        Formula: angle_corrected = k * q + b
        """
        cfg = self.servos[joint_name]['cfg']
        cal = cfg['calib']
        k = cal.get('k', 1.0)
        b = cal.get('b', 0.0)
        
        # 1. Apply linear calibration model
        hw_angle = (q_angle * k) + b
        
        # [Coupling Logic for Mk1]
        # Compensates for mechanical dependency between Shoulder and Elbow.
        # If Shoulder (q2) moves, Elbow (q3) physical angle must adjust to maintain relative geometric angle.
        if joint_name == 'elbow' and self.config['settings'].get('coupling_mk1', False):
            # Get current shoulder geometric angle
            shoulder_q = self.servos['shoulder']['q_current']
            # Formula: Elbow_Servo = Elbow_Geom + (Shoulder_Geom - 90)
            # This is an approximation of the parallel link behavior.
            hw_angle += (shoulder_q - 90.0)
        
        # 2. Safety Clamp (Physical Limits)
        limits = cfg['limits']
        hw_angle = max(limits[0], min(limits[1], hw_angle))
        
        # 3. Convert to Duty Cycle (MicroPython ESP8266: 0-1023)
        # Use Helper to map Angle -> US -> Duty
        pwm_range = cfg['pwm_range'] # [min_us, max_us]
        
        # Standard Servo: 0-180 deg maps to min_us-max_us
        # Assuming hw_angle is in degrees relative to servo horn
        # We assume 0 deg = min_us, 180 deg = max_us for normalized generic calculation
        # But 'hw_angle' IS the degree value.
        # Map hw_angle (e.g. 0..180 or -90..90 depending on servo type) to US
        
        # For MG90S, usually 0-180 range.
        # If user uses -90 to +90 conventions, we need to shift.
        # Let's assume standard 0-180 input to this map function for simplicity?
        # Or map limits[0]..limits[1] to pwm_range[0]..range[1]?
        # Usually easier: map 0-180 to US directly.
        
        # Let's map 0->min_us, 180->max_us.
        # So effective_us over full range.
        # But wait, hw_angle produced by calib could be any range.
        # Let's assume Calibrated Angle is 0-180 compatible.
        
        us = self._map(hw_angle, 0, 180, pwm_range[0], pwm_range[1])
        
        # Duty = (US / 20000us) * 1023
        duty = int((us / 20000.0) * 1023)
        return duty

    def _trapezoidal_generator(self, start_q, end_q, duration_ms):
        """
        Yields position q at each tick based on Trapezoidal Velocity Profile.
        For simplicity on uPy: SmoothStep or S-Curve over Time is computationally cheaper/cleaner than explicit V/A integration.
        We use a normalized 't' (0..1) and apply an easing function.
        """
        start_time = time.ticks_ms()
        while True:
            now = time.ticks_ms()
            elapsed = time.ticks_diff(now, start_time)
            
            if elapsed >= duration_ms:
                yield end_q
                return # Stop
            
            # Normalized Time 0.0 -> 1.0
            t = elapsed / duration_ms
            
            # Easing: SmoothStep (Hermite) => 3t^2 - 2t^3
            # This provides smooth accel/decel (Trapezoidal-ish velocity)
            ease_t = t * t * (3 - 2 * t)
            
            current_q = start_q + (end_q - start_q) * ease_t
            yield current_q

    def move_to(self, x, y, z):
        """
        L1 Layer: Cartesian Input
        """
        # 1. IO/Memory Optimization
        gc.collect()
        
        # 2. Inverse Kinematics
        print(f"[Robot] MoveTo: {x}, {y}, {z}")
        result = self.ik.solve(x, y, z)
        if not result:
            print("[Robot] Metric Unreachable!")
            return False
            
        base_t, shoulder_t, elbow_t = result
        
        # Targets Dictionary
        targets = {
            'base': base_t, 
            'shoulder': shoulder_t, 
            'elbow': elbow_t,
            # Gripper unchanged unless specified? This method is X,Y,Z.
            # Assuming gripper stays.
            'gripper': self.servos['gripper']['q_current'] 
        }
        
        # 3. Motion Profiling (Sync)
        # Calculate Max Duration needed
        max_duration = 0
        moves = []
        
        for name, target in targets.items():
            start = self.servos[name]['q_current']
            diff = abs(target - start)
            # Duration = Dist / Speed
            # Adding min duration of 50ms to avoid div/0 or instant jumps
            dur = (diff / self.max_speed) * 1000 # ms
            if dur > max_duration:
                max_duration = dur
            
        if max_duration < 50: max_duration = 50 # Floor
        
        print(f"[Robot] Plan: T={max_duration:.0f}ms")
            
        # 4. Create Generators
        self.motion_generators = {}
        for name, target in targets.items():
            start = self.servos[name]['q_current']
            # Pass SAME duration to all to ensure Sync arrival!
            self.motion_generators[name] = self._trapezoidal_generator(start, target, max_duration)
            
            # Update 'target' state immediately? Or wait?
            # Better to update q_target as "Final Goal"
            self.servos[name]['q_target'] = target
            
        self.is_moving = True
        return True

    def move_angles(self, base, shoulder, elbow):
        """
        L1 Layer: Direct Angle Input (Bypass IK)
        """
        gc.collect()
        
        targets = {
            'base': base, 
            'shoulder': shoulder, 
            'elbow': elbow,
            'gripper': self.servos['gripper']['q_current'] 
        }
        
        # Motion Profiling (Sync)
        max_duration = 0
        
        for name, target in targets.items():
            start = self.servos[name]['q_current']
            diff = abs(target - start)
            dur = (diff / self.max_speed) * 1000 # ms
            if dur > max_duration:
                max_duration = dur
            
        if max_duration < 50: max_duration = 50
        
        print(f"[Robot] Angles Plan: T={max_duration:.0f}ms")
            
        # Create Generators
        self.motion_generators = {}
        for name, target in targets.items():
            start = self.servos[name]['q_current']
            self.motion_generators[name] = self._trapezoidal_generator(start, target, max_duration)
            self.servos[name]['q_target'] = target
            
        self.is_moving = True
        return True

    def update(self):
        """
        Main Loop Tick. Non-blocking.
        """
        if not self.is_moving:
            return

        active_count = 0
        
        # Update all joints
        for name, gen in self.motion_generators.items():
            try:
                # Get next position from generator
                q_next = next(gen)
                
                # Update State
                self.servos[name]['q_current'] = q_next
                
                # L3/L4: Apply Calibration & Drive PWM
                duty = self._apply_calibration(name, q_next)
                self.pwm_objs[name].duty(duty)
                
                active_count += 1
            except StopIteration:
                # This joint finished.
                pass
                
        # If all generators exhausted
        if active_count == 0:
            self.is_moving = False
            print("[Robot] Move Complete")
            gc.collect()

    def stop(self):
        self.is_moving = False
        self.motion_generators = {}
        # PWM duty 0 for base? (Recall previous task)
        # Or just hold position?
        # For now, just stop updating.
