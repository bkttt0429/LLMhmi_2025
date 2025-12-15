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
        
        # Initial angles (safe home position)
        initial_angles = {
            'base': 0.0,
            'shoulder': 90.0,
            'elbow': 90.0,
            'gripper': 50.0  # Half open
        }
        
        # 1. Initialize State (Two-pass to handle coupling dependencies)
        for name, cfg in servo_cfg.items():
            init_angle = initial_angles.get(name, 90.0)
            self.servos[name] = {
                'cfg': cfg,
                'q_current': init_angle,
                'q_target': init_angle
            }

        # 2. Setup Hardware
        for name, cfg in servo_cfg.items():
            pin = machine.Pin(cfg['pin'])
            pwm = machine.PWM(pin)
            pwm.freq(self.config['settings']['pwm_freq'])
            
            self.pwm_objs[name] = pwm
            
            # Apply initial position immediately
            # Now safe because all self.servos entries exist
            init_angle = self.servos[name]['q_current']
            duty = self._apply_calibration(name, init_angle)
            pwm.duty(duty)
            print("[Robot] " + name + " initialized at " + str(init_angle) + "deg (duty=" + str(duty) + ")")
            
        # Kinematics
        geo = self.config['geometry']
        self.ik = InverseKinematics(geo['l1'], geo['l2'])
        
        # Motion State
        self.motion_generators = {}
        self.is_moving = False
        self.max_speed = self.config['settings'].get('max_speed', 100.0)
        
        print("[Robot] Initialization complete")
        gc.collect()

    def _map(self, x, in_min, in_max, out_min, out_max):
        return (x - in_min) * (out_max - out_min) / (in_max - in_min) + out_min

    def _apply_calibration(self, joint_name, q_angle):
        """Convert logical angle to PWM duty cycle"""
        cfg = self.servos[joint_name]['cfg']
        cal = cfg['calib']
        k = cal.get('k', 1.0)
        b = cal.get('b', 0.0)
        
        # Apply calibration
        hw_angle = (q_angle * k) + b
        
        # Coupling logic for MK1
        if joint_name == 'elbow' and self.config['settings'].get('coupling_mk1', False):
            shoulder_q = self.servos['shoulder']['q_current']
            hw_angle += (shoulder_q - 90.0)
        
        # Clamp to limits
        limits = cfg['limits']
        hw_angle = max(limits[0], min(limits[1], hw_angle))
        
        # Convert to microseconds
        pwm_range = cfg['pwm_range']
        us = self._map(hw_angle, 0, 180, pwm_range[0], pwm_range[1])
        
        # Convert to duty cycle
        # For 50Hz: period = 20ms = 20000us
        # duty = (pulse_width_us / 20000) * 1023
        duty = int((us / 20000.0) * 1023)
        
        # Clamp duty to valid range
        duty = max(0, min(1023, duty))
        
        return duty

    def _trapezoidal_generator(self, start_q, end_q, duration_ms):
        start_time = time.ticks_ms()
        while True:
            now = time.ticks_ms()
            elapsed = time.ticks_diff(now, start_time)
            
            if elapsed >= duration_ms:
                yield end_q
                return
            
            t = elapsed / duration_ms
            ease_t = t * t * (3 - 2 * t)
            current_q = start_q + (end_q - start_q) * ease_t
            yield current_q

    def move_to(self, x, y, z, gripper=None):
        gc.collect()
        
        print("[Robot] MoveTo: " + str(x) + ", " + str(y) + ", " + str(z))
        result = self.ik.solve(x, y, z)
        if not result:
            print("[Robot] Unreachable!")
            return False
            
        base_t, shoulder_t, elbow_t = result
        
        targets = {
            'base': base_t, 
            'shoulder': shoulder_t, 
            'elbow': elbow_t
        }
        
        # Add Gripper to targets if provided, else keep current
        if gripper is not None:
            targets['gripper'] = gripper
        else:
            targets['gripper'] = self.servos['gripper']['q_current']
        
        max_duration = 0
        
        for name, target in targets.items():
            start = self.servos[name]['q_current']
            diff = abs(target - start)
            dur = (diff / self.max_speed) * 1000
            if dur > max_duration:
                max_duration = dur
            
        if max_duration < 50: 
            max_duration = 50
        
        print("[Robot] Plan: T=" + str(int(max_duration)) + "ms")
            
        self.motion_generators = {}
        for name, target in targets.items():
            start = self.servos[name]['q_current']
            self.motion_generators[name] = self._trapezoidal_generator(start, target, max_duration)
            self.servos[name]['q_target'] = target
            
        self.is_moving = True
        return True

    def move_angles(self, base, shoulder, elbow, gripper=None):
        gc.collect()
        
        print("[Robot] MoveAngles: B=" + str(base) + " S=" + str(shoulder) + " E=" + str(elbow))
        
        targets = {
            'base': base, 
            'shoulder': shoulder, 
            'elbow': elbow
        }
        
        # Add Gripper to targets if provided, else keep current
        if gripper is not None:
            targets['gripper'] = gripper
        else:
            targets['gripper'] = self.servos['gripper']['q_current']
        
        max_duration = 0
        
        for name, target in targets.items():
            start = self.servos[name]['q_current']
            diff = abs(target - start)
            dur = (diff / self.max_speed) * 1000
            if dur > max_duration:
                max_duration = dur
            
        if max_duration < 50: 
            max_duration = 50
        
        print("[Robot] Plan: T=" + str(int(max_duration)) + "ms")
            
        self.motion_generators = {}
        for name, target in targets.items():
            start = self.servos[name]['q_current']
            self.motion_generators[name] = self._trapezoidal_generator(start, target, max_duration)
            self.servos[name]['q_target'] = target
            
        self.is_moving = True
        return True
    
    def set_angle_direct(self, joint_name, angle):
        """Directly set a joint angle without motion planning (for testing)"""
        if joint_name not in self.servos:
            print("[Robot] Unknown joint: " + joint_name)
            return False
            
        self.servos[joint_name]['q_current'] = angle
        self.servos[joint_name]['q_target'] = angle
        
        duty = self._apply_calibration(joint_name, angle)
        self.pwm_objs[joint_name].duty(duty)
        
        print("[Robot] " + joint_name + " set to " + str(angle) + "deg (duty=" + str(duty) + ")")
        return True

    def update(self):
        if not self.is_moving:
            return

        active_count = 0
        
        for name, gen in self.motion_generators.items():
            try:
                q_next = next(gen)
                self.servos[name]['q_current'] = q_next
                duty = self._apply_calibration(name, q_next)
                self.pwm_objs[name].duty(duty)
                active_count += 1
            except StopIteration:
                pass
                
        if active_count == 0:
            self.is_moving = False
            print("[Robot] Move Complete")
            gc.collect()

    def stop(self):
        self.is_moving = False
        self.motion_generators = {}