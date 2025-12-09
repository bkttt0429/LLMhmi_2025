# 測試與診斷工具

此資料夾包含各種測試腳本和診斷工具。

---

## 🧪 測試工具

### GPU / CUDA 測試
- **test_gpu.py** - 完整的 GPU 狀態檢測
  ```powershell
  python tests/test_gpu.py
  ```
  檢測內容：CUDA 可用性、GPU 資訊、記憶體使用、矩陣運算測試

- **diagnose_cuda.py** - CUDA 環境診斷
  ```powershell
  python tests/diagnose_cuda.py
  ```
  檢測內容：環境變數、DLL 路徑、PyTorch 配置

- **check_cuda.py** - 快速 CUDA 檢查
  ```powershell
  python tests/check_cuda.py
  ```

### GPU 監控
- **monitor_gpu.py** - 即時 GPU 使用率監控
  ```powershell
  python tests/monitor_gpu.py
  ```
  顯示：VRAM 使用、GPU 使用率、溫度（如支援）

---

## 🐛 除錯工具

- **reproduce_discovery.py** - 網路發現機制除錯
- **reproduce_stutter.py** - 影像串流卡頓除錯

---

## 📝 使用建議

### GPU 問題排查流程
1. 運行 `test_gpu.py` 確認 CUDA 是否可用
2. 如果失敗，運行 `diagnose_cuda.py` 查看詳細診斷
3. 使用 `monitor_gpu.py` 監控運行時的 GPU 使用

### 效能測試
```powershell
# 監控 GPU（終端 1）
python tests/monitor_gpu.py

# 啟動伺服器（終端 2）
python web_server.py
```

---

**最後更新**: 2025-12-09
