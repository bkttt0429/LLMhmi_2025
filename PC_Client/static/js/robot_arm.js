// ==================== 3D ROBOT ARM SIMULATOR ====================
import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';

// State
let robot3DInitialized = false;
let scene3D, camera3D, renderer3D, controls3D;
let robotModel, basePart, shoulderPart, elbowPart, gripperPart;
let animationId;

// Export Logic State for Access
window.targetBaseAngle = 0.0; // 0.0 rad = 90 deg (Center)
window.targetShoulderAngle = 0.0;
window.targetElbowAngle = 0.0;
window.currentBaseAngle = 0.0;
window.currentShoulderAngle = 0.0;
window.currentElbowAngle = 0.0;

// Gamepad Helper: Deadzone
const deadzone = 0.15;
const apply = (v) => Math.abs(v) < deadzone ? 0 : v;

// ==================== MAIN INIT ====================
function initRobot3D() {
    if (robot3DInitialized) return;
    robot3DInitialized = true;
    window.robot3DInitialized = true;
    console.log('[3D] Initializing Robot Arm Simulator...');

    const container = document.getElementById('canvas-3d-container');
    if (!container) {
        console.error('[3D] Canvas container not found!');
        return;
    }

    // Scene Setup
    scene3D = new THREE.Scene();
    scene3D.background = new THREE.Color(0x222222);
    window.scene3D = scene3D; // Debug access

    // Camera
    camera3D = new THREE.PerspectiveCamera(45, container.clientWidth / container.clientHeight, 0.01, 1000);
    camera3D.position.set(-0.28, 0.40, -0.01); // Calibrated Zoom
    window.camera3D = camera3D;

    // Renderer
    renderer3D = new THREE.WebGLRenderer({ antialias: true, alpha: false });
    renderer3D.setSize(container.clientWidth, container.clientHeight);
    renderer3D.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer3D.shadowMap.enabled = true;
    renderer3D.shadowMap.type = THREE.PCFSoftShadowMap;
    renderer3D.toneMapping = THREE.ACESFilmicToneMapping;
    renderer3D.toneMappingExposure = 1.2;
    container.appendChild(renderer3D.domElement);
    window.renderer3D = renderer3D;

    // Controls
    controls3D = new OrbitControls(camera3D, renderer3D.domElement);
    controls3D.enableDamping = true;
    controls3D.dampingFactor = 0.05;
    controls3D.minDistance = 0.01;
    controls3D.maxDistance = 100;
    // Set Target to center of base (approx)
    controls3D.target.set(0, 0.15, 0);
    controls3D.update();

    // Lighting
    const ambientLight = new THREE.AmbientLight(0x00ff99, 0.4);
    scene3D.add(ambientLight);

    const mainLight = new THREE.DirectionalLight(0x00ffaa, 1.2);
    mainLight.position.set(10, 15, 10);
    mainLight.castShadow = true;
    mainLight.shadow.mapSize.width = 2048;
    mainLight.shadow.mapSize.height = 2048;
    scene3D.add(mainLight);

    const fillLight = new THREE.DirectionalLight(0x00ddff, 0.5);
    fillLight.position.set(-5, 5, -5);
    scene3D.add(fillLight);

    const rimLight = new THREE.PointLight(0x00ff99, 0.8, 30);
    rimLight.position.set(0, 8, -8);
    scene3D.add(rimLight);

    // Grid & Ground
    const gridHelper = new THREE.GridHelper(20, 20, 0x00ff99, 0x003322);
    gridHelper.material.opacity = 0.3;
    gridHelper.material.transparent = true;
    scene3D.add(gridHelper);

    const groundGeometry = new THREE.PlaneGeometry(20, 20);
    const groundMaterial = new THREE.ShadowMaterial({ opacity: 0.4 });
    const ground = new THREE.Mesh(groundGeometry, groundMaterial);
    ground.rotation.x = -Math.PI / 2;
    ground.receiveShadow = true;
    scene3D.add(ground);

    // Load Model
    loadModel();

    // Start Animation Loop
    animate3D();

    // Event Listeners
    window.addEventListener('resize-3d', onWindowResize);
}

function loadModel() {
    const gltfLoader = new GLTFLoader();
    const modelPath = './models/eezybotarm.glb';

    gltfLoader.load(
        modelPath,
        (gltf) => {
            handleModelLoaded(gltf);
        },
        undefined,
        (error) => {
            console.warn('[3D] GLB load failed, using placeholder:', error);
            createCyberRobot();
        }
    );

    // Timeout Fallback
    setTimeout(() => {
        if (!robotModel) createCyberRobot();
    }, 2000);
}

function handleModelLoaded(gltf) {
    robotModel = gltf.scene;
    robotModel.position.set(0, 0, 0);
    scene3D.add(robotModel);

    // Force Update
    scene3D.updateMatrixWorld(true);

    // Cyber Material Update
    robotModel.traverse((child) => {
        if (child.isMesh) {
            child.castShadow = true;
            child.receiveShadow = true;
            if (child.material) {
                // CLONE MATERIAL to prevent shared-material side effects
                child.material = child.material.clone();
                child.material.side = THREE.DoubleSide;
                if (child.material.emissive && child.material.emissive.getHex() === 0) {
                    child.material.emissive = new THREE.Color(0x004400); // Default Cyber Green
                    child.material.emissiveIntensity = 0.3;
                }
                child.userData.baseEmissive = child.material.emissive.getHex();
            }
        }
    });

    try {
        autoRigModel();
        updateStatus('ACTIVE', 'GLB MODEL');
    } catch (e) {
        console.error('[3D] Auto-Rigging Failed:', e);
        robotModel.position.set(0, -3, 0); // Fallback position
    }
}

function createCyberRobot() {
    const robotGroup = new THREE.Group();

    // Base
    const baseGeo = new THREE.CylinderGeometry(0.8, 1, 0.3, 16);
    const baseMat = new THREE.MeshStandardMaterial({
        color: 0x001a1a, emissive: 0x00ff99, emissiveIntensity: 0.3, metalness: 0.8, roughness: 0.2
    });
    basePart = new THREE.Mesh(baseGeo, baseMat);
    basePart.castShadow = true;
    basePart.receiveShadow = true;
    basePart.position.y = 0.15;
    robotGroup.add(basePart);

    // Shoulder
    const shoulderGeo = new THREE.BoxGeometry(0.4, 2, 0.4);
    const shoulderMat = new THREE.MeshStandardMaterial({
        color: 0x003300, emissive: 0x00ff66, emissiveIntensity: 0.4, metalness: 0.7, roughness: 0.3
    });
    shoulderPart = new THREE.Mesh(shoulderGeo, shoulderMat);
    shoulderPart.castShadow = true;
    shoulderPart.position.set(0, 1.3, 0);
    basePart.add(shoulderPart);

    // Elbow
    const elbowGeo = new THREE.BoxGeometry(0.3, 1.5, 0.3);
    const elbowMat = new THREE.MeshStandardMaterial({
        color: 0x001a33, emissive: 0x00aaff, emissiveIntensity: 0.4, metalness: 0.7, roughness: 0.3
    });
    elbowPart = new THREE.Mesh(elbowGeo, elbowMat);
    elbowPart.castShadow = true;
    elbowPart.position.set(0, 1.5, 0);
    shoulderPart.add(elbowPart);

    scene3D.add(robotGroup);
    robotModel = robotGroup;

    // Export parts
    window.basePart = basePart;
    window.shoulderPart = shoulderPart;
    window.elbowPart = elbowPart;

    updateStatus('ACTIVE', 'PLACEHOLDER');
}

function autoRigModel() {
    console.log('[3D] Starting Auto-Rigging...');
    const box = new THREE.Box3().setFromObject(robotModel);
    const size = box.getSize(new THREE.Vector3());
    let minY = box.min.y;
    const height = size.y;

    if (minY < -0.01) {
        const offset = -minY;
        robotModel.position.y += offset;
        robotModel.updateMatrixWorld(true);
        box.setFromObject(robotModel);
        minY = box.min.y;
    }

    const pivotShoulderY = minY + height * 0.25;
    const pivotElbowY = minY + height * 0.70;
    const pivotGripperY = minY + height * 0.95;

    // Rig Groups (Kinematic Chain)
    const rigBase = new THREE.Group(); rigBase.name = 'Rig_Base'; scene3D.add(rigBase);
    const rigLowerArm = new THREE.Group(); rigLowerArm.name = 'Rig_LowerArm'; rigLowerArm.position.set(0, pivotShoulderY, 0); rigBase.add(rigLowerArm);
    const rigUpperArm = new THREE.Group(); rigUpperArm.name = 'Rig_UpperArm'; rigUpperArm.position.set(0, pivotElbowY - pivotShoulderY, 0); rigLowerArm.add(rigUpperArm);
    const rigGripper = new THREE.Group(); rigGripper.name = 'Rig_Gripper'; rigGripper.position.set(0, pivotGripperY - pivotElbowY, 0); rigUpperArm.add(rigGripper);

    const clusters = { base: [], lowerArm: [], upperArm: [], gripper: [] };

    // Strict Hardware Lists (Simplified for Reconstruction)
    const UPPER_ARM_HARDWARE = ["eba3_006", "upper", "ecrou", "m3 nuts", "din7991_m3x22mm", "din912_m4x25mm_2_m4 bolts"];
    const LOWER_ARM_HARDWARE = ["eba3_005", "step", "motor", "din912", "m4_washer"];
    const GRIPPER_HARDWARE = ["finger", "horn", "gear", "tower", "din7991_m3x16mm"];
    const isPart = (name, list) => list.some(k => name.includes(k.toLowerCase()));

    robotModel.traverse((child) => {
        if (child.isMesh) {
            const name = child.name.toLowerCase();
            const cy = new THREE.Box3().setFromObject(child).getCenter(new THREE.Vector3()).y;

            if (isPart(name, GRIPPER_HARDWARE)) clusters.gripper.push(child);
            else if (isPart(name, UPPER_ARM_HARDWARE)) clusters.upperArm.push(child);
            else if (isPart(name, LOWER_ARM_HARDWARE)) clusters.lowerArm.push(child);
            else if (['base', 'bottom', 'eba3_001', 'eba3_014'].some(k => name.includes(k))) clusters.base.push(child);
            else {
                // Spatial Fallback
                if (cy > pivotGripperY) clusters.gripper.push(child);
                else if (cy > pivotElbowY) clusters.upperArm.push(child);
                else if (cy > pivotShoulderY) clusters.lowerArm.push(child);
                else clusters.base.push(child);
            }
        }
    });

    clusters.base.forEach(m => rigBase.attach(m));
    clusters.lowerArm.forEach(m => rigLowerArm.attach(m));
    clusters.upperArm.forEach(m => rigUpperArm.attach(m));
    clusters.gripper.forEach(m => rigGripper.attach(m));

    rigBase.userData.meshes = clusters.base;
    rigLowerArm.userData.meshes = clusters.lowerArm;
    rigUpperArm.userData.meshes = clusters.upperArm;
    rigGripper.userData.meshes = clusters.gripper;

    window.basePart = basePart = rigBase;
    window.shoulderPart = shoulderPart = rigLowerArm;
    window.elbowPart = elbowPart = rigUpperArm;
    window.gripperPart = gripperPart = rigGripper;

    // Optional: Visual Auto-Fit Camera
    const finalCenter = new THREE.Box3().setFromObject(rigBase).getCenter(new THREE.Vector3());
    controls3D.target.copy(finalCenter);
    controls3D.update();
}

// ==================== ANIMATION LOOP ====================
function animate3D() {
    animationId = requestAnimationFrame(animate3D);
    if (controls3D) controls3D.update();

    // Lerp Output
    window.currentBaseAngle = THREE.MathUtils.lerp(window.currentBaseAngle, window.targetBaseAngle, 0.1);
    window.currentShoulderAngle = THREE.MathUtils.lerp(window.currentShoulderAngle, window.targetShoulderAngle, 0.1);
    window.currentElbowAngle = THREE.MathUtils.lerp(window.currentElbowAngle, window.targetElbowAngle, 0.1);

    // Logic Output
    if (typeof updateBasePhysics === 'function') updateBasePhysics(); // [NEW] Run Physics Loop

    // Apply Rotation
    if (basePart) basePart.rotation.y = window.currentBaseAngle;
    if (shoulderPart) shoulderPart.rotation.z = window.currentShoulderAngle;
    if (elbowPart) elbowPart.rotation.z = window.currentElbowAngle;

    updateTelemetry();
    if (renderer3D && scene3D && camera3D) renderer3D.render(scene3D, camera3D);
}

function updateTelemetry() {
    const toDeg = (rad) => (rad * 180 / Math.PI).toFixed(1);
    const updateText = (id, val) => { const el = document.getElementById(id); if (el) el.textContent = toDeg(val) + '°'; };

    updateText('angle-base', window.currentBaseAngle);
    updateText('angle-shoulder', window.currentShoulderAngle);
    updateText('angle-elbow', window.currentElbowAngle);

    const updateBar = (id, angle, max) => {
        const bar = document.getElementById(id);
        if (bar) {
            bar.style.width = Math.abs(angle / max) * 50 + '%';
            bar.style.marginLeft = (angle < 0 ? (50 - Math.abs(angle / max) * 50) : 50) + '%';
        }
    };
    updateBar('bar-base', window.currentBaseAngle, Math.PI);
    updateBar('bar-shoulder', window.currentShoulderAngle, Math.PI / 2);
    updateBar('bar-elbow', window.currentElbowAngle, Math.PI / 2);
}

function updateStatus(status, mode) {
    const s = document.getElementById('3d-status'); if (s) s.textContent = status;
    const m = document.getElementById('model-mode'); if (m) m.textContent = mode;
}

function onWindowResize() {
    const c = document.getElementById('canvas-3d-container');
    if (c && camera3D && renderer3D) {
        camera3D.aspect = c.clientWidth / c.clientHeight;
        camera3D.updateProjectionMatrix();
        renderer3D.setSize(c.clientWidth, c.clientHeight);
    }
}

// ==================== PHYSICS ENGINE (Base Servo) ====================
// [DISABLED] Physics engine removed in favor of direct Rate Control in gamepad.js
/*
const basePhysics = {
    current: 90,       // Current PWM (90 = Stop)
    target: 90,        // Target PWM based on input (from Gamepad)
    step: 0.8,         // Acceleration Rate (Change per Frame). Lower = Slower Ramp.
    lastDir: 0,        // -1 (CW), 0 (Stop), 1 (CCW)
    pauseUntil: 0,     // Timestamp to wait until
    pauseDuration: 300 // ms to wait on reversal
};

function updateBasePhysics() {
    const now = Date.now();

    // 1. Reversal Check
    // If we are moving (current != 90) and want to move opposite (target vs current),
    // OR if we were moving one way and want to go OTHER way immediately.
    let currentDir = Math.sign(basePhysics.current - 90);
    // Treat near-90 as 0 for stability
    if (Math.abs(basePhysics.current - 90) < 1) currentDir = 0;

    let targetDir = Math.sign(basePhysics.target - 90);

    // Use Pause State.
    if (targetDir !== 0 && basePhysics.lastDir !== 0 && targetDir !== basePhysics.lastDir) {
        if (basePhysics.pauseUntil === 0) {
            // Start Pause Timer
            basePhysics.pauseUntil = now + basePhysics.pauseDuration;
        }
    }

    // If Paused
    if (now < basePhysics.pauseUntil) {
        // Wait period, no change to Current towards Target yet?
        // Actually, if we are in Pause, we ideally want to Stop.
        // But the Loop below drives Current -> Target.
        // If we want to Pause, we should temporarily make Target = 90.
        // However, basePhysics.target is set by Gamepad every frame.
        // So we need a LOCAL override here.

        // Simpler Logic: FORCE current 90 if in pause?
        // No, that's jerky. 
        // We let it ramp to 90 normally. Once it hits 90, if Timer is Active, we Hold 90.

        // Wait: The timer is set when Reversal Detected.
        // Reversal assumes we are already moving?
        // Actually, easiest: Only allow Target update if Timer expired.
        // But Gamepad updates Target!
    }

    // 3. Ramping (Linear Interpolation) with Pause Override
    let effectiveTarget = basePhysics.target;

    if (now < basePhysics.pauseUntil) {
        effectiveTarget = 90; // Force Stop during Pause
    }

    if (basePhysics.current < effectiveTarget) {
        basePhysics.current += basePhysics.step;
        if (basePhysics.current > effectiveTarget) basePhysics.current = effectiveTarget;
    } else if (basePhysics.current > effectiveTarget) {
        basePhysics.current -= basePhysics.step;
        if (basePhysics.current < effectiveTarget) basePhysics.current = effectiveTarget;
    }

    // Update Direction Memory
    if (Math.abs(basePhysics.current - 90) >= 1) {
        basePhysics.lastDir = Math.sign(basePhysics.current - 90);
    }

    // Export to Global for sendArmData
    window.baseCommandOverride = Math.round(basePhysics.current);
}
*/

// ==================== GAMEPAD LOGIC ====================
// [DISABLED] Moved to gamepad.js (RobotArmController)
/*
// ⭐ Updated for Continuous Rotation and Fixed Speed
window.updateRobotArmFromGamepad = (gp) => {
    if (!gp) return;

    // Right Stick X (Axis 2) -> Base
    // Right Stick Y (Axis 3) -> Shoulder/Elbow
    let rightX = gp.axes[2] || 0;
    let rightY = gp.axes[3] || 0;

    const fx = apply(rightX);
    const fy = apply(rightY);
    const speed = 0.05;

    // --- Base Logic (Continuous) with Dynamic Torque Slider ---
    const torqueEl = document.getElementById('base-torque-slider');
    const torqueValEl = document.getElementById('base-torque-val');
    let torqueOffset = 45; // Default

    if (torqueEl) {
        torqueOffset = parseInt(torqueEl.value);
        if (torqueValEl) torqueValEl.textContent = torqueOffset;
    }

    // 1. Calculate Desired Target
    let desiredTarget = 90;
    if (Math.abs(fx) > 0.1) {
        window.targetBaseAngle += fx * speed;
        if (fx > 0) desiredTarget = 90 + torqueOffset; // CCW
        else desiredTarget = 90 - torqueOffset; // CW

        // Smart Reversal Trigger
        // If we want to move, and we are currently opposite, TRIGGER PAUSE
        // But updateBasePhysics handles this now.
        // We just feed the Target.
        basePhysics.target = desiredTarget;

    } else {
        basePhysics.target = 90; // Stop
    }

    // --- Standard Joints (Positional) ---
    window.targetShoulderAngle += fy * speed;
    window.targetElbowAngle -= fy * speed * 0.8;

    // Highlights
    setHighlight(window.basePart, Math.abs(fx) > 0.1, 0x9900ff);
    const armActive = Math.abs(fy) > 0.1;
    setHighlight(window.shoulderPart, armActive, 0x00ffff);
    setHighlight(window.elbowPart, armActive, 0x00ffff);

    // Clamping (Radians)
    window.targetShoulderAngle = Math.max(-1.57, Math.min(1.57, window.targetShoulderAngle));
    window.targetElbowAngle = Math.max(-1.57, Math.min(1.57, window.targetElbowAngle));
};
*/

function setHighlight(obj, active, color) {
    if (!obj) return;
    const meshes = obj.userData && obj.userData.meshes ? obj.userData.meshes : [];
    const applyColor = (m) => {
        if (m.material && m.material.emissive) {
            if (m.userData.baseEmissive === undefined) m.userData.baseEmissive = m.material.emissive.getHex();
            m.material.emissive.setHex(active ? color : m.userData.baseEmissive);
            m.material.emissiveIntensity = active ? 0.8 : 0.3;
        }
    };
    if (meshes.length) meshes.forEach(applyColor);
    else obj.traverse((c) => { if (c.isMesh) applyColor(c); });
}

// ==================== NETWORK LOGIC ====================
// [DISABLED] Network logic moved to gamepad.js (WebSocket)
/*
// Helper: Radians to Servo Degrees (0-180)
function toServo(rad) {
    // 0 rad = 90 deg. -1.57 = 0 deg. 1.57 = 180 deg.
    // Formula: (rad * (180/PI)) + 90
    // Example: 0 * 57 + 90 = 90. Correct.
    let deg = (rad * 180 / Math.PI) + 90;
    return Math.max(0, Math.min(180, Math.floor(deg)));
}

function getGripperAngle() {
    if (window.gripperPart && window.gripperPart.scale.x < 0.9) return 180;
    return 0;
}

let lastSentTime = 0;
let lastPayloadStr = "";
const SEND_INTERVAL = 100;
const HEARTBEAT_INTERVAL = 2000;

function sendArmData() {
    const now = Date.now();

    let baseVal = 90;
    if (window.baseCommandOverride !== undefined) {
        baseVal = window.baseCommandOverride;
    } else {
        baseVal = toServo(window.targetBaseAngle);
    }

    const payload = {
        base: baseVal,
        shoulder: toServo(window.targetShoulderAngle),
        elbow: toServo(window.targetElbowAngle),
        gripper: getGripperAngle()
    };

    const payloadStr = JSON.stringify(payload);

    if (payloadStr !== lastPayloadStr || (now - lastSentTime > HEARTBEAT_INTERVAL)) {
        lastSentTime = now;
        lastPayloadStr = payloadStr;
        fetch('/api/arm', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: payloadStr
        }).catch(e => { }); // Silent fail
    }
}

// Start Network Loop
setInterval(sendArmData, SEND_INTERVAL);
*/

// Exports
window.initRobot3D = initRobot3D;
window.resetRobotArm = () => {
    window.targetBaseAngle = 0; window.targetShoulderAngle = 0; window.targetElbowAngle = 0;
    // window.baseCommandOverride = 90;
    // basePhysics.current = 90;
    // basePhysics.target = 90;
};
