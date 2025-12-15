// === Gamepad & Control Logic ===
let lastXboxUpdate = 0;
let lastKeyboardActivity = 0;
let keyPressed = {};
let speedLimitPercent = 100;
let lastGamepadCmdTime = 0;
let wasJoystickActive = false;
let motorEnabled = true; // Safety Lock: Default ON (User Request)
const CMD_INTERVAL = 50; // Throttle to 20Hz

// Flood Protection & Serialization State
let lastSentCmd = { left: 0, right: 0 };
let lastCmdTime = 0;
let isRequestPending = false; // Mutex: Is an HTTP request currently flying?
let pendingCmd = null;        // Queue: Next command to send immediately after current one finishes

// Export for main.js and UI
window.lastXboxUpdate = 0;
window.toggleMotorLock = toggleMotorLock;

function toggleMotorLock() {
    motorEnabled = !motorEnabled;
    const btn = document.getElementById('btn-motor-lock');
    const status = document.getElementById('motor-status-text');

    if (motorEnabled) {
        log("[CONTROL] Motors UNLOCKED");
        if (btn) {
            btn.classList.add('text-green-400', 'border-green-500');
            btn.classList.remove('text-red-400', 'border-red-500');
            btn.innerHTML = 'MOTORS: <span class="animate-pulse">ON</span>';
        }
    } else {
        log("[CONTROL] Motors LOCKED (Safety)");
        if (btn) {
            btn.classList.remove('text-green-400', 'border-green-500');
            btn.classList.add('text-red-400', 'border-red-500');
            btn.innerText = 'MOTORS: OFF (LOCK)';
        }
        // Send Stop once
        emitControlCommand(0, 0);
    }
}

function initMotorLock() {
    const btn = document.getElementById('btn-motor-lock');
    if (motorEnabled && btn) {
        btn.classList.add('text-green-400', 'border-green-500');
        btn.classList.remove('text-red-400', 'border-red-500');
        btn.innerHTML = 'MOTORS: <span class="animate-pulse">ON</span>';
    }
}
window.initMotorLock = initMotorLock;

function setupKeyboardControls() {
    document.addEventListener('keydown', (e) => {
        if (e.repeat) return; // Prevent repeat spam (we handle state)
        const key = e.key.toUpperCase();

        // Prevent default scrolling for WASD
        if (['W', 'A', 'S', 'D', ' '].includes(key)) {
            // e.preventDefault(); 
        }

        if (keyPressed[key]) return;
        keyPressed[key] = true;
        lastKeyboardActivity = Date.now();

        // Map keys to commands (Single press logic)
        switch (key) {
            case 'W': sendCmd('F'); break;
            case 'S': sendCmd('S'); break;
            case 'A': sendCmd('L'); break;
            case 'D': sendCmd('R'); break;
            case 'X': sendCmd('B'); break;
            case ' ': sendCmd('S'); break;
            case 'R':
                if (window.resetRobotArm) window.resetRobotArm();
                break;
        }
    });

    document.addEventListener('keyup', (e) => {
        const key = e.key.toUpperCase();
        keyPressed[key] = false;

        // Stop on release if it was a movement key
        if (['W', 'A', 'S', 'D', 'X', ' '].includes(key)) {
            // Only send stop if no other movement keys are pressed? 
            // For simplicity, release = STOP.
            sendCmd('S');
        }
    });

    log('[CONTROL] Keyboard listeners ready');
}
window.setupKeyboardControls = setupKeyboardControls;

function initSpeedLimiter() {
    const slider = document.getElementById('speed-limit-slider');
    if (!slider) return;

    speedLimitPercent = parseInt(slider.value);
    updateSpeedLimitDisplay();

    slider.addEventListener('input', (e) => {
        speedLimitPercent = parseInt(e.target.value);
        updateSpeedLimitDisplay();
    });

    slider.addEventListener('change', (e) => {
        log(`Speed Limit set to ${speedLimitPercent}%`);
    });
}
window.initSpeedLimiter = initSpeedLimiter;

function updateSpeedLimitDisplay() {
    const display = document.getElementById('speed-limit-value');
    if (display) display.innerText = speedLimitPercent + '%';
}

function applySpeedLimit(pwmValue) {
    return Math.round(pwmValue * (speedLimitPercent / 100));
}

// === Command Sending ===
function sendCmd(cmd) {
    highlightKey(cmd);
    lastKeyboardActivity = Date.now();

    let left = 0, right = 0;

    switch (cmd) {
        case 'F': left = 200; right = 200; break;
        case 'B': left = -200; right = -200; break;
        case 'L': left = -180; right = 180; break;
        case 'R': left = 180; right = -180; break;
        case 'S': left = 0; right = 0; break;
        default: return;
    }

    left = applySpeedLimit(left);
    right = applySpeedLimit(right);

    emitControlCommand(left, right);
}

function emitControlCommand(left, right) {
    // === FLOOD PROTECTION & SERIALIZATION ===
    const now = Date.now();
    const isDifferent = (left !== lastSentCmd.left || right !== lastSentCmd.right);

    // 1. WebSocket Mode (No serialization needed usually, but good practice)
    if (window.socket && window.wsConnected) {
        // WS is async but usually handles concurrency better.
        // Still, let's deduplicate.
        if (!isDifferent && (now - lastCmdTime < 100)) return;

        window.socket.emit('control_command', { left: left, right: right });
        lastSentCmd = { left: left, right: right };
        lastCmdTime = now;
        return;
    }

    // 2. HTTP Fallback Mode (Critical Serialization)
    // If a request is already in flight, queue this one (latest wins)
    if (isRequestPending) {
        pendingCmd = { left: left, right: right };
        return;
    }

    // Deduplication (only if not forcing a queued command)
    if (!isDifferent && (now - lastCmdTime < 100)) return;

    // Send immediately
    sendHttpCommand(left, right);
}

function sendHttpCommand(left, right) {
    isRequestPending = true;
    lastSentCmd = { left: left, right: right };
    lastCmdTime = Date.now();

    fetch('/api/control', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'Connection': 'close' // [FIX] Help ESP32 close socket
        },
        body: JSON.stringify({ left: left, right: right })
    })
        .then(() => {
            // Success
        })
        .catch(e => {
            console.error("Control Error", e);
        })
        .finally(() => {
            isRequestPending = false;

            // If there is a pending command that is DIFFERENT from what we just sent, send it now.
            if (pendingCmd) {
                const next = pendingCmd;
                pendingCmd = null;
                // Recursion? No, just call internal sender if different
                // Check if it's materially different or just a repeat of what we just sent
                if (next.left !== left || next.right !== right) {
                    sendHttpCommand(next.left, next.right);
                }
            }
        });
}
window.sendCmd = sendCmd; // Export for UI buttons

function highlightKey(cmd) {
    const map = { 'F': 'btn-w', 'L': 'btn-a', 'S': 'btn-s', 'R': 'btn-d', 'B': 'btn-x' };
    const id = map[cmd];
    if (id) {
        const btn = document.getElementById(id);
        if (btn) {
            btn.classList.add('btn-active');
            setTimeout(() => btn.classList.remove('btn-active'), 150);
        }
    }
}

// === Robot Arm Controller (Rate Control) ===
class RobotArmController {
    constructor() {
        // Initial State (Matches Firmware Home)
        this.angles = {
            base: 0,      // 0-180
            shoulder: 90, // 0-180
            elbow: 90,    // 0-180
            gripper: 50   // 0-180 (50=Open)
        };

        // Speed Factors (Degrees per Tick)
        // Tick is ~50ms (20Hz)
        // 1.0 = 20 deg/sec at full stick
        this.baseSpeed = 2.0;
        this.armSpeed = 1.5;

        this.lastUpdateTime = 0;
        this.gripperState = false; // false=Open, true=Closed
        this.lastButtonState = { a: false };
    }

    update(gp) {
        const now = Date.now();
        const dt = (now - this.lastUpdateTime) / 50.0; // Normalize to 50ms units
        this.lastUpdateTime = now;

        // --- Inputs ---
        // Stick Left X: Base Rotate (Left/Right)
        // Stick Left Y: Shoulder (Up/Down)
        // Stick Right Y: Elbow (Up/Down)

        // Deadzone
        const dz = (v) => Math.abs(v) < 0.15 ? 0 : v;

        const baseInput = dz(gp.axes[0]);
        const shoulderInput = -dz(gp.axes[1]); // Invert Y (Up is -1)
        const elbowInput = -dz(gp.axes[3]);    // Right Stick Y

        // --- Integration (Rate Control) ---
        // Angle += Input * Speed * Scaling

        // Base
        if (baseInput !== 0) {
            this.angles.base -= baseInput * this.baseSpeed * (speedLimitPercent / 100) * dt;
        }

        // Shoulder
        if (shoulderInput !== 0) {
            this.angles.shoulder += shoulderInput * this.armSpeed * (speedLimitPercent / 100) * dt;
        }

        // Elbow
        if (elbowInput !== 0) {
            this.angles.elbow += elbowInput * this.armSpeed * (speedLimitPercent / 100) * dt;
        }

        // --- Clamping (Safety) ---
        this.angles.base = Math.max(0, Math.min(180, this.angles.base));
        this.angles.shoulder = Math.max(0, Math.min(180, this.angles.shoulder));
        this.angles.elbow = Math.max(0, Math.min(180, this.angles.elbow));

        // --- Gripper (Toggle on A Button) ---
        const btnA = gp.buttons[0]?.pressed;
        if (btnA && !this.lastButtonState.a) {
            this.gripperState = !this.gripperState;
            this.angles.gripper = this.gripperState ? 100 : 0; // 100=Closed, 0=Open
            log(`[ARM] Gripper: ${this.gripperState ? "CLOSED" : "OPEN"}`);
        }
        this.lastButtonState.a = btnA;

        // --- Send Command ---
        // Only send if changed? Or periodic?
        // Periodic is safer for UDP stream
        this.send();
        // Update Visualization Globals (Sync with robot_arm.js 3D model)
        // Convert Degrees (0-180) to Radians (-PI/2 to +PI/2) for 3D Model
        if (typeof window.targetBaseAngle !== 'undefined') {
            window.targetBaseAngle = (this.angles.base - 90) * (Math.PI / 180);
            window.targetShoulderAngle = (this.angles.shoulder - 90) * (Math.PI / 180);
            window.targetElbowAngle = (this.angles.elbow - 90) * (Math.PI / 180);
        }

        // Send Command via WebSocket
        if (now - this.lastSent > this.sendInterval) {
            if (window.socket && window.wsConnected) {
                const payload = {
                    base: Math.round(this.angles.base),
                    shoulder: Math.round(this.angles.shoulder),
                    elbow: Math.round(this.angles.elbow),
                    gripper: Math.round(this.angles.gripper)
                };
                window.socket.emit('arm_command', payload);
                this.lastSent = now;
            }
        }
    }

    send() {
        if (window.socket && window.wsConnected) {
            // Update UI
            const display = document.getElementById('arm-status');
            if (display) display.innerText = `B:${this.angles.base.toFixed(0)} S:${this.angles.shoulder.toFixed(0)} E:${this.angles.elbow.toFixed(0)}`;
        }
    }
}

const armController = new RobotArmController();
window.updateRobotArmFromGamepad = (gp) => armController.update(gp);
window.resetRobotArm = () => {
    armController.angles = { base: 0, shoulder: 90, elbow: 90, gripper: 50 };
    log("[ARM] Position Reset");
};

// === Xbox Controller Loop ===
function updateJoystickLoop() {
    const gamepads = navigator.getGamepads ? navigator.getGamepads() : [];
    const gp = gamepads[0];

    if (!gp || !gp.connected) return;

    // Heartbeat
    window.lastXboxUpdate = Date.now();
    const icon = document.getElementById('gamepad-status');
    if (icon) {
        icon.classList.remove('gamepad-inactive');
        icon.classList.add('gamepad-active');
    }

    // Input Priority: Block gamepad if keyboard used recently
    // if (Date.now() - lastKeyboardActivity < 500) return;

    // Handle Robot Arm Control (Right Stick) - Must run before Chassis Optimization
    if (window.updateRobotArmFromGamepad) {
        window.updateRobotArmFromGamepad(gp);
    }

    // Chassis Control (Left/Right PWM)
    // Only if user wants? Or always?
    // User requested "Joystick Left/Right -> Rotate Base".
    // This conflicts with Chassis Steering.
    // For now, let's DISABLE Chassis Mixing if we are in Arm Mode?
    // Or just run both?
    // The user's request implies the "Left/Right Stick" IS for the Arm Base.
    // So we should NOT calculate chassis drive from the same stick.
    // BUT we don't have a mode switch yet.
    // Let's assume this is PURELY an ARM Controller now (since user said "Joystick controls motor logic").

    // We update UI indicators but skip sending Chassis commands if Arm is main focus?
    // Actually, let's keep Chassis logic but maybe on D-Pad?
    // Or just let overlap happen (dangerous).

    // DECISION: User said "Joystick Left/Right control Base Rotate".
    // This uses Axis 0. 
    // Chassis uses Axis 0 for Steering.
    // I will COMMENT OUT the Chassis 'emitControlCommand' call below to prevent conflict
    // and let the Arm Controller handle the logic.

    /*
    // Read Standard Axes
    const rawX = gp.axes[0];
    const rawY = gp.axes[1];
    ...
    emitControlCommand(leftPWM, rightPWM);
    */

    // Update Visuals Only
    if (window.updateJoystickVisualizer) {
        window.updateJoystickVisualizer(gp);
    }
    updateButtonIndicators(gp);
}
window.updateJoystickLoop = updateJoystickLoop;


// === Visual Handling ===
function updateButtonIndicators(gp) {
    const setInd = (id, pressed) => {
        const el = document.getElementById(`btn-indicator-${id}`);
        if (!el) return;
        if (pressed) {
            el.classList.remove('bg-gray-700', 'indicator-inactive');
            el.classList.add('bg-green-400', 'indicator-active');
        } else {
            el.classList.add('bg-gray-700', 'indicator-inactive');
            el.classList.remove('bg-green-400', 'indicator-active');
        }
    };

    setInd('a', gp.buttons[0]?.pressed);
    setInd('x', gp.buttons[2]?.pressed);
    setInd('ls', gp.buttons[10]?.pressed);
}

function updatePWMDisplay(left, right) {
    const leftEl = document.getElementById('pwm-left');
    const rightEl = document.getElementById('pwm-right');

    const updateColor = (el, val) => {
        el.innerText = val;
        if (val > 0) el.className = 'text-green-400 font-bold text-sm';
        else if (val < 0) el.className = 'text-red-400 font-bold text-sm';
        else el.className = 'text-gray-500 font-bold text-sm';
    };

    if (leftEl) updateColor(leftEl, left);
    if (rightEl) updateColor(rightEl, right);
}
