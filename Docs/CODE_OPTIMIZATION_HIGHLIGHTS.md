# 技術優化代碼精選 (Code Optimization Highlights)

這是一份針對專案核心優化點的代碼集錦，直接提取自目前的開發版本，適合作為簡報中的技術展示。

---

## ⚡ 1. 消除 WiFi 延遲 (韌體層)
**檔案:** `wifi_sta.c`
```c
/* 
 * 核心優化：禁用 WiFi 省電模式
 * 預設模式會導致 CPU 進入微睡眠，造成指令響應延遲 (100ms+)
 */
esp_wifi_set_ps(WIFI_PS_NONE); 
```

---

## 🏎️ 2. 馬達軟啟動與保護 (韌體層)
**檔案:** `app_motor.c`
```c
/* 
 * 透過計時器任務實施 PWM 緩升/緩降
 * 防止啟動突波、減輕齒輪負擔、避免電壓不穩
 */
const int accel_table[] = { 2, 3, 5, 8, 12, 18, 25, 40 };

void motor_control_task(void *arg) {
    while(1) {
        if (current_pwm < target_pwm) 
            current_pwm += accel_table[step++]; // 平滑加速
        // ... 設定 PWM 輸出 ...
        vTaskDelay(pdMS_TO_TICKS(10)); // 10ms 解析度
    }
}
```

---

## 📡 3. 雙網卡路由綁定 (PC 端)
**檔案:** `web_server.py`
```python
"""
使用 SourceAddressAdapter 強制流量走特定介面 (Camera Net)
避免在雙網卡環境下影像數據流向公網導致的卡頓
"""
from requests.adapters import HTTPAdapter

def create_control_session(bind_ip):
    session = requests.Session()
    adapter = SourceAddressAdapter(bind_ip) # 綁定本地特定網卡 IP
    session.mount('http://', adapter)
    return session
```

---

## 🧠 4. AI 影像並行處理 (PC 端)
**檔案:** `video_process.py`, `web_server.py`
```python
"""
使用 Multiprocessing Queue 實現 AI 與控制的解耦
"""
# AI 程序端
def ai_worker(in_q, out_q):
    while True:
        frame = in_q.get() # 獲取新影像
        results = model(frame) # YOLO 推理 (耗時)
        out_q.put(results) # 異步返回結果

# 主通訊端 (Flask)
@socketio.on('control')
def handle_control(data):
    # 此處運作在獨立 Thread，與 AI Worker 併行，延遲極低
    send_motor_cmd(data)
```

---

## 📐 5. 運動學補償 (前端)
**檔案:** `static/js/robot_arm.js`
```javascript
/**
 * 機械耦合補償算法
 * 針對平行連桿 (Parallel Linkage) 的幾何特性進行伺服角度修正
 */
function updateArmAngles(q2_geom, q3_geom) {
    // 當關節 2 變動時，關節 3 會被動連動。此公式修復該現象。
    const q3_servo_corrected = q3_geom + (q2_geom - 90);
    
    servo2.rotate(q2_geom);
    servo3.rotate(q3_servo_corrected);
}
```

---
*這些代碼片段代表了整個專案在「穩定性」與「流暢度」上的工程智慧。*
