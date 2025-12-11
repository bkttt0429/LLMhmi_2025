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
        "PORT": "3334"
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
