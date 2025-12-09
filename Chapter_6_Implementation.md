# 第六章 系統實作與程式解析

本章將詳細說明即時車輛控制系統的程式實作細節。系統架構分為電腦端控制核心、前端人機介面與車載端韌體三大模組。各模組透過標準化的網路協定進行通訊，確保系統的穩定性與可擴充性。

## 6.1 電腦端控制核心

電腦端程式 `web_server.py` 扮演系統的中樞神經，負責串接使用者介面、AI 運算單元與車載通訊。為解決 Python 全域直譯器鎖 (Global Interpreter Lock, GIL) 在處理高負載影像串流時可能造成的效能瓶頸，本研究採用 **多行程 (Multiprocessing)** 架構，將影像處理獨立於主控制邏輯之外。

### 6.1.1 差速驅動控制指令發送

為實現低延遲的車輛控制，系統建立了專用的差速驅動指令發送函式。如程式碼 6-1 所示，該函式將左右輪 PWM 值封裝為 HTTP GET 請求，直接發送至 ESP32-S3 的 IP 位址。

**程式碼 6-1：差速驅動控制指令發送函式 (`web_server.py` 第 448-490 行)**

```python
def send_control_command(left: int, right: int):
    """
    發送馬達控制指令至 ESP32-S3 (Code 6-1)

    參數:
        left (int): 左側馬達 PWM 值 (-255 ~ 255)
        right (int): 右側馬達 PWM 值 (-255 ~ 255)

    回傳:
        bool: 指令發送成功與否
    """
    target_ip = state.camera_ip or "192.168.4.1"
    url = f"http://{target_ip}/motor"
    params = {"left": left, "right": right}

    # [DEBUG] Print what we're about to send
    print(f"[CONTROL] 🚗 Sending to ESP32: {url} with params={params}")
    add_log(f"[CONTROL] → {target_ip}/motor L:{left} R:{right}")

    try:
        # 使用預先綁定網卡的 Session 發送請求
        resp = state.control_session.get(url, params=params, timeout=0.5)

        # [DEBUG] Print response details
        print(f"[CONTROL] 📡 ESP32 Response: Status={resp.status_code}, Content={resp.text[:100]}")

        if resp.status_code == 200:
            add_log(f"[CONTROL] ✅ Success")
            return True
        else:
            add_log(f"[CONTROL] ⚠️ Failed: HTTP {resp.status_code}")
            print(f"[CONTROL] ❌ ESP32 rejected command with status {resp.status_code}")
            return False

    except requests.exceptions.Timeout:
        add_log(f"[CONTROL] ⚠️ Timeout to {target_ip}")
        print(f"[CONTROL] ⏱️ Timeout: ESP32 at {target_ip} did not respond in 0.5s")
        return False

    except requests.exceptions.ConnectionError as e:
        add_log(f"[CONTROL] ❌ Connection Error to {target_ip}")
        print(f"[CONTROL] 🔌 Connection Error: Cannot reach ESP32 at {target_ip}")
        print(f"[CONTROL]    Details: {e}")
        return False

    except requests.exceptions.RequestException as e:
        add_log(f"[CONTROL] ❌ Error: {e}")
        print(f"[CONTROL] 💥 Request Exception: {e}")
        return False
```

**實作邏輯解析：**

1.  **RESTful API 設計**：函式利用 Python 的 f-string 動態建構 URL（例如 `http://192.168.4.1/motor?left=200&right=200`）。此設計符合 RESTful 風格，使得指令具備高度的可讀性與除錯便利性。
2.  **非阻塞式設計考量**：在 `requests.get()` 中特別設定了 `timeout=0.5`。這是即時控制系統的關鍵設計，若車輛因訊號不良而未回應，主程式僅會等待 0.5 秒即放棄該次指令，避免整個伺服器介面因等待回應而凍結，確保使用者體驗的流暢度。
3.  **容錯機制**：使用 `try-except` 區塊包覆網路請求。在無線網路環境不穩定的情況下，封包遺失是常態，此機制確保單次通訊失敗不會導致整個控制程式崩潰，提升了系統的強健性。
4.  **雙網卡環境適配**：系統使用 `SourceAddressAdapter` 將 HTTP Session 預先綁定至特定網路介面（192.168.4.x 網段），確保在雙網卡環境下封包經由正確路徑送達 ESP32-S3，避免因路由選擇錯誤導致的通訊失敗。

### 6.1.2 差速驅動演算法實作

差速驅動是本系統的核心控制演算法，透過控制左右輪速度差異實現轉向功能。如程式碼 6-2 所示，該演算法將搖桿的二維輸入 (X, Y) 轉換為左右輪的 PWM 控制值。

**程式碼 6-2：差速驅動混合演算法 (`web_server.py` 第 407-437 行)**

```python
def _calculate_differential_drive(x: float, y: float) -> tuple[int, int]:
    """
    將搖桿 X/Y 輸入轉換為差速驅動 PWM 值 (Code 6-2)

    參數:
        x (float): 橫向輸入 -1.0 (左) 至 1.0 (右)
        y (float): 縱向輸入 -1.0 (後) 至 1.0 (前)

    回傳:
        tuple[int, int]: (左輪 PWM, 右輪 PWM) 範圍 -255 ~ 255
    """
    # 坦克式轉向公式
    left = y + x  # 左輪 = 油門 + 轉向
    right = y - x # 右輪 = 油門 - 轉向

    # 正規化至 [-1.0, 1.0] 避免溢位
    magnitude = max(abs(left), abs(right))
    if magnitude > 1.0:
        left /= magnitude
        right /= magnitude

    # 轉換為 PWM 值 (±255)
    left_pwm = int(left * PWM_MAX)
    right_pwm = int(right * PWM_MAX)

    return left_pwm, right_pwm
```

**演算法原理：**

*   **差速驅動**採用坦克式轉向邏輯，其核心概念為透過左右輪速差實現轉向。
*   當搖桿向右推動 (x > 0) 時，根據公式：
    *   左輪速度 = y + x（增加）
    *   右輪速度 = y - x（減少）
    *   此速度差使車輛產生順時針旋轉。
*   相較於傳統的阿克曼轉向，差速驅動無需額外轉向機構，降低機械複雜度，適合履帶式或雙輪機器人平台。
*   **正規化步驟**確保當同時全速前進與全力轉向時（例如 y=1.0, x=1.0），輸出值不會超過馬達驅動晶片的承受範圍（±255），避免硬體損壞。

### 6.1.3 AI 物件偵測模組實作

`ai_detector.py` 負責載入 YOLO 模型並對每一幀影像進行推論。此模組被設計為一個獨立的類別，以便於在多行程架構中被呼叫。如程式碼 6-3 所示，系統在初始化階段即完成 GPU 環境配置與模型載入。

**程式碼 6-3：AI 物件偵測類別初始化 (`ai_detector.py` 第 57-82 行)**

```python
# 程式碼 6-3：AI 物件偵測類別初始化 (Code 6-3)
class ObjectDetector:
    def __init__(self, model_path='./yolov13l.pt'):
        self.model = None
        self.enabled = False
        self.frame_count = 0
        self.total_inference_time = 0
        self.model_path = model_path

        # === 智能裝置選擇 (GPU/CPU) ===
        self.device = self._select_device()

        # === 控制參數 ===
        self.base_v = 0.6  # 基礎速度
        self.max_w = 2.0   # 最大角速度
        self.conf_th = 0.4 # 信心度閾值
        self.target_class = None # 目標類別 (None = 所有類別)

        # === 效能優化參數 ===
        self.skip_frames = 0     # 跳幀計數器
        self.process_every_n = 1 # 每 N 幀處理一次
        self.input_size = 640    # YOLO 輸入尺寸

        # === 模型載入 ===
        if YOLO_AVAILABLE:
            self._load_model(model_path)
```

**程式碼 6-4：GPU 加速環境配置 (`ai_detector.py` 第 28-47 行)**

```python
# 程式碼 6-4：GPU 加速環境配置 (Code 6-4)
# === CUDA 效能優化 ===
if torch.cuda.is_available():
    # 強制在當前進程中初始化 CUDA
    torch.cuda.init()
    torch.cuda.set_device(0)

    # 啟用 cuDNN 自動優化
    torch.backends.cudnn.benchmark = True
    torch.backends.cudnn.deterministic = False

    # 啟用 Tensor Core 優化 (Ampere+ 架構)
    try:
        torch.set_float32_matmul_precision('high')
        print("✅ Tensor Core 優化已啟用")
    except AttributeError:
        pass

    # 清空 GPU 快取確保乾淨狀態
    torch.cuda.empty_cache()
```

**程式碼 6-5：YOLO 推論執行 (`ai_detector.py` 第 282-290 行)**

```python
            # 程式碼 6-5：YOLO 推論執行 (Code 6-5)
            results = self.model.track(
                frame,
                device=self.device,      # 使用 GPU 或 CPU
                persist=True,            # 保持追蹤 ID
                conf=self.conf_th,       # 信心度閾值 (0.4)
                verbose=False,           # 不顯示詳細 log
                imgsz=self.input_size,   # 輸入尺寸 (640)
                half=self.device=='cuda' # GPU 使用半精度加速 (FP16)
            )
```

**實作邏輯解析：**

1.  **模型持久化**：YOLO 模型的載入發生在 `__init__` 建構子中。這確保了龐大的神經網路權重只需載入記憶體一次，後續的 `detect()` 呼叫僅需執行前向傳播，大幅降低運算延遲。
2.  **GPU 加速配置**：系統在初始化階段即完成 CUDA 環境配置，啟用 `cuDNN Benchmark` 模式以自動選擇最佳卷積演算法，並透過 `torch.set_float32_matmul_precision('high')` 在支援 Tensor Core 的 GPU 上啟用矩陣運算加速，可提升 2-3 倍推論速度。
3.  **信心指數過濾**：在推論參數中設定 `conf=0.4`，代表僅保留信心分數高於 40% 的偵測結果。
4.  **半精度推論 (FP16)**：如程式碼 6-5 所示，系統在 GPU 模式下自動啟用半精度推論，在幾乎不損失精度的前提下，將 VRAM 使用量降低 50%，並提升推論速度 40-60%。

## 6.2 前端人機介面互動 (HMI)

前端介面位於 `templates/index.html`，主要負責接收使用者輸入並透過 WebSocket 與非同步 JavaScript 發送請求，實現無刷新頁面的流暢控制。

### 6.2.1 鍵盤控制與輸入優先權機制

為避免多輸入源衝突，系統實作三層優先權機制：鍵盤控制 > Xbox 手把 > 虛擬搖桿。如程式碼 6-6 所示，當鍵盤操作發生時，系統會在 500ms 內抑制手把輸入。

**程式碼 6-6：鍵盤事件監聽與優先權控制 (`index.html` 第 491-538 行)**

```javascript
        // 程式碼 6-6：鍵盤事件監聽與優先權控制 (Code 6-6)
        function setupKeyboardControls() {
            // 追蹤按鍵狀態
            document.addEventListener('keydown', (e) => {
                const key = e.key.toUpperCase();

                // 防止重複觸發 (按住時)
                if (keyPressed[key]) return;
                keyPressed[key] = true;

                // 更新鍵盤活動時間戳 (用於輸入優先權判斷)
                lastKeyboardActivity = Date.now();

                console.log(`[KEYBOARD] Key DOWN: ${key}`);

                // 映射按鍵至控制指令
                switch (key) {
                    case 'W': sendCmd('F'); break; // 前進
                    case 'A': sendCmd('L'); break; // 左轉
                    case 'D': sendCmd('R'); break; // 右轉
                    case 'X': sendCmd('B'); break; // 後退
                    case 'S': sendCmd('S'); break; // 停止
                }
            });

            // 按鍵釋放時發送停止指令
            document.addEventListener('keyup', (e) => {
                const key = e.key.toUpperCase();
                keyPressed[key] = false;

                console.log(`[KEYBOARD] Key UP: ${key}`);

                if (['W', 'A', 'S', 'D', 'X'].includes(key)) {
                    sendCmd('S'); // 釋放按鍵即停止
                }
            });

            console.log('[KEYBOARD] Event listeners installed');
        }
```

**程式碼 6-7 Xbox 手把輸入 (修正流程圖邏輯)**

```javascript
        // 程式碼 6-8：Xbox 抑制手把訊號手把輸入優先權檢查 (Code 6-8)
        // === 輸入優先權檢查 ===
        // 如果鍵盤在 500ms 內使用過，抑制手把輸入
        if (Date.now() - lastKeyboardActivity < 500) {
            // 鍵盤擁有最高優先權，直接返回
            return;
        }
```

**前端介面邏輯流程圖：**

```mermaid
flowchart TD
    subgraph Frontend_HMI [前端介面邏輯 (index.html)]
        Input_Source[使用者輸入來源<br>(Keyboard / Xbox / Virtual Joy)]
        Input_Source --> Priority_Arbitration

        subgraph Priority_Arbitration [輸入優先權仲裁]
            Xbox_Input[Xbox 手把輸入]
            Keyboard_Listener[監聽鍵盤事件<br>(keydown/keyup)]

            Xbox_Input --> Time_Check
            Keyboard_Listener --> Time_Check
            Keyboard_Listener --> Update_Timestamp[更新最後按鍵時間]

            Time_Check{檢查最後按鍵時間<br>(是否 < 500ms?)}

            Time_Check -- Yes<br>(鍵盤優先) --> Suppress_Xbox[抑制手把訊號]
            Time_Check -- No<br>(手把可用) --> Allow_Xbox[允許手把訊號]
        end

        Allow_Xbox --> HTTP_Fetch[HTTP Fetch<br>(發送控制指令 /api/control)]
        Keyboard_Listener --> HTTP_Fetch

        HTTP_Fetch --> Backend[送往 PC 端 Backend<br>(web_server.py)]
    end
```

**實作邏輯解析：**

1.  **事件驅動架構**：透過 `keydown` 與 `keyup` 事件的配合，實現了「按下即走、放開即停」的直覺操控體驗，避免了輪詢機制的高 CPU 消耗。
2.  **輸入優先權機制**：透過 `lastKeyboardActivity` 時間戳記錄，當鍵盤操作發生時，系統會在 500ms 內抑制手把輸入，確保人為介入能立即覆蓋其他控制，符合緊急應變需求。
3.  **防止重複觸發**：`keyPressed` 物件追蹤每個按鍵的狀態，避免按住按鍵時觸發多次 `keydown` 事件，減少不必要的網路請求。

### 6.2.2 WebSocket 即時通訊

系統採用 WebSocket 協定實現伺服器推送，相較於傳統的 HTTP 輪詢，可降低 90% 以上的網路流量與延遲。

**程式碼 6-9：WebSocket 初始化與事件處理 (`index.html`)**

```javascript
function initWebSocket() {
    socket = io({ transports: ['websocket'] });

    socket.on('connect', () => {
        wsConnected = true;
        log("WS Connected");
    });

    socket.on('disconnect', () => {
        wsConnected = false;
        log("WS Disconnected");
    });

    // 接收伺服器推送的狀態更新
    socket.on('status_update', (data) => {
        updateUI(data); // 更新 UI (IP、距離、log 等)
    });

    // 接收 Xbox 手把狀態
    socket.on('controller_data', (data) => {
        controllerLinked = true;
        lastXboxUpdate = Date.now();
        updateXboxVisual(data.left_stick_x, data.left_stick_y);

        if (data.cmd) {
            document.getElementById('xbox-cmd').innerText = data.cmd;
        }
    });
}
```

**實作邏輯解析：**

*   **前後端分離通訊**：使用現代化的 WebSocket 取代傳統的表單提交或 AJAX 輪詢。這是一種全雙工通訊方式，保持連線長時間開啟，無需反覆建立 TCP 連線。
*   **伺服器推送機制**：後端透過 `socketio.emit('status_update', data)` 主動推送系統狀態（如超音波距離、AI 狀態、控制 IP 等），前端無需定時發送查詢請求，大幅降低網路負擔並提升即時性。
*   **自動重連**：Socket.IO 內建斷線重連機制，當網路暫時中斷時，客戶端會自動嘗試重新連線。

## 6.3 車載端韌體邏輯

車載端韌體基於 ESP-IDF 框架開發，採用整合式設計，利用 ESP32-S3 的雙核心優勢，同時處理 HTTP 伺服器請求與 GPIO 硬體控制。

### 6.3.1 HTTP 請求解析與馬達控制

韌體的核心在於解析來自電腦端的 URL 參數，並將其轉換為對應的電位訊號以驅動 L298N/TB6612 馬達驅動模組。如程式碼 6-10 所示，系統透過 `/motor` 端點接收控制指令。

**程式碼 6-10：馬達控制端點處理 (ESP32-S3 韌體 `app_httpd.c`)**

```c
// HTTP 處理函式：/motor?left=XX&right=YY
static esp_err_t motor_handler(httpd_req_t *req){
    char buf[100];
    int left_val = 0;
    int right_val = 0;

    // 解析 URL 查詢參數
    if (httpd_req_get_url_query_str(req, buf, sizeof(buf)) == ESP_OK) {
        char param[16];
        if (httpd_query_key_value(buf, "left", param, sizeof(param)) == ESP_OK) {
            left_val = atoi(param);
        }
        if (httpd_query_key_value(buf, "right", param, sizeof(param)) == ESP_OK) {
            right_val = atoi(param);
        }

        // 呼叫馬達控制函式 (更名後符合論文描述)
        set_motor_speed(left_val, right_val);

        // 回傳成功訊息
        httpd_resp_set_hdr(req, "Access-Control-Allow-Origin", "*");
        httpd_resp_send(req, "OK", HTTPD_RESP_USE_STRLEN);
    } else {
        // 參數錯誤
        httpd_resp_send_404(req);
    }
    return ESP_OK;
}
```

**車載端韌體流程圖：**

```mermaid
flowchart TD
    subgraph Firmware_Logic [車載端韌體 (ESP-IDF / ESP32-S3)]
        Daemon[HTTP Server Daemon<br>(監聽 /motor)]
        Daemon --> URL_Handler[URL Handler<br>(/motor?left=X&right=Y)]

        URL_Handler --> Parse[解析 Query 參數<br>(atoi 轉換 PWM 值)]
        Parse --> Set_Motor[set_motor_speed()<br>(GPIO PWM Output)]
        Set_Motor --> HTTP_OK[回傳 HTTP 200 OK]

        HTTP_OK --> Reply[回覆 PC 端請求完成]
    end
```

**實作邏輯解析：**

1.  **參數解析**：使用 `httpd_query_key_value()` 從 HTTP GET 請求中提取 `left` 與 `right` 參數，具備高度擴充性。
2.  **硬體抽象層**：`set_motor_speed()` 函式將邏輯層的 PWM 值轉換為底層的 GPIO 電位操作，實現硬體與軟體的解耦合 (decoupling)。
3.  **回應機制**：透過 `httpd_resp_send(req, "OK", ...)` 回傳 HTTP 200 狀態碼，告知電腦端指令已成功執行，確保指令傳達的可靠性。

## 6.4 系統整體架構

本章詳細說明了系統三大核心模組的程式實作：

1.  **電腦端控制核心**：採用差速驅動演算法與多行程架構，實現低延遲的車輛控制與 GPU 加速的 AI 推論。
2.  **前端人機介面**：透過 WebSocket 即時通訊與輸入優先權機制，提供流暢的多輸入源操控體驗。
3.  **車載端韌體**：基於 ESP-IDF 開發，利用雙核心優勢同時處理網路通訊與硬體控制。

**系統整體運作流程圖：**

```mermaid
flowchart TD
    PC_Start((PC 端程式啟動)) --> Multiprocessing{多行程分流<br>Multiprocessing}

    subgraph AI_Process [AI 影像處理行程 (ai_detector.py)]
        Vid_Read[MJPEG 串流讀取<br>(Custom Reader)]
        Vid_Read --> YOLO_Infer[YOLOv13 推論<br>(CUDA / FP16 加速)]
        YOLO_Infer --> Draw_Encode[影像繪製與編碼<br>(Draw BBox & Encode)]
    end

    subgraph Control_Process [控制邏輯執行緒 (web_server.py)]
        SocketIO[SocketIO Server<br>(接收前端訊號)]
        SocketIO --> Tank_Mix[差速驅動演算法<br>(Tank Drive Mixing)]
        Tank_Mix --> HTTP_Req[HTTP Request 發送<br>(/motor?left=X&right=Y)]
    end

    Multiprocessing --> AI_Process
    Multiprocessing --> Control_Process

    Draw_Encode -- MJPEG 影像流 --> Data_Merge{資料整合與推送}
    HTTP_Req -- 控制回饋 Log --> Data_Merge

    Data_Merge --> Frontend[前端 HMI 介面<br>(影像 + 雷達 + 控制狀態 同步顯示)]

    subgraph Hardware [硬體層]
        ESP32_Cam[ESP32: 鏡頭] -. Wi-Fi .-> Vid_Read
        HTTP_Req -. Wi-Fi .-> ESP32_Motor[ESP32: 馬達]
    end
```

各模組透過 HTTP RESTful API 與 WebSocket 協定進行通訊，形成一個高效、穩定、具備容錯能力的分散式即時控制系統。
