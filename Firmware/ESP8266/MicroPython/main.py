
import socket
import machine
import time
import json

# === CONFIGURATION ===
UDP_PORT = 4211
RAMP_SPEED = 2 # steps per loop

# === PIN DEFINITIONS (Wemos D1 Mini) ===
# D1=5, D2=4, D3=0, D4=2
PIN_BASE     = 5
PIN_SHOULDER = 4
PIN_ELBOW    = 0
PIN_GRIPPER  = 2  # Note: D4 is also Built-in LED on some boards

# === SERVO CLASS ===
class Servo:
    def __init__(self, pin_num, min_us=500, max_us=2500, freq=50, ramping=True):
        self.pin = machine.Pin(pin_num)
        self.pwm = machine.PWM(self.pin)
        self.pwm.freq(freq)
        self.min_us = min_us
        self.max_us = max_us
        self.ramping = ramping
        self.current_angle = 90  # Default Safe Position
        self.target_angle = 90
        
        # Initial Move (Fast)
        self.write_angle(90)

    def write_angle(self, angle):
        # Constrain
        if angle < 0: angle = 0
        if angle > 180: angle = 180
        
        # [NOISE FIX] Auto-Detach at 90 (Stop)
        # If angle is exactly 90, we cut the signal (Duty 0).
        # This stops the 360 servo from creeping/humming.
        if angle == 90:
            self.pwm.duty(0)
            self.current_angle = 90
            return

        # Map 0-180 to Duty (0-1023)
        # us = min_us + (angle/180 * range)
        us = self.min_us + (angle * (self.max_us - self.min_us) / 180)
        duty = int(us / 20000 * 1023)
        self.pwm.duty(duty)
        self.current_angle = angle

    def update(self):
        # Direct Move if Ramping Disabled
        if not self.ramping:
            if self.current_angle != self.target_angle:
                self.write_angle(self.target_angle)
            return

        # Ramping Logic
        if self.current_angle != self.target_angle:
            diff = self.target_angle - self.current_angle
            step = RAMP_SPEED
            
            if abs(diff) <= step:
                self.write_angle(self.target_angle) # Snap to target
            else:
                new_angle = self.current_angle
                if diff > 0: new_angle += step
                else: new_angle -= step
                self.write_angle(new_angle) # Update via write_angle to set PWM

# === SETUP ===
print("Initializing Servos...")
# Base: 360 Continuous -> No Ramping (Instant Stop)
base     = Servo(PIN_BASE, ramping=False) 
# Others: 180 Positional -> Ramping (Smooth Move)
shoulder = Servo(PIN_SHOULDER, ramping=True) 
elbow    = Servo(PIN_ELBOW, ramping=True)
gripper  = Servo(PIN_GRIPPER, ramping=True)

servos = {'base': base, 'shoulder': shoulder, 'elbow': elbow, 'gripper': gripper}

# === UDP SETUP ===
s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
try:
    s.bind(('0.0.0.0', UDP_PORT))
    s.settimeout(0.02) # 20ms timeout (Non-blocking-ish)
    print(f"Listening on UDP {UDP_PORT}")
except Exception as e:
    print("UDP Bind Error:", e)

# === MAIN LOOP ===
last_time = time.ticks_ms()
last_beacon = 0

while True:
    try:
        now = time.ticks_ms()
        
        # 0. Discovery Beacon (Every 2000ms)
        if time.ticks_diff(now, last_beacon) >= 2000:
            last_beacon = now
            try:
                # Broadcast Identity
                s.sendto(b"ESP8266_ARM", ('255.255.255.255', 4211))
            except OSError:
                pass # Broadcast might fail if network busy

        # 1. Ramping Loop (Run every 20ms)
        if time.ticks_diff(now, last_time) >= 20:
            last_time = now
            base.update()
            shoulder.update()
            elbow.update()
            gripper.update()

        # 2. UDP Receive
        try:
            data, addr = s.recvfrom(256)
            msg = data.decode('utf-8')
            # Expect: {"base":90,"shoulder":90,"elbow":90,"gripper":0}
            cmd = json.loads(msg)
            
            if 'base' in cmd: base.target_angle = int(cmd['base'])
            if 'shoulder' in cmd: shoulder.target_angle = int(cmd['shoulder'])
            if 'elbow' in cmd: elbow.target_angle = int(cmd['elbow'])
            if 'gripper' in cmd: gripper.target_angle = int(cmd['gripper'])
            
            # Reset Watchdog
            last_packet_time = time.ticks_ms()
            
        except OSError:
            pass # Timeout (No Packet)
            
        except ValueError:
            print("JSON Error")

        # 3. Safety Watchdog (Auto-Stop if no connection)
        if time.ticks_diff(now, last_packet_time) > 2000:
            # Force target to 90 (Stop/Center)
            if base.target_angle != 90: base.target_angle = 90
            # Optional: Keep positional servos where they are? Or Home them?
            # Safer to just STOP the base.


    except KeyboardInterrupt:
        break
    except Exception as e:
        print("Loop Error:", e)
        time.sleep(1)
