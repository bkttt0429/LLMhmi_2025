// === UI Interaction Logic ===

// Export for global access
window.switchView = switchView;
window.applySettings = applySettings;
window.toggleAI = toggleAI;
window.exportLogs = exportLogs;
window.showNetInfo = showNetInfo;
window.updateCameraSetting = updateCameraSetting;
window.toggleCamBool = toggleCamBool;
window.fetchCameraSettings = fetchCameraSettings; // Exported for use in switchView logic
window.fetchModels = fetchModels;
window.applyModel = applyModel;

// View Switching
function switchView(view) {
    // Update Global State
    window.currentView = view; // Update export

    const mainView = document.getElementById('main-view');
    const settingsView = document.getElementById('settings-view');
    const robotView = document.getElementById('robot-view');

    // Hide all views
    if (mainView) {
        mainView.classList.add('view-hidden');
        mainView.classList.remove('view-grid');
    }
    if (settingsView) {
        settingsView.classList.add('view-hidden');
        settingsView.classList.remove('view-block');
    }
    if (robotView) robotView.classList.add('view-hidden');

    // Show selected view
    if (view === 'main') {
        if (mainView) {
            mainView.classList.remove('view-hidden');
            mainView.classList.add('view-grid');
        }
    } else if (view === 'robot') {
        if (robotView) robotView.classList.remove('view-hidden');
        if (window.initRobot3D) window.initRobot3D();
    } else if (view === 'settings') {
        if (settingsView) {
            settingsView.classList.remove('view-hidden');
            settingsView.classList.add('view-block');
        }
        fetchCameraSettings();
    }

    // Update Nav Buttons
    document.querySelectorAll('.nav-btn').forEach(btn => btn.classList.remove('active'));
    const activeBtn = document.getElementById('nav-' + view);
    if (activeBtn) activeBtn.classList.add('active');
}

// === Settings ===
function applySettings() {
    const carIp = document.getElementById('settings-car-ip').value;
    const camIp = document.getElementById('settings-cam-ip').value;

    // IP Setting Logic (Simulated or via API if implemented)
    log(`Settings view - Current CAR: ${carIp}, CAM: ${camIp} (read-only)`);
    log(`To change IPs, edit config.py and restart server`);
    switchView('main');
}

async function fetchModels() {
    try {
        const res = await fetch('/api/get_models');
        const data = await res.json();
        const selector = document.getElementById('model-selector');
        if (selector && data.models && data.models.length > 0) {
            selector.innerHTML = '';
            data.models.forEach(model => {
                const opt = document.createElement('option');
                opt.value = model;
                opt.text = model;
                selector.appendChild(opt);
            });
        }
    } catch (e) {
        console.log("Failed to fetch models", e);
    }
}

async function applyModel() {
    const selector = document.getElementById('model-selector');
    if (!selector) return;
    const model = selector.value;
    log(`Switching AI model to ${model}...`);
    try {
        const res = await fetch('/api/set_model', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ model: model })
        });
        const data = await res.json();
        if (data.status === 'ok') {
            log(`Model switched to ${model}`);
        } else {
            log(`Failed to switch model: ${data.msg}`);
        }
    } catch (e) {
        log(`Error switching model: ${e}`);
    }
}

// === System Tools ===
function toggleAI() {
    fetch('/api/toggle_ai', { method: 'POST' });
}

function exportLogs() {
    const box = document.getElementById('log-box');
    if (!box) return;
    const logs = box.innerText;
    const blob = new Blob([logs], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url; a.download = 'system_logs.txt'; a.click();
}

async function showNetInfo() {
    try {
        const res = await fetch('/netinfo');
        const data = await res.json();
        let msg = "=== NETWORK INTERFACES ===\n\n";

        if (data.camera_net) {
            msg += `[CAMERA NET] (ESP32)\nName: ${data.camera_net.name}\nIP: ${data.camera_net.ip}\nMAC: ${data.camera_net.mac}\n\n`;
        } else {
            msg += `[CAMERA NET] Not Detected\n\n`;
        }

        if (data.internet_net) {
            msg += `[INTERNET/CAR NET]\nName: ${data.internet_net.name}\nIP: ${data.internet_net.ip}\nMAC: ${data.internet_net.mac}\n\n`;
        } else {
            msg += `[INTERNET/CAR NET] Not Detected\n\n`;
        }

        msg += "--- Other Interfaces ---\n";
        data.all_ifaces.forEach(iface => {
            if ((!data.camera_net || iface.name !== data.camera_net.name) &&
                (!data.internet_net || iface.name !== data.internet_net.name)) {
                msg += `${iface.name}: ${iface.ip}\n`;
            }
        });

        alert(msg);
        log("Network Info retrieved.");
    } catch (e) {
        alert("Failed to fetch network info");
    }
}

// === Camera Settings ===
const camState = {};

async function fetchCameraSettings() {
    try {
        const res = await fetch('/api/camera_settings');
        if (!res.ok) return;
        const data = await res.json();

        // Update UI
        const updateVal = (id, val) => {
            const el = document.getElementById(id);
            if (el) {
                el.value = val;
                const display = document.getElementById('val-' + id.replace('cfg-', ''));
                if (display) display.innerText = val;
            }
        };

        ['framesize', 'special_effect', 'wb_mode', 'quality', 'brightness', 'contrast', 'saturation'].forEach(key => {
            if (data[key] !== undefined) {
                updateVal('cfg-' + key, data[key]);
                camState[key] = data[key];
            }
        });

        ['awb', 'aec', 'aec2', 'agc', 'bpc', 'wpc', 'raw_gma', 'lenc', 'hmirror', 'vflip', 'dcw', 'colorbar'].forEach(key => {
            if (data[key] !== undefined) {
                camState[key] = data[key];
                const btn = document.getElementById('btn-' + key);
                if (btn) {
                    if (data[key] == 1) btn.classList.add('btn-active');
                    else btn.classList.remove('btn-active');
                }
            }
        });

        log("Camera settings synced.");

    } catch (e) {
        log("Failed to sync camera settings.");
    }
}

async function updateCameraSetting(varName, val) {
    camState[varName] = val;
    const display = document.getElementById('val-' + varName);
    if (display) display.innerText = val;

    try {
        await fetch('/api/camera_settings', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ var: varName, val: Number(val) })
        });
    } catch (e) {
        log(`Failed to set ${varName}`);
    }
}

function toggleCamBool(varName) {
    const current = camState[varName] || 0;
    const newVal = current ? 0 : 1;

    // Toggle visual
    const btn = document.getElementById('btn-' + varName);
    if (btn) {
        if (newVal) btn.classList.add('btn-active');
        else btn.classList.remove('btn-active');
    }

    updateCameraSetting(varName, newVal);
}

// Video Retry Logic (moved from main.js inner logic)
function initVideoRetry() {
    const img = document.getElementById('video-stream');
    const noSig = document.getElementById('no-sig');
    let retryTimeout = null;

    if (!img || !noSig) return;

    img.onerror = () => {
        // console.log("[VIDEO] Stream error/disconnect. Retrying in 2s...");
        img.style.display = 'none';
        noSig.style.display = 'flex';

        if (retryTimeout) clearTimeout(retryTimeout);

        retryTimeout = setTimeout(() => {
            img.src = "/video_feed?t=" + new Date().getTime();
        }, 2000);
    };

    img.onload = () => {
        // console.log("[VIDEO] Stream connected");
        img.style.display = 'block';
        noSig.style.display = 'none';
    };
}
window.initVideoRetry = initVideoRetry;
