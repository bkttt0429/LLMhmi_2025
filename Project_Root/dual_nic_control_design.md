# 雙網卡控制架構整合設計方案（含自動偵測網卡 IP / MAC）

## 0. 目標

讓一台 PC 透過 **兩張網卡** 同時連到兩個不同網路，並在 Flask 伺服器中樞整合：

1. 與 **ESP32-S3-CAM（相機）** 連線
   * ESP32 以 Wi-Fi AP 模式運作，提供影像串流。
2. 與 **ESP12F（車子控制板）** 連線
   * ESP12F 連手機熱點或路由器，接收控制指令。

PC 端：

* 啟動時自動偵測所有網卡
* 自動判斷哪張是「相機網路（camera_net）」，哪張是「Internet / 車子網路（internet_net）」
* 記錄每張網卡的 IP 與 MAC，提供給日後設定與除錯使用
* Flask 內部開背景執行緒拉相機影像，並透過 HTTP / UDP 控制 ESP12F

---

## 1. 系統整體架構

### 1.1 網路拓樸

* ESP32-S3-CAM
  * 以 AP 模式開出 Wi-Fi：
    * SSID：`ESP32CAM`（可自訂）
    * AP IP：固定為 `192.168.4.1`
  * 對外服務：
    * 影像串流：`http://192.168.4.1:81/stream`

* ESP12F 車子控制模組
  * 以 STA 模式連上手機熱點或路由器：
    * 熱點子網範例：`10.243.115.0/24`
    * ESP12F IP 範例：`10.243.115.179`
  * 提供簡單 HTTP 或 UDP 介面接收指令，例如：
    * HTTP `/command` 接收 JSON 指令
    * 或 UDP 收文字指令

* PC（Flask + YOLO / 推論流程）
  * 有兩張實體或虛擬網卡：
    * **Wi-Fi 1**：連 `ESP32CAM` AP
      * IP 範例：`192.168.4.2`
      * 沒有 default gateway
    * **Wi-Fi 2 或 Ethernet**：連手機熱點 / 路由器
      * IP 範例：`10.243.115.243`
      * default gateway：例如 `10.243.115.157`
  * 角色：
    * Flask 伺服器
    * 背景執行緒負責從 ESP32 拉影像
    * 整合 YOLO 或其他 AI 模型做畫面分析（例如判斷路邊行人是否招手搭車）
    * 對 ESP12F 發送控制指令（前進、停止、轉彎等）

---

## 2. Windows 雙網卡網路設定

### 2.1 基本要求

* PC 需具備兩張網路介面（例如內建 Wi-Fi + USB Wi-Fi dongle，或 Wi-Fi + 有線網卡）。
* 配置：
  * 網卡 1：專門用來連 ESP32 AP，取得 `192.168.4.x` 的 IP。
  * 網卡 2：專門用來連手機熱點 / 路由器，有對外網路，負責 ESP12F 與 Internet。

### 2.2 預期 ipconfig 結果（例）

* Wi-Fi 1（連 ESP32AP）
  * IPv4：`192.168.4.2`
  * 子網遮罩：`255.255.255.0`
  * Gateway：空白

* Wi-Fi 2（連熱點/Internet）
  * IPv4：`10.243.115.243`
  * 子網遮罩：`255.255.255.0`
  * Gateway：`10.243.115.157`

### 2.3 靜態路由建議（可選）

* 額外在 Windows 路由表中設定一條路由：
  * 將 `192.168.4.0/24` 的流量固定走 Wi-Fi 1 對應的 gateway（通常是 `192.168.4.1`，但實務上會由系統自動處理，多數情況可不手動設定）
* 原則：
  * **只保留一個 default gateway**（熱點／路由器那張網卡）
  * 專用子網（例如 `192.168.4.x`）走 ESP32 那張網卡

---

## 3. 模組設計（ESP 端）

### 3.1 ESP32-S3-CAM（相機）

* Wi-Fi 模式：
  * 設定成 AP 模式，開啟 SSID，例如 `ESP32CAM`，密碼可自由設定。
  * 預設 AP IP 為 `192.168.4.1`（若有更改須同步調整 PC 偵測規則）。
* 功能：
  1. 提供 MJPEG 串流（路徑類似 `/stream`）
  2. 可選擇額外提供：
     * `GET /capture` 取得單張 JPEG
     * `GET /dist` 回傳超聲波測距數值（若有接超聲波感測器）
* 注意事項：
  * 串流品質與穩定度配置（解析度、frame size、frame buffer 等）在相機初始化中調整。
  * Mirror / flip 等圖像設定按實際車子架設位置設置。

### 3.2 ESP12F（車子）

* Wi-Fi 模式：
  * STA 模式連線手機熱點或路由器。
  * 建議：
    * 熱點 SSID / 密碼固定。
    * 儘量固定或可預測的 IP（例如由路由器 DHCP Reservation 配置）。
* 功能：
  * 接收控制指令，例如：
    * HTTP `/command`：JSON 格式，內含 `cmd` 欄位，如 `{"cmd": "forward"}`。
    * 或 UDP：文字協定，例如 `FORWARD`、`STOP`。
* 回應：
  * 可以簡單回傳目前狀態（成功、失敗、錯誤訊息等），便於 Flask 顯示結果。

---

## 4. PC 端 Flask + 自動網卡偵測設計

### 4.1 啟動流程：自動偵測網卡 IP / MAC

1. Flask 啟動時，先執行「網卡偵測」邏輯：
   * 透過系統 API 或第三方套件（例如 psutil）列出所有網卡資訊：
     * 介面名稱（iface name，如 `Wi-Fi`, `Wi-Fi 2`）
     * IPv4 位址
     * MAC 位址
     * 啟用狀態（是否 up）
2. 過濾掉：
   * 未啟用的網卡
   * 沒有 IPv4 的網卡
   * loopback（如 `127.0.0.1`）
3. 根據 IP 規則自動分類：
   * 若 IP 前綴為 `192.168.4.` → 判定為 **camera_net**（連 ESP32 的網卡）
   * 第一個非 loopback 且非 `192.168.4.*` 的網卡 → 判定為 **internet_net**（連熱點／路由器 / ESP12F 的網卡）
4. 建立一個 NetConfig 結構／物件，包含：
   * `camera_net`：
     * `iface`：網卡名稱
     * `ip`：IPv4 位址
     * `mac`：MAC 位址
   * `internet_net`：
     * 同上
   * `all_ifaces`：字典／列表，記錄所有偵測到的網卡名稱、IP、MAC
5. 啟動時在 log 中印出：
   * 所有網卡列表：介面名稱 / IP / MAC
   * 判定出來的：
     * Camera Net：哪一張網卡（名稱 / IP / MAC）
     * Internet Net：哪一張網卡（名稱 / IP / MAC）
6. 將這份 NetConfig 存在 Flask 全域狀態中，並提供一個 HTTP API（如 `/netinfo`）讓前端或除錯工具可以查詢。

### 4.2 影像擷取執行緒（Camera Thread）

* 在 Flask 啟動時，開啟一個背景執行緒負責：
  1. 依照 ESP32 AP IP（固定為 `192.168.4.1` 或設定檔指定）組成串流 URL。
  2. 與 `http://ESP32_IP:81/stream` 建立連線。
  3. 持續讀取串流影像 frame：
     * 若成功，更新全域變數（例如 `latest_frame`）。
     * 若發生錯誤（斷線、timeout），紀錄 log，稍作等待後重試。
  4. 將影像留在記憶體中，讓 Flask 的 `/camera.jpg` 或其他 API 可以即時抓到最新影像。
* Flask 額外提供一個 HTTP 路徑，例如 `/camera.jpg`：
  * 將最新影像轉成 JPEG 格式回傳。
  * 若影像尚未準備好，回傳錯誤狀態（例如 503）。

### 4.3 車子控制 API 設計

* Flask 提供一個 HTTP 路徑（例如 `/control`），用來接收前端或其他系統送來的車子控制指令：
  * 使用 POST，body 採 JSON 格式：
    * 例如：`{"cmd": "forward"}`、`{"cmd": "stop"}`、`{"cmd": "left"}` 等。
* Flask 在收到指令後：
  1. 從設定或自動發現機制取得 ESP12F IP（初期可先寫死，未來可改成 UDP 廣播自動發現）。
  2. 透過 HTTP 或 UDP 將指令轉送給 ESP12F。
  3. 收到 ESP12F 回覆後：
     * 將結果包裝成 JSON 回傳給呼叫方。
     * 若發生錯誤（連線錯誤、timeout），返回錯誤訊息。

### 4.4 網卡資訊查詢 API（除錯用）

* 提供一個簡單的 GET API，例如 `/netinfo`：
  * 回傳 JSON：
    * 所有網卡名稱 / IP / MAC
    * 目前判定為 Camera Net 的介面資訊
    * 目前判定為 Internet Net 的介面資訊
  * 方便在開發與除錯時確認實際環境配置是否符合預期。

---

## 5. 測試與驗證流程

1. **網路連線確認**
   * 確認 PC：
     * 能成功連上 ESP32 AP（取得 192.168.4.x）
     * 能成功連上手機熱點或路由器（取得 10.x.x.x 或 192.168.x.x）
2. **啟動 Flask**
   * 執行 Flask 伺服器。
   * 啟動 log 中應顯示：
     * 掃描到的網卡列表
     * Camera Net 與 Internet Net 判定結果
3. **查看網卡資訊 API**
   * 瀏覽器請求 `/netinfo`：
     * 檢查 JSON 中的 IP / MAC 是否符合實際 `ipconfig` 結果。
4. **相機串流測試**
   * 在瀏覽器中請求 Flask 提供的影像路徑（例如 `/camera.jpg` 或其他視覺化頁面）。
   * 應能看到 ESP32 的即時畫面。
   * 若停止 ESP32 或中斷 Wi-Fi，應在 log 中看到重試或錯誤訊息。
5. **車子控制測試**
   * 使用 curl 或 Postman 對 `/control` 送出 JSON 指令（例如 forward）。
   * ESP12F 應接收到對應指令並執行動作。
   * Flask 回應中應顯示 ESP12F 的回傳結果。

---

## 6. 後續可擴充項目

1. **ESP12F IP 自動發現**
   * 目前先假設 ESP12F IP 寫死或由路由器固定指派。
   * 之後可在 ESP12F 實作 UDP 廣播（例如週期性發送「我是 ESP12F，在某某 IP」）。
   * Flask 端開啟 UDP Listener Thread，自動記錄最新的 ESP12F IP，完全免手動輸入。
2. **ESP32 AP 子網彈性**
   * 若未來想修改 AP IP（例如 172.20.10.x），只需：
     * 修改 ESP32 AP 的 IP 設定。
     * 修改 PC 端「判定 Camera Net 的 IP 前綴規則」。
3. **YOLO / AI 整合**
   * 在 Camera Thread 拉到的影像上做即時推論：
     * 判斷畫面中是否有路邊行人招手。
     * 依條件產生控制策略（例如：減速、靠邊、停車等），透過 `/control` 自動下指令給 ESP12F。
4. **錯誤處理與重連機制強化**
   * 相機串流斷線時，自動重連。
   * ESP12F 無回應時，自動重試或標記狀態。
