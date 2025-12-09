# 工具腳本

此資料夾包含便利的啟動腳本與工具。

---

## 🚀 啟動腳本

### run_server.bat
**用途**: 自動配置環境並啟動 Flask 伺服器

**功能**:
- 自動啟動 `yolov13` Conda 環境
- 設定 `KMP_DUPLICATE_LIB_OK=TRUE`（解決 OpenMP 衝突）
- 設定 CUDA 記憶體優化
- 啟動 `web_server.py`

**使用方法**:
```powershell
# 方法 1: 雙擊執行
.\scripts\run_server.bat

# 方法 2: 從專案根目錄執行
cd PC_Client
.\scripts\run_server.bat
```

---

## 🔧 修復工具

### fix_cuda.bat
**用途**: 自動修復 CUDA/PyTorch 環境問題

**功能**:
- 檢查當前 PyTorch 狀態
- 重新安裝 PyTorch (CUDA 11.8 版本)
- 驗證安裝結果

**使用方法**:
```powershell
.\scripts\fix_cuda.bat
```

**適用情況**:
- CUDA 不可用
- PyTorch 與 CUDA 版本不匹配
- GPU 無法正常使用

---

## 💡 使用建議

### 日常開發
建議使用 `run_server.bat` 啟動伺服器，它會自動處理環境設定。

### 環境問題排查
1. 如果遇到 CUDA 相關錯誤，先運行 `tests/test_gpu.py`
2. 如果確認是環境問題，運行 `fix_cuda.bat`
3. 重新測試

---

**最後更新**: 2025-12-09
