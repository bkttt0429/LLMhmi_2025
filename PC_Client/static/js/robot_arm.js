
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
    camera3D = new THREE.PerspectiveCamera(45, container.clientWidth / container.clientHeight, 0.01, 1000);
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
    controls3D.minDistance = 0.01;
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
                // CLONE MATERIAL to prevent shared-material side effects (bleeding colors)
                child.material = child.material.clone();

                child.material.side = THREE.DoubleSide;
                // Add Glow if missing
                if (child.material.emissive && child.material.emissive.getHex() === 0) {
                    child.material.emissive = new THREE.Color(0x004400); // Default Cyber Green
                    child.material.emissiveIntensity = 0.3;
                }

                // Store initial state IMMEDIATELY to be safe
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

function autoRigModel() {
    console.log('[3D] Starting Auto-Rigging (Hierarchy Strategy)...');

    // 1. Analyze Geometry for Pivots
    const box = new THREE.Box3().setFromObject(robotModel);
    const size = box.getSize(new THREE.Vector3());
    const center = box.getCenter(new THREE.Vector3());
    const minY = box.min.y;
    const height = size.y;

    console.log(`[3D] Model Height: ${height.toFixed(2)}, MinY: ${minY.toFixed(2)}`);

    // Pivot Estimates relative to Model Base (minY)
    // These ratios are tuned for EEZYbotARM MK2/MK3 geometry
    const pivotShoulderY = minY + height * 0.42;
    const pivotElbowY = minY + height * 0.81;
    const pivotGripperY = minY + height * 0.95; // Rough estimate for gripper base

    // 2. Create Kinematic Groups (The "Rig")
    // Structure: Base -> LowerArm (Shoulder) -> UpperArm (Elbow) -> Gripper

    // RIG_BASE (Rotates Y)
    const rigBase = new THREE.Group();
    rigBase.name = 'Rig_Base';
    // Base sits at the model's bottom center
    rigBase.position.set(0, 0, 0);
    scene3D.add(rigBase);

    // RIG_LOWER_ARM (Rotates Z) - "Shoulder"
    const rigLowerArm = new THREE.Group();
    rigLowerArm.name = 'Rig_LowerArm';
    // pivot relative to Base
    rigLowerArm.position.set(0, pivotShoulderY, 0);
    rigBase.add(rigLowerArm);

    // RIG_UPPER_ARM (Rotates Z) - "Elbow"
    const rigUpperArm = new THREE.Group();
    rigUpperArm.name = 'Rig_UpperArm';
    // pivot relative to LowerArm
    rigUpperArm.position.set(0, pivotElbowY - pivotShoulderY, 0);
    rigLowerArm.add(rigUpperArm);

    // RIG_GRIPPER (Rotates ?)
    const rigGripper = new THREE.Group();
    rigGripper.name = 'Rig_Gripper';
    // pivot relative to UpperArm
    rigGripper.position.set(0, pivotGripperY - pivotElbowY, 0);
    rigUpperArm.add(rigGripper);

    // 3. Categorize Meshes (Filtering Logic)
    const clusters = { base: [], lowerArm: [], upperArm: [], gripper: [] };

    // Grouping Helpers (Renamed to avoid scope conflicts)

    // Base: Structural parts only
    const checkBase = (n) =>
        ['eba3_001', 'eba3_014', 'base', 'bottom'].some(k => n.includes(k));

    // Gripper: Distinctive parts
    const checkGripper = (n) =>
        ['tower', 'finger', 'horn', 'gear'].some(k => n.includes(k));

    // Upper Arm: Specific parts
    const checkUpperArm = (n) =>
        ['eba3_006', 'upper'].some(k => n.includes(k));

    // Lower Arm: Specific parts
    const checkLowerArm = (n) =>
        ['eba3_005', 'step', 'motor'].some(k => n.includes(k));

    // Generic bits that are scattered everywhere - DO NOT put in specific lists:
    // 'm1', 'm2', 'm3', 'm4', 'm5', 'm6', 'washer', 'bearing', 'nut', 'bolt', 'din'

    robotModel.updateMatrixWorld(true); // Ensure world transforms are current

    robotModel.traverse((child) => {
        if (child.isMesh) {
            const name = child.name.toLowerCase();
            const cy = new THREE.Box3().setFromObject(child).getCenter(new THREE.Vector3()).y;

            // Strict Rules for Main Structural Parts
            if (checkGripper(name)) {
                clusters.gripper.push(child);
            } else if (checkUpperArm(name)) {
                clusters.upperArm.push(child);
            } else if (checkLowerArm(name)) {
                clusters.lowerArm.push(child);
            } else if (checkBase(name)) {
                clusters.base.push(child);
            }
            // Spatial Logic for ALL Generic Hardware (Screws, Washers, etc.)
            // and any unrecognized parts
            else {
                // Determine hierarchy by height relative to calculated pivots
                // Gripper Zone
                if (cy > pivotGripperY) {
                    clusters.gripper.push(child);
                }
                // Upper Arm Zone
                else if (cy > pivotElbowY) {
                    clusters.upperArm.push(child);
                }
                // Lower Arm Zone
                else if (cy > pivotShoulderY) {
                    clusters.lowerArm.push(child);
                }
                // Base Zone
                else {
                    clusters.base.push(child);
                }
            }
        }
    });

    console.log(`[3D] Categorization: Base=${clusters.base.length}, Lower=${clusters.lowerArm.length}, Upper=${clusters.upperArm.length}, Gripper=${clusters.gripper.length}`);

    // 4. Attach Meshes to Rigs
    // Using .attach() preserves the world transform while reparenting
    clusters.base.forEach(m => rigBase.attach(m));
    clusters.lowerArm.forEach(m => rigLowerArm.attach(m));
    clusters.upperArm.forEach(m => rigUpperArm.attach(m));
    clusters.gripper.forEach(m => rigGripper.attach(m));

    // Store clustered meshes in userData for isolated highlighting
    rigBase.userData.meshes = clusters.base;
    rigLowerArm.userData.meshes = clusters.lowerArm;
    rigUpperArm.userData.meshes = clusters.upperArm;
    rigGripper.userData.meshes = clusters.gripper;

    // 5. Update Global References for Animation Loop
    window.basePart = rigBase;
    window.shoulderPart = rigLowerArm;  // Maps to "Shoulder" control
    window.elbowPart = rigUpperArm;     // Maps to "Elbow" control
    window.gripperPart = rigGripper;

    // CRITICAL FIX: Update Module-Scope Variables for animate3D()
    basePart = rigBase;
    shoulderPart = rigLowerArm;
    elbowPart = rigUpperArm;
    gripperPart = rigGripper;

    // 6. Camera Auto-Fit (Zoomed In)
    const finalBox = new THREE.Box3().setFromObject(rigBase);
    const finalCenter = finalBox.getCenter(new THREE.Vector3());
    const finalSize = finalBox.getSize(new THREE.Vector3());
    const maxDim = Math.max(finalSize.x, finalSize.y, finalSize.z);

    // Closer Zoom: 0.9 optimal (Balanced)
    const dist = maxDim * 0.9;
    camera3D.position.set(finalCenter.x + dist, finalCenter.y + dist * 0.5, finalCenter.z + dist * 1.0);
    camera3D.lookAt(finalCenter);
    controls3D.target.copy(finalCenter);
    controls3D.update();

    // 7. Visual Debug Helpers (Optional - Uncomment to see skeletons)
    // const axes1 = new THREE.AxesHelper(5); rigBase.add(axes1);
    // const axes2 = new THREE.AxesHelper(5); rigLowerArm.add(axes2);
    // const axes3 = new THREE.AxesHelper(5); rigUpperArm.add(axes3);
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
    // Debug: Log view and gp state occasionally
    // if (Math.random() < 0.01) console.log(`[3D-DEBUG] View: ${window.currentView}, GP: ${!!gp}`);

    // IGNORE VIEW CHECK TEMPORARILY for debugging
    // if (window.currentView !== 'robot' && window.currentView !== 'main') return;

    if (!gp) return;

    // Right Stick X (Axis 2) -> Base Rotation
    // Right Stick Y (Axis 3) -> Shoulder & Elbow (Coordinated)
    let rightX = gp.axes[2] || 0;
    let rightY = gp.axes[3] || 0;

    // Debug Input
    if (Math.abs(rightX) > 0.2 || Math.abs(rightY) > 0.2) {
        // console.log(`[3D-INPUT] RX: ${rightX.toFixed(2)}, RY: ${rightY.toFixed(2)}`);
    }

    const deadzone = 0.15;
    const apply = (v) => Math.abs(v) < deadzone ? 0 : v;

    const fx = apply(rightX);
    const fy = apply(rightY);

    // Control Speed
    const speed = 0.05;

    window.targetBaseAngle += fx * speed;
    window.targetShoulderAngle += fy * speed;
    window.targetElbowAngle -= fy * speed * 0.8; // Inverse Elbow for natural movement

    // Check if parts exist
    if (!window.basePart) {
        // console.warn("[3D] window.basePart is missing!");
    } else {
        // console.log(`[3D] Base Rot: ${window.basePart.rotation.y.toFixed(2)} -> Target: ${window.targetBaseAngle.toFixed(2)}`);
    }

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

    // Angle Clamping
    window.targetShoulderAngle = Math.max(-1.0, Math.min(1.0, window.targetShoulderAngle));
    window.targetElbowAngle = Math.max(-1.5, Math.min(1.5, window.targetElbowAngle));
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
                // Fix: Check undefined strictly, as 0 (blackness) is falsy
                if (mesh.userData.baseEmissive === undefined) mesh.userData.baseEmissive = mesh.material.emissive.getHex();

                mesh.material.emissive.setHex(active ? colorHex : mesh.userData.baseEmissive);
                // Optional: Bump intensity on active
                mesh.material.emissiveIntensity = active ? 0.8 : 0.3;
            }
        });
    } else {
        // Fallback for placeholder objects (CyberRobot) which are simple groups
        groupOrPart.traverse(c => {
            if (c.isMesh && c.material && c.material.emissive) {
                if (c.userData.baseEmissive === undefined) c.userData.baseEmissive = c.material.emissive.getHex();
                c.material.emissive.setHex(active ? colorHex : c.userData.baseEmissive);
            }
        });
    }
}
