// === Main Global State ===
let socket;
let wsConnected = false;
let lastLogs = [];
let currentView = 'main';
let lastFrameTime = 0;
let radarAngle = 0;

// Export global variables that are needed by other modules
window.socket = null;
window.wsConnected = false;
window.currentView = 'main';

// === Initialization ===
window.onload = () => {
    initWebSocket();
    resizeCanvas();
    requestAnimationFrame(animationLoop);
    log("System Initialized. Modular Interface Active.");

    if (window.fetchModels) window.fetchModels();

    // Initialize Subsystems
    if (window.setupKeyboardControls) window.setupKeyboardControls();
    if (window.initSpeedLimiter) window.initSpeedLimiter();
    if (window.initVideoRetry) window.initVideoRetry();
    if (window.initRobot3D) window.initRobot3D();
};

window.onresize = () => {
    resizeCanvas();
    if (window.camera3D && window.renderer3D) {
        // Trigger 3D resize if exists
        window.dispatchEvent(new Event('resize-3d'));
    }
}

// === WebSocket Handling ===
function initWebSocket() {
    // Initialize Socket.IO
    socket = io({ transports: ['websocket'] });
    window.socket = socket;

    socket.on('connect', () => {
        wsConnected = true;
        window.wsConnected = true;
        log("WS Connected");
    });

    socket.on('disconnect', () => {
        wsConnected = false;
        window.wsConnected = false;
        log("WS Disconnected");
    });

    // Handle status updates pushed from server
    socket.on('status_update', (data) => {
        updateUI(data);
    });

    // Handle controller feedback (if using hardware controller via server)
    socket.on('controller_data', (data) => {
        if (window.handleControllerData) {
            window.handleControllerData(data);
        }
    });

    socket.on('log', (data) => {
        // Optional: Real-time log stream
        // log(data.data);
    });
}

function updateUI(data) {
    // Update Header IPs
    const carIpDisplay = document.getElementById('car-ip-display');
    const camIpDisplay = document.getElementById('cam-ip-display');

    if (data.car_ip) {
        carIpDisplay.innerText = data.car_ip;
        carIpDisplay.className = "text-green-400 font-bold font-mono";
        const setCar = document.getElementById('settings-car-ip');
        if (setCar && !setCar.value) setCar.value = data.car_ip;
    }

    if (data.camera_ip) {
        camIpDisplay.innerText = data.camera_ip;
        camIpDisplay.className = "text-blue-400 font-bold font-mono";
        const setCam = document.getElementById('settings-cam-ip');
        if (setCam && !setCam.value) setCam.value = data.camera_ip;
    }

    // Update AI Status
    const aiStatus = document.getElementById('ai-status');
    const aiToggleBtn = document.getElementById('ai-toggle-btn');
    if (data.ai_status) {
        aiStatus.innerText = "AI: ACTIVE";
        aiStatus.className = "text-green-400 font-bold animate-pulse";
        if (aiToggleBtn) aiToggleBtn.innerText = "DEACTIVATE AI";
    } else {
        aiStatus.innerText = "AI: STANDBY";
        aiStatus.className = "text-gray-500";
        if (aiToggleBtn) aiToggleBtn.innerText = "ACTIVATE AI HUD";
    }

    // Update Distance
    const distVal = document.getElementById('dist-val');
    if (distVal && data.dist !== undefined) {
        distVal.innerText = data.dist.toFixed(2) + " CM";
    }

    // Logs
    if (data.logs) {
        const serialized = JSON.stringify(data.logs);
        if (serialized !== JSON.stringify(lastLogs)) {
            lastLogs = data.logs.slice();
            const box = document.getElementById('log-box');
            if (box) {
                box.innerHTML = "";
                data.logs.forEach(l => {
                    const d = document.createElement('div');
                    d.innerText = l;
                    box.appendChild(d);
                });
                box.scrollTop = box.scrollHeight;
            }
        }
    }
}

// === Visual Animations ===
function animationLoop(timestamp) {
    const dt = timestamp - lastFrameTime;
    lastFrameTime = timestamp;

    drawRadar(document.getElementById('radar-canvas-main'), timestamp);

    // Gamepad Logic Loop (Polls standard gamepad API)
    if (window.updateJoystickLoop) {
        window.updateJoystickLoop();
    }

    // 3D Animation Loop is usually handled safely inside robot_arm.js, 
    // but if we unified it, we'd call it here. 
    // Currently robot_arm.js starts its own loop.

    requestAnimationFrame(animationLoop);
}

function drawRadar(canvas, time) {
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    const w = canvas.width, h = canvas.height;
    const cx = w / 2, cy = h / 2;
    // Fix: Ensure valid radius
    let radius = Math.min(w, h) / 2 - 2;
    if (radius < 5) radius = 5;

    ctx.clearRect(0, 0, w, h);

    // Grid
    ctx.strokeStyle = 'rgba(0, 255, 157, 0.2)';
    ctx.lineWidth = 1;
    ctx.beginPath(); ctx.arc(cx, cy, radius, 0, Math.PI * 2); ctx.stroke();
    ctx.beginPath(); ctx.arc(cx, cy, radius * 0.5, 0, Math.PI * 2); ctx.stroke();
    ctx.beginPath(); ctx.moveTo(cx, cy - radius); ctx.lineTo(cx, cy + radius); ctx.stroke();
    ctx.beginPath(); ctx.moveTo(cx - radius, cy); ctx.lineTo(cx + radius, cy); ctx.stroke();

    // Sweep
    radarAngle = (time / 2000 * Math.PI * 2) % (Math.PI * 2);
    const grad = ctx.createConicGradient(radarAngle - Math.PI / 2, cx, cy);
    grad.addColorStop(0, 'rgba(0, 255, 157, 0)');
    grad.addColorStop(0.8, 'rgba(0, 255, 157, 0.1)');
    grad.addColorStop(1, 'rgba(0, 255, 157, 0.4)');
    ctx.fillStyle = grad;
    ctx.beginPath(); ctx.arc(cx, cy, radius, 0, Math.PI * 2); ctx.fill();
}

function resizeCanvas() {
    const mainC = document.getElementById('radar-canvas-main');
    if (mainC) {
        mainC.width = mainC.parentElement.clientWidth;
        mainC.height = mainC.parentElement.clientHeight;
    }
}

function log(msg) {
    const box = document.getElementById('log-box');
    if (box) {
        const time = new Date().toLocaleTimeString('en-GB');
        const d = document.createElement('div');
        d.innerHTML = `<span class="text-gray-600">[${time}]</span> ${msg}`;
        box.appendChild(d);
        box.scrollTop = box.scrollHeight;
    }
    console.log(`[SYS] ${msg}`);
}

// Global Log Helper
window.log = log;
