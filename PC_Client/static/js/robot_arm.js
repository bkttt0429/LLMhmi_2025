
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
window.targetBaseAngle = 0;
window.targetShoulderAngle = 0;
window.targetElbowAngle = 0;
window.currentBaseAngle = 0;
window.currentShoulderAngle = 0;
window.currentElbowAngle = 0;

const controlSpeed = 0.03;

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
    camera3D = new THREE.PerspectiveCamera(45, container.clientWidth / container.clientHeight, 0.1, 1000);
    camera3D.position.set(5, 5, 5);
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
    controls3D.minDistance = 1;
    controls3D.maxDistance = 100;

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

function createCyberRobot() {
    const robotGroup = new THREE.Group();

    // Base (Glowing Cyan)
    const baseGeo = new THREE.CylinderGeometry(0.8, 1, 0.3, 16);
    const baseMat = new THREE.MeshStandardMaterial({
        color: 0x001a1a, emissive: 0x00ff99, emissiveIntensity: 0.3, metalness: 0.8, roughness: 0.2
    });
    basePart = new THREE.Mesh(baseGeo, baseMat);
    basePart.castShadow = true;
    basePart.receiveShadow = true;
    basePart.position.y = 0.15;
    robotGroup.add(basePart);

    // Shoulder (Glowing Green)
    const shoulderGeo = new THREE.BoxGeometry(0.4, 2, 0.4);
    const shoulderMat = new THREE.MeshStandardMaterial({
        color: 0x003300, emissive: 0x00ff66, emissiveIntensity: 0.4, metalness: 0.7, roughness: 0.3
    });
    shoulderPart = new THREE.Mesh(shoulderGeo, shoulderMat);
    shoulderPart.castShadow = true;
    shoulderPart.position.set(0, 1.3, 0);
    basePart.add(shoulderPart);

    // Elbow (Glowing Cyan)
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

    // Export parts for update
    window.basePart = basePart;
    window.shoulderPart = shoulderPart;
    window.elbowPart = elbowPart;

    updateStatus('ACTIVE', 'PLACEHOLDER');
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
                child.material.side = THREE.DoubleSide;
                // Add Glow if missing
                if (child.material.emissive && child.material.emissive.getHex() === 0) {
                    child.material.emissive = new THREE.Color(0x004400);
                    child.material.emissiveIntensity = 0.3;
                }
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

function autoRigModel() {
    console.log('[3D] Starting Auto-Rigging...');

    // 1. Create Kinematic Chain
    const virtualBase = new THREE.Group(); virtualBase.name = 'Virtual_Base';
    scene3D.add(virtualBase);
    const virtualShoulder = new THREE.Group(); virtualShoulder.name = 'Virtual_Shoulder';
    const virtualElbow = new THREE.Group(); virtualElbow.name = 'Virtual_Elbow';
    virtualBase.add(virtualShoulder);
    virtualShoulder.add(virtualElbow);
    virtualBase.updateMatrixWorld(true);

    // 2. Auto-Center
    const rawBox = new THREE.Box3().setFromObject(robotModel);
    const rawCenter = rawBox.getCenter(new THREE.Vector3());
    robotModel.position.x -= rawCenter.x;
    robotModel.position.z -= rawCenter.z;
    robotModel.position.y -= rawBox.min.y;
    robotModel.updateMatrixWorld(true);

    // 3. Setup Pivots
    const box = new THREE.Box3().setFromObject(robotModel);
    const height = box.getSize(new THREE.Vector3()).y;
    const minY = box.min.y;

    virtualShoulder.position.y = minY + height * 0.45;
    virtualElbow.position.y = (minY + height * 0.82) - virtualShoulder.position.y;

    // 4. Cluster Parts (Strict Logic per User Request)
    // C Group: Base (Priority)
    // A Group: Gripper
    // B Group: Arms
    const clusters = { base: [], shoulder: [], elbow: [], gripper: [] };
    const limits = { base: minY + height * 0.40, elbow: minY + height * 0.82 };

    // Grouping Helpers
    const isBase = (n) => ['m6', 'eba3_001', 'eba3_014', 'base', 'bottom'].some(k => n.includes(k));
    const isGripper = (n) => ['tower', 'm1', 'm2', 'finger', 'horn'].some(k => n.includes(k));
    const isArm = (n) => ['washer', 'step', 'm4', 'm3', 'brass', 'bearing', 'eba3'].some(k => n.includes(k));

    robotModel.traverse((child) => {
        if (child.isMesh) {
            const name = child.name.toLowerCase();
            const cy = new THREE.Box3().setFromObject(child).getCenter(new THREE.Vector3()).y;

            // Priority 1: Base (Group C)
            if (isBase(name)) {
                clusters.base.push(child);
            }
            // Priority 2: Gripper (Group A)
            else if (isGripper(name)) {
                clusters.gripper.push(child);
            }
            // Priority 3: Arms (Group B) -- Only if not strict Base
            else if (isArm(name)) {
                // Determine hierarchy by height
                if (cy < limits.elbow) clusters.shoulder.push(child);
                else clusters.elbow.push(child);
            }
            // Fallback for unclassified parts
            else {
                if (cy < limits.base) clusters.base.push(child);
                else if (cy < limits.elbow) clusters.shoulder.push(child);
                else clusters.elbow.push(child);
            }
        }
    });

    // 5. Attach
    // Note: Attaching removes from original parent, so traversal order matters if recursing, but we collected all meshes first.
    clusters.base.forEach(m => virtualBase.attach(m));
    clusters.shoulder.forEach(m => virtualShoulder.attach(m));
    clusters.elbow.forEach(m => virtualElbow.attach(m));

    const virtualGripper = new THREE.Group(); virtualGripper.name = 'Virtual_Gripper';
    virtualElbow.add(virtualGripper);
    clusters.gripper.forEach(m => virtualGripper.attach(m));

    // Export Groups for Highlighting (Store Arrays, not just Groups)
    // We attach the arrays to the virtual groups as userData for easy access
    virtualBase.userData.meshes = clusters.base;
    virtualShoulder.userData.meshes = clusters.shoulder; // Shoulder arm parts
    virtualElbow.userData.meshes = clusters.elbow;       // Elbow arm parts (upper arm)
    virtualGripper.userData.meshes = clusters.gripper;

    // Export globals
    window.basePart = basePart = virtualBase;
    window.shoulderPart = shoulderPart = virtualShoulder;
    window.elbowPart = elbowPart = virtualElbow;
    window.gripperPart = gripperPart = virtualGripper;

    // 6. Scale and Zoom
    virtualBase.scale.set(15, 15, 15);
    virtualBase.position.set(0, 0, 0);

    // Auto-Fit Camera
    const finalBox = new THREE.Box3().setFromObject(virtualBase);
    const finalCenter = finalBox.getCenter(new THREE.Vector3());
    const size = finalBox.getSize(new THREE.Vector3());
    const maxDim = Math.max(size.x, size.y, size.z);

    // Position slightly above and front
    const dist = maxDim * 1.5;
    camera3D.position.set(finalCenter.x, finalCenter.y + dist, finalCenter.z + dist);
    camera3D.lookAt(finalCenter);
    controls3D.target.copy(finalCenter);
    controls3D.update();
}

function updateStatus(status, mode) {
    const statusEl = document.getElementById('3d-status');
    const modeEl = document.getElementById('model-mode');
    if (statusEl) statusEl.textContent = status;
    if (modeEl) modeEl.textContent = mode;
}

function animate3D() {
    requestAnimationFrame(animate3D);

    if (controls3D) controls3D.update();

    // Lerp Angels
    window.currentBaseAngle = THREE.MathUtils.lerp(window.currentBaseAngle, window.targetBaseAngle, 0.1);
    window.currentShoulderAngle = THREE.MathUtils.lerp(window.currentShoulderAngle, window.targetShoulderAngle, 0.1);
    window.currentElbowAngle = THREE.MathUtils.lerp(window.currentElbowAngle, window.targetElbowAngle, 0.1);

    // Apply Rotation
    if (basePart) basePart.rotation.y = window.currentBaseAngle;
    if (shoulderPart) shoulderPart.rotation.z = window.currentShoulderAngle;
    if (elbowPart) elbowPart.rotation.z = window.currentElbowAngle;

    // Update Telemetry UI
    updateTelemetry();

    if (renderer3D && scene3D && camera3D) {
        renderer3D.render(scene3D, camera3D);
    }
}

function updateTelemetry() {
    const toDeg = (rad) => (rad * 180 / Math.PI).toFixed(1);

    const updateText = (id, val) => {
        const el = document.getElementById(id);
        if (el) el.textContent = toDeg(val) + '°';
    };

    updateText('angle-base', window.currentBaseAngle);
    updateText('angle-shoulder', window.currentShoulderAngle);
    updateText('angle-elbow', window.currentElbowAngle);

    const updateBar = (id, angle, max) => {
        const bar = document.getElementById(id);
        if (bar) {
            const pct = ((angle / max) + 1) / 2 * 100;
            bar.style.width = Math.abs(angle / max) * 50 + '%';
            bar.style.marginLeft = (angle < 0 ? (50 - Math.abs(angle / max) * 50) : 50) + '%';
        }
    };

    updateBar('bar-base', window.currentBaseAngle, Math.PI);
    updateBar('bar-shoulder', window.currentShoulderAngle, Math.PI / 2);
    updateBar('bar-elbow', window.currentElbowAngle, Math.PI / 2);
}

function onWindowResize() {
    const container = document.getElementById('canvas-3d-container');
    if (container && camera3D && renderer3D) {
        camera3D.aspect = container.clientWidth / container.clientHeight;
        camera3D.updateProjectionMatrix();
        renderer3D.setSize(container.clientWidth, container.clientHeight);
    }
}

// Global Exports
window.initRobot3D = initRobot3D;
window.resetRobotArm = () => {
    window.targetBaseAngle = 0;
    window.targetShoulderAngle = 0;
    window.targetElbowAngle = 0;
};

// Gamepad Integration Hook
window.updateRobotArmFromGamepad = (gp) => {
    // Enabled in Robot View AND Main View (since 3D is now in dashboard)
    if (window.currentView !== 'robot' && window.currentView !== 'main') return;

    if (!gp) return;

    // Right Stick X (Axis 2) -> Base Rotation
    // Right Stick Y (Axis 3) -> Shoulder & Elbow (Coordinated)
    let rightX = gp.axes[2] || 0;
    let rightY = gp.axes[3] || 0;

    // Fallback Removed: User requested strict separation. Left joystick does NOT affect arm.
    // if (Math.abs(rightX) < 0.05 && Math.abs(rightY) < 0.05) { ... }

    const deadzone = 0.15;
    const apply = (v) => Math.abs(v) < deadzone ? 0 : v;

    const fx = apply(rightX);
    const fy = apply(rightY);

    // Control Speed
    const speed = 0.05;

    window.targetBaseAngle += fx * speed;
    window.targetShoulderAngle += fy * speed;
    window.targetElbowAngle -= fy * speed * 0.8; // Inverse Elbow for natural movement

    // --- Highlighting Logic ---
    // Base Highlight: Purple (Frequency: Rotate)
    setHighlight(window.basePart, Math.abs(fx) > 0.1, 0x9900ff); // Purple

    // Arm Highlight: Cyan (Frequency: Move Up/Down)
    const armActive = Math.abs(fy) > 0.1;
    // Highlight "Arm Group" (Shoulder + Elbow parts)
    setHighlight(window.shoulderPart, armActive, 0x00ffff); // Cyan
    setHighlight(window.elbowPart, armActive, 0x00ffff);    // Cyan

    // Gripper Highlight: Red (Button A or 0)
    const gripperActive = (gp.buttons[0] && gp.buttons[0].pressed) || (gp.buttons[5] && gp.buttons[5].pressed); // A or RB
    setHighlight(window.gripperPart, gripperActive, 0xff0000); // Red

    // Gripper Animation
    if (window.gripperPart && gripperActive) {
        window.gripperPart.scale.setScalar(0.8);
    } else if (window.gripperPart) {
        window.gripperPart.scale.lerp(new THREE.Vector3(1, 1, 1), 0.2);
    }

    // ... [existing clamp code] ...
}

// ... [existing function] ...

function setHighlight(groupOrPart, active, colorHex) {
    if (!groupOrPart) return;

    // Strict Mode: Use the pre-calculated mesh list if available to avoid bleaching parents/children
    const targets = groupOrPart.userData && groupOrPart.userData.meshes ? groupOrPart.userData.meshes : [];

    if (targets.length > 0) {
        // Iterate only specific meshes in this group
        targets.forEach(mesh => {
            if (mesh.material && mesh.material.emissive) {
                if (!mesh.userData.baseEmissive) mesh.userData.baseEmissive = mesh.material.emissive.getHex();
                mesh.material.emissive.setHex(active ? colorHex : mesh.userData.baseEmissive);
                // Optional: Bump intensity on active
                mesh.material.emissiveIntensity = active ? 0.8 : 0.3;
            }
        });
    } else {
        // Fallback for placeholder objects (CyberRobot) which are simple groups
        groupOrPart.traverse(c => {
            if (c.isMesh && c.material && c.material.emissive) {
                if (!c.userData.baseEmissive) c.userData.baseEmissive = c.material.emissive.getHex();
                c.material.emissive.setHex(active ? colorHex : c.userData.baseEmissive);
            }
        });
    }
}
