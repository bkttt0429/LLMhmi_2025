// AI Detection Toggle
let aiDetectionEnabled = false;

function toggleAIDetection() {
    aiDetectionEnabled = !aiDetectionEnabled;
    const btn = document.getElementById('btn-ai-det');
    const text = document.getElementById('ai-det-text');
    const status = document.getElementById('ai-status');

    if (aiDetectionEnabled) {
        if (btn) {
            btn.classList.add('bg-green-900/40', 'border-green-400');
            btn.classList.remove('border-green-500');
        }
        if (text) text.textContent = 'AI DET: ON';
        if (status) status.textContent = 'AI: ACTIVE';
        log('[AI] Detection ENABLED');

        // Send WebSocket command to enable AI detection
        if (window.socket && window.wsConnected) {
            window.socket.emit('ai_detection_toggle', { enabled: true });
        }
    } else {
        if (btn) {
            btn.classList.remove('bg-green-900/40', 'border-green-400');
            btn.classList.add('border-green-500');
        }
        if (text) text.textContent = 'AI DET';
        if (status) status.textContent = 'AI: STANDBY';
        log('[AI] Detection DISABLED');

        // Send WebSocket command to disable AI detection
        if (window.socket && window.wsConnected) {
            window.socket.emit('ai_detection_toggle', { enabled: false });
        }
    }
}

// Make it globally accessible
window.toggleAIDetection = toggleAIDetection;

// Update Joystick Visualizer to support dual sticks
function updateJoystickVisualizer(gp) {
    if (!gp) return;

    // LEFT stick (Axis 0/1)
    const leftStick = document.getElementById('xbox-stick-left');
    const leftCoords = document.getElementById('stick-coords-left');
    if (leftStick && leftCoords) {
        const leftX = (gp.axes[0] || 0) * 32;
        const leftY = (gp.axes[1] || 0) * 32;
        leftStick.style.transform = `translate(-50%, -50%) translate(${leftX}px, ${leftY}px)`;
        leftCoords.textContent = `X:${(gp.axes[0] || 0).toFixed(2)} Y:${(gp.axes[1] || 0).toFixed(2)}`;
    }

    // RIGHT stick (Axis 2/3)
    const rightStick = document.getElementById('xbox-stick-right');
    const rightCoords = document.getElementById('stick-coords-right');
    if (rightStick && rightCoords) {
        const rightX = (gp.axes[2] || 0) * 32;
        const rightY = (gp.axes[3] || 0) * 32;
        rightStick.style.transform = `translate(-50%, -50%) translate(${rightX}px, ${rightY}px)`;
        rightCoords.textContent = `X:${(gp.axes[2] || 0).toFixed(2)} Y:${(gp.axes[3] || 0).toFixed(2)}`;
    }

    // Legacy fallback for single stick (backward compatibility)
    const singleStick = document.getElementById('xbox-stick');
    const singleCoords = document.getElementById('stick-coords');
    if (singleStick && singleCoords) {
        const x = (gp.axes[0] || 0) * 32;
        const y = (gp.axes[1] || 0) * 32;
        singleStick.style.transform = `translate(-50%, -50%) translate(${x}px, ${y}px)`;
        singleCoords.textContent = `X:${(gp.axes[0] || 0).toFixed(2)} Y:${(gp.axes[1] || 0).toFixed(2)}`;
    }

    // Update button indicators
    updateButtonIndicator('btn-indicator-a', gp.buttons[0]);
    updateButtonIndicator('btn-indicator-x', gp.buttons[2]);
    updateButtonIndicator('btn-indicator-ls', gp.buttons[10]);
    updateButtonIndicator('btn-indicator-rb', gp.buttons[5]);
}

// Helper function for button indicators
function updateButtonIndicator(id, button) {
    const indicator = document.getElementById(id);
    if (!indicator) return;

    const isPressed = button && (button.pressed || button.value > 0.5);
    if (isPressed) {
        indicator.classList.add('indicator-active');
        indicator.classList.remove('indicator-inactive');
    } else {
        indicator.classList.remove('indicator-active');
        indicator.classList.add('indicator-inactive');
    }
}

window.updateJoystickVisualizer = updateJoystickVisualizer;
