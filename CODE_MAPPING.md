# System Implementation & Code Mapping

This document provides a detailed mapping between the system's logical implementation flowcharts and the actual source code. Each section corresponds to a specific flowchart node, providing the logic description and the associated code segment.

---

## 1. Web Implementation (`web_impl_flow.drawio`)

### Node (1): Window Load
*   **File:** `PC_Client/static/js/main.js`
*   **Lines:** 15 - 28
*   **Description:** The application entry point. It initializes WebSocket connections, canvas resizing, and the main animation loop. It also conditionally loads subsystems like the robot arm 3D simulator (`initRobot3D`) and input controls.

```javascript
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
```

### Node (2): Connect SocketIO
*   **File:** `PC_Client/static/js/main.js`
*   **Lines:** 39 - 48
*   **Description:** Establishes a bidirectional real-time communication channel with the Python Flask server using `Socket.IO`. It handles connection events and updates global state `wsConnected`.

```javascript
function initWebSocket() {
    // Initialize Socket.IO
    socket = io({ transports: ['websocket'] });
    window.socket = socket;

    socket.on('connect', () => {
        wsConnected = true;
        window.wsConnected = true;
        log("WS Connected");
    });
    // ...
}
```

### Node (3): Init Three.js
*   **File:** `PC_Client/static/js/robot_arm.js`
*   **Lines:** 23 - 43
*   **Description:** Initializes the 3D rendering environment. It creates the `THREE.Scene`, `PerspectiveCamera`, and `WebGLRenderer`. This function sets the foundation for the visual digital twin of the robot arm.

```javascript
function initRobot3D() {
    if (robot3DInitialized) return;
    robot3DInitialized = true;
    window.robot3DInitialized = true;
    console.log('[3D] Initializing Robot Arm Simulator...');

    const container = document.getElementById('canvas-3d-container');
    // ...
    // Scene Setup
    scene3D = new THREE.Scene();
    scene3D.background = new THREE.Color(0x222222);
    
    // Camera
    camera3D = new THREE.PerspectiveCamera(45, container.clientWidth / container.clientHeight, 0.01, 1000);
    // ...
}
```

### Node (5): Poll Gamepad API
*   **File:** `PC_Client/static/js/gamepad.js`
*   **Lines:** 161 - 165
*   **Description:** The `updateJoystickLoop` functions as the main input loop. It uses the browser's `navigator.getGamepads()` API to fetch the real-time state of connected controllers (e.g., Xbox Controller).

```javascript
function updateJoystickLoop() {
    const gamepads = navigator.getGamepads ? navigator.getGamepads() : [];
    const gp = gamepads[0];

    if (!gp || !gp.connected) return;

    // Heartbeat & Status Update
    window.lastXboxUpdate = Date.now();
    // ...
}
```

### Node (6): Process Axes
*   **File:** `PC_Client/static/js/gamepad.js`
*   **Lines:** 201 - 215
*   **Description:** Processes raw analog stick inputs. It applies a deadzone calculation to filter out noise (`applyDeadzone`) and mixes the Throttle (Y-axis) and Steering (X-axis) values to calculate differential drive speeds.

```javascript
    // Deadzone
    const DEADZONE = 0.15;
    const applyDeadzone = (val) => Math.abs(val) < DEADZONE ? 0 : val;

    let steer = applyDeadzone(rawX);
    let throttle = -applyDeadzone(rawY); // Invert Y

    // Mixing Strategy
    let leftVal = throttle + steer;
    let rightVal = throttle - steer;
```

### Node (8): Emit control_cmd
*   **File:** `PC_Client/static/js/gamepad.js`
*   **Lines:** 132 - 144
*   **Description:** Sends the calculated motor values to the backend. It prioritizes `WebSocket` for low latency but includes an `HTTP POST` fallback if the socket is disconnected.

```javascript
function emitControlCommand(left, right) {
    // 1. WebSocket (Preferred)
    if (window.socket && window.wsConnected) {
        window.socket.emit('control_command', { left: left, right: right });
    } else {
        // 2. HTTP Fallback
        fetch('/api/control', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ left: left, right: right })
        }).catch(e => { console.error("Control Error", e); });
    }
}
```

### Node (9): Update Target Angles (IK)
*   **File:** `PC_Client/static/js/robot_arm.js`
*   **Lines:** 454 - 476
*   **Description:** Maps gamepad inputs to the robot arm's joint angles. It increments or decrements target angles based on joystick deflection, implementing a basic velocity control system for the arm.

```javascript
window.updateRobotArmFromGamepad = (gp) => {
    // ...
    let rightX = gp.axes[2] || 0;
    let rightY = gp.axes[3] || 0;

    const speed = 0.05;

    window.targetBaseAngle += fx * speed;
    window.targetShoulderAngle += fy * speed;
    window.targetElbowAngle -= fy * speed * 0.8; // Inverse Elbow for natural movement
    // ...
}
```

---

## 2. PC Client Implementation (`pc_client_impl.drawio`)

### Node (11): Start
*   **File:** `PC_Client/web_server.py`
*   **Lines:** 1044 - 1052
*   **Description:** Python's main execution block. It initializes thread-safe queues for inter-process communication (IPC) between the Web Server and the Video Process.

```python
if __name__ == '__main__':
    # Initialize Multiprocessing Queues
    video_cmd_queue = Queue()
    video_frame_queue = Queue(maxsize=3) # Limit buffer to reduce latency
    video_log_queue = Queue()

    # Start Video Process (Optional - skip if camera unavailable)
    video_process_enabled = os.getenv('DISABLE_VIDEO') != '1'
```

### Node (13): Spawn VideoProcess
*   **File:** `PC_Client/web_server.py`
*   **Lines:** 1054 - 1060
*   **Description:** Creates a separate OS process for video handling. This heavily offloads the main Flask process, preventing video decoding or AI inference from blocking web request handling.

```python
    if video_process_enabled:
        try:
            print("[INIT] Starting video process...")
            initial_config = build_initial_video_config(state)
            p = Process(target=video_process_target, args=(video_cmd_queue, video_frame_queue, video_log_queue, initial_config))
            p.daemon = True
            p.start()
            print("[INIT] ✅ Video process started")
```

### Node (16): SocketIO Event 'control_cmd'
*   **File:** `PC_Client/web_server.py`
*   **Lines:** 803 - 821
*   **Description:** The event handler for incoming WebSocket control messages. It parses the JSON payload and calls the function to forward commands to the ESP hardware.

```python
@socketio.on('control_command')
def handle_control_command(data):
    """
    Handle motor control commands via WebSocket for lower latency.
    Expected JSON: {"left": int, "right": int}
    """
    try:
        left = data.get('left')
        right = data.get('right')

        if left is None or right is None:
            return

        # Send to ESP32
        send_control_command(int(left), int(right))
```

### Node (18): Loop: Read Frame
*   **File:** `PC_Client/video_process.py`
*   **Lines:** 133 - 137
*   **Description:** The core loop of the video subprocess. It continuously checks for commands from the main process and then attempts to read video frames from the MJPEG stream.

```python
    try:
        while True: 
            # 1. Process Commands (Non-blocking)
            try:
                while not cmd_queue.empty():
                    cmd, data = cmd_queue.get_nowait()

                    if cmd == CMD_EXIT:
                        if stream: stream.stop()
                        return
                    # ...
```

### Node (20): YOLO Inference
*   **File:** `PC_Client/ai_detector.py`
*   **Lines:** 297 - 315
*   **Description:** Performs the actual AI inference. It tracks objects using the YOLO model, leveraging GPU acceleration (CUDA) and Flash Attention if available.

```python
        # === 開始推論 ===
        start_time = time.time()
        
        try:
            # 1. YOLO 推論 (使用 track 模式保持 ID)
            results = self.model.track(
                frame, 
                device=self.device,
                persist=True,           # 保持追蹤 ID
                conf=self.conf_th,      # 信心度閾值
                imgsz=self.input_size,  # 輸入尺寸
                half=self.device=='cuda' # GPU 使用半精度加速
            )
            result = results[0]
```

### Node (22): Encode JPEG
*   **File:** `PC_Client/video_process.py`
*   **Lines:** 276 - 282
*   **Description:** Compresses the processed (and potentially annotated) frame back into JPEG format to be sent over the HTTP stream to the frontend.

```python
                # 5. Send to Web (Queue)
                try: 
                    ret, buffer = cv2.imencode('.jpg', final_frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
                    if ret: 
                        if frame_queue.full(): 
                            try: frame_queue.get_nowait()
                            except Empty: pass
                        frame_queue.put(buffer.tobytes()) 
                except:
                    pass
```

---

## 3. Firmware Implementation (`firmware_impl.drawio`)

### Node (23): Boot & Init WiFi
*   **File:** `Firmware/ESP32_S3/main/app_camera.c` & `wifi_sta.c`
*   **Lines:** 11 - 13 (app_camera.c)
*   **Description:** Initializes the hardware abstraction layer. This includes configuring the camera interface (SCCB/I2C, D0-D7 pins) and connecting to the specified WiFi network.

```c
esp_err_t app_camera_init(void)
{
    ESP_LOGI(TAG, "Initializing Camera (Refactored)...");

    camera_config_t config;
    config.ledc_channel = LEDC_CHANNEL_0;
    config.ledc_timer = LEDC_TIMER_0;
    config.pin_d0 = Y2_GPIO_NUM;
    // ... pin config ...
    config.pixel_format = PIXFORMAT_JPEG;
```

### Node (26): Loop (Stream Handler)
*   **File:** `Firmware/ESP32_S3/main/app_httpd.c`
*   **Lines:** 191 - 210
*   **Description:** The persistent loop handling a client's video stream connection. It captures frames from the camera hardware and prepares them for network transmission.

```c
    while(true){
        fb = esp_camera_fb_get();
        if (!fb) {
            ESP_LOGE(TAG, "Camera capture failed");
            res = ESP_FAIL;
        } else {
            if(fb->format != PIXFORMAT_JPEG){
                bool jpeg_converted = frame2jpg(fb, 80, &_jpg_buf, &_jpg_buf_len);
                esp_camera_fb_return(fb);
                fb = NULL;
                // ...
            } else {
                _jpg_buf_len = fb->len;
                _jpg_buf = fb->buf;
            }
        }
```

### Node (28): Send MJPEG Chunk
*   **File:** `Firmware/ESP32_S3/main/app_httpd.c`
*   **Lines:** 211 - 216
*   **Description:** Sends the formatted JPEG frame as a multipart HTTP chunk, enabling the "video" stream effect in the browser.

```c
        if(res == ESP_OK){
            size_t hlen = snprintf((char *)part_buf, 128, _STREAM_BOUNDARY _STREAM_PART, _jpg_buf_len);
            res = httpd_resp_send_chunk(req, (const char *)part_buf, hlen);
        }
        if(res == ESP_OK){
            res = httpd_resp_send_chunk(req, (const char *)_jpg_buf, _jpg_buf_len);
        }
```
