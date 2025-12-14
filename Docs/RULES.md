# Project Rules & Configuration

## 1. Environment Setup
*   **Conda Environment**: `yolov13`
*   **Python Version**: 3.8+ (Recommended)
*   **Root Directory**: `d:\hmidata\project\PC_Client`

### Startup Command
```powershell
$env:KMP_DUPLICATE_LIB_OK="TRUE"; python web_server.py
```
*Note: The environment variable `KMP_DUPLICATE_LIB_OK="TRUE"` is required to prevent OpenMP runtime conflicts with YOLO/PyTorch.*

## 2. Server Access
*   **Local Web Interface**: `http://127.0.0.1:5000/`
*   **Video Stream**: `http://127.0.0.1:81/stream` (from ESP32)
*   **Control API**: `http://192.168.0.184/` (ESP12F Car)

## 3. MCP Server Configuration (Reference)
Copy the following configuration to your MCP settings file (e.g., `mcp_config.json`):

```json
{
  "mcpServers": {
    "drawio": {
      "command": "npx",
      "args": [
        "-y",
        "drawio-mcp-server"
      ],
      "env": {
        "PORT": "3333"
      }
    },
    "sequential-thinking": {
      "command": "npx",
      "args": [
        "-y",
        "@modelcontextprotocol/server-sequential-thinking"
      ],
      "env": {}
    },
    "knowledge-graph": {
      "command": "node",
      "args": [
        "D:/MCP_Server/mcp-knowledge-graph/dist/index.js"
      ],
      "env": {}
    },
    "mcp-three": {
      "command": "node",
      "args": [
        "D:/MCP_Server/mcp-three/dist/stdio.js"
      ],
      "env": {}
    },
    "filesystem": {
      "command": "npx",
      "args": [
        "-y",
        "@modelcontextprotocol/server-filesystem",
        "D:/hmidata/project/PC_Client/models/"
      ]
    }
  }
}
```

# ESP32-S3 Firmware Build Guide (Added 2025-12-12)

## 1. Environment Setup (PowerShell)
To compile the firmware, you must first activate the ESP-IDF environment.
Run the following command in PowerShell:

```powershell
. C:\Users\ken\esp\v5.5.1\esp-idf\export.ps1
```

*Note: The leading dot `.` is important! It ensures the environment variables are loaded into the current session.*

## 2. Compilation Steps
Navigate to the firmware directory and build:

```powershell
# 1. Enter Firmware Directory
cd d:\hmidata\project\Firmware\ESP32_S3

# 2. Set Target (Only needed once per project)
idf.py set-target esp32s3

# 3. Remove environment variable lock if needed
$env:IDF_TARGET=$null

# 4. Build Firmware
idf.py build
```

## 3. Flash & Monitor
```powershell
# Flash firmware and monitor output (Replace COMx with your device port)
idf.py -p COMx flash monitor
```

## 4. Critical Optimizations (N16R8)
This firmware has been optimized for the ESP32-S3 N16R8 module.
- **WiFi Power Save:** Disabled via `esp_wifi_set_ps(WIFI_PS_NONE)` in `wifi_sta.c` to fix latency.
- **Camera Buffer:** Increased to 5 frames in PSRAM (`app_camera.c`) for smoother video.

## 5. Hardware Safety Settings (Added 2025-12-13)
- **Brownout Detection:** Disabled (`CONFIG_ESP_BROWNOUT_DET=n`) to prevent restarts on low voltage.
  - **WARNING**: Disabling this increases the risk of flash corruption if the voltage drops significantly while the device is writing to flash. Ensuring a stable power supply is critical.

# ESP8266 MicroPython Flashing Guide (Added 2025-12-15)

## Reprogramming User Code
If you are reverting from C++ to MicroPython, or if `ampy` hangs, execute this full sequence:

```powershell
# 1. Enter Directory
cd d:\hmidata\project\Firmware\ESP8266\MicroPython

# 2. Erase Flash (Removes C++ Core)
python -m esptool --port COM12 erase_flash

# 3. Flash Python Interpreter
python -m esptool --port COM12 --baud 460800 write_flash --flash_size=detect 0 ESP8266_GENERIC-20251209-v1.27.0.bin

# 4. Verify System
ampy --port COM12 ls
# Output should be: /boot.py

# 5. Upload Firmware v2.0
ampy --port COM12 put config.json
ampy --port COM12 put kinematics.py
ampy --port COM12 put robot.py
ampy --port COM12 put main.py
ampy --port COM12 reset
```