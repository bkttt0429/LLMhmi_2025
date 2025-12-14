// === Gamepad & Control Logic ===
let lastXboxUpdate = 0;
let lastKeyboardActivity = 0;
let keyPressed = {};
let speedLimitPercent = 100;
let lastGamepadCmdTime = 0;
let wasJoystickActive = false;
let motorEnabled = false; // Safety Lock: Default OFF to prevent mapping issues
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
    if (Date.now() - lastKeyboardActivity < 500) return;

    // Read Standard Axes
    const rawX = gp.axes[0];
    const rawY = gp.axes[1];

    // Motor Safety Check
    if (!motorEnabled) {
        // Still update visual stick but DO NOT calculate PWM
        if (window.updateJoystickVisualizer) window.updateJoystickVisualizer(gp);
        updateButtonIndicators(gp);

        // Handle Arm (Right Stick) even if motors locked
        if (window.updateRobotArmFromGamepad) {
            window.updateRobotArmFromGamepad(gp);
        }
        return;
    }

    // Deadzone
    const DEADZONE = 0.15;
    const applyDeadzone = (val) => Math.abs(val) < DEADZONE ? 0 : val;

    // [DEBUG] Log Raw Input
    // console.log(`RawX: ${rawX.toFixed(2)}, RawY: ${rawY.toFixed(2)}`);

    let steer = applyDeadzone(rawX);
    let throttle = -applyDeadzone(rawY); // [FIX] Invert Y for Standard Gamepad (Up = -1 -> +1)

    // Update Visual Indicator
    if (window.updateJoystickVisualizer) {
        window.updateJoystickVisualizer(gp);
    }
    updateButtonIndicators(gp);

    // Mixing
    let leftVal = throttle + steer;
    let rightVal = throttle - steer;

    leftVal = Math.max(-1, Math.min(1, leftVal));
    rightVal = Math.max(-1, Math.min(1, rightVal));

    // PWM Scaling
    const MAX_PWM = 255;
    let leftPWM = Math.round(leftVal * MAX_PWM);
    let rightPWM = Math.round(rightVal * MAX_PWM);

    leftPWM = applySpeedLimit(leftPWM);
    rightPWM = applySpeedLimit(rightPWM);

    updatePWMDisplay(leftPWM, rightPWM);

    // Sending Logic (Throttled)
    const isStickActive = (leftPWM !== 0 || rightPWM !== 0);

    // Stop Logic: If stopped, strictly don't send unless we JUST stopped
    if (!isStickActive && !wasJoystickActive) {
        return;
    }

    const now = Date.now();
    // Send if: Active OR (Idle AND just became Idle)
    if (isStickActive || wasJoystickActive) {
        // Check local throttle AND let emitControlCommand handle serialization
        if ((now - lastGamepadCmdTime > CMD_INTERVAL) || (wasJoystickActive && !isStickActive)) {
            emitControlCommand(leftPWM, rightPWM);

            // Visual Debug in UI
            const cmdDisplay = document.getElementById('xbox-cmd');
            if (cmdDisplay) cmdDisplay.innerText = `L:${leftPWM} R:${rightPWM}`;

            lastGamepadCmdTime = now;
        }
    }

    wasJoystickActive = isStickActive;

    // Handle Robot Arm Control (Right Stick) if in Robot View (or Dual Mode)
    if (window.updateRobotArmFromGamepad) {
        window.updateRobotArmFromGamepad(gp);
    }
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
