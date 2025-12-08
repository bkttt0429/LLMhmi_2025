"""
MJPEG Stream Reader - 專為 ESP32-CAM 優化

解決問題：
1. MJPEG 邊界分片 - TCP packet 可能切斷 JPEG 標記
2. 自動重連 - ESP32 經常斷線
3. 網路介面綁定 - 支援雙網卡架構
4. 低延遲 - 最小化 buffering

作者: Optimized for ESP32-CAM MJPEG streams
"""

import threading
import time
import requests
from queue import Queue, Empty
from typing import Optional, Callable


class MJPEGStreamReader:
    """
    專為 ESP32-CAM MJPEG 串流設計的讀取器
    
    核心特性：
    - JPEG 邊界檢測 (0xFFD8 start, 0xFFD9 end)
    - 背景線程持續讀取防止 socket buffer 溢出
    - Exponential backoff 重連機制
    - 支援 SourceAddressAdapter 綁定網路介面
    - 低延遲設計 (小 buffer, 快速 queue)
    """
    
    # JPEG markers
    JPEG_START = b'\xff\xd8'
    JPEG_END = b'\xff\xd9'
    
    def __init__(self, 
                 url: str,
                 source_ip: Optional[str] = None,
                 frame_queue_size: int = 2,
                 chunk_size: int = 16384,  # 增加到 16KB for better efficiency
                 reconnect_delay: float = 1.0,  # 減少初始延遲到 1s
                 max_reconnect_delay: float = 30.0,
                 connection_timeout: int = 30,  # 增加 connection timeout
                 log_callback: Optional[Callable[[str], None]] = None):
        """
        初始化 MJPEG 讀取器
        
        Args:
            url: MJPEG stream URL (例如 http://10.243.115.133:81/stream)
            source_ip: 綁定的本地 IP (用於雙網卡環境)
            frame_queue_size: frame queue 最大長度 (越小延遲越低)
            chunk_size: socket 讀取 chunk 大小 (增加可提升效率)
            reconnect_delay: 初始重連延遲 (秒)
            max_reconnect_delay: 最大重連延遲 (秒)
            connection_timeout: HTTP 連接超時 (秒)
            log_callback: 日誌回調函數
        """
        self.url = url
        self.source_ip = source_ip
        self.chunk_size = chunk_size
        self.reconnect_delay = reconnect_delay
        self.max_reconnect_delay = max_reconnect_delay
        self.connection_timeout = connection_timeout
        self.log = log_callback or print
        
        # Frame queue (producer: reader thread, consumer: main loop)
        self.frame_queue = Queue(maxsize=frame_queue_size)
        
        # Control
        self.running = False
        self.reader_thread = None
        self._buffer = bytearray()
        
    def start(self):
        """啟動背景讀取線程"""
        if self.running:
            self.log("⚠️ Reader already running")
            return
        
        self.running = True
        self.reader_thread = threading.Thread(target=self._reader_loop, daemon=True)
        self.reader_thread.start()
        self.log(f"✅ MJPEGStreamReader started: {self.url}")
        
    def stop(self):
        """停止讀取器"""
        if not self.running:
            return
            
        self.running = False
        if self.reader_thread:
            self.reader_thread.join(timeout=5)
        self.log("🛑 MJPEGStreamReader stopped")
        
    def read(self, timeout: float = 0.1) -> Optional[bytes]:
        """
        讀取下一幀 (JPEG bytes)
        
        Args:
            timeout: 超時時間 (秒)
        
        Returns:
            bytes: JPEG 影像資料，如果超時則返回 None
        """
        try:
            return self.frame_queue.get(timeout=timeout)
        except Empty:
            return None
    
    def _create_session(self) -> requests.Session:
        """創建 HTTP session，支援 source IP binding"""
        session = requests.Session()
        
        if self.source_ip:
            try:
                from network_utils import SourceAddressAdapter
                session.mount('http://', SourceAddressAdapter(self.source_ip))
                self.log(f"📌 Session bound to {self.source_ip}")
            except Exception as e:
                self.log(f"⚠️ Failed to bind to {self.source_ip}: {e}")
        
        return session
    
    def _reader_loop(self):
        """背景線程主循環 - 持續讀取 stream"""
        current_delay = self.reconnect_delay
        last_log_time = 0
        connection_count = 0
        
        while self.running:
            try:
                connection_count += 1
                session = self._create_session()
                
                # 建立持久連接
                self.log(f"🔌 Connecting to {self.url} (attempt #{connection_count})")
                with session.get(self.url, stream=True, timeout=self.connection_timeout) as resp:
                    if resp.status_code != 200:
                        self.log(f"❌ HTTP {resp.status_code} from {self.url}")
                        time.sleep(current_delay)
                        current_delay = min(current_delay * 2, self.max_reconnect_delay)
                        continue
                    
                    # 連接成功，重置 delay
                    current_delay = self.reconnect_delay
                    self.log(f"✅ Connected to {self.url}")
                    
                    # 讀取 stream
                    for chunk in resp.iter_content(chunk_size=self.chunk_size):
                        if not self.running:
                            break
                        
                        if chunk:
                            self._process_chunk(chunk)
                    
                    # Stream 正常結束
                    self.log("📡 Stream ended normally")
                    
            except requests.exceptions.Timeout as e:
                now = time.time()
                if now - last_log_time > 10:  # 節流日誌
                    self.log(f"⏱️ Timeout: {e}, retrying in {current_delay}s")
                    last_log_time = now
                
                time.sleep(current_delay)
                current_delay = min(current_delay * 2, self.max_reconnect_delay)
                
            except requests.exceptions.ConnectionError as e:
                now = time.time()
                if now - last_log_time > 10:
                    self.log(f"🔌 Connection error: {e}, retrying in {current_delay}s")
                    last_log_time = now
                
                time.sleep(current_delay)
                current_delay = min(current_delay * 2, self.max_reconnect_delay)
                
            except Exception as e:
                self.log(f"💥 Unexpected error: {e}")
                time.sleep(current_delay)
                current_delay = min(current_delay * 2, self.max_reconnect_delay)
    
    def _process_chunk(self, chunk: bytes):
        """
        處理接收到的數據塊，提取完整 JPEG 幀
        
        核心邏輯：
        1. 累積 bytes 到 buffer
        2. 搜索 JPEG 起始標記 (0xFFD8)
        3. 搜索 JPEG 結束標記 (0xFFD9)
        4. 提取完整 JPEG 並放入 queue
        5. 重複直到 buffer 中沒有完整幀
        
        這個方法解決了 ESP32-CAM 的 MJPEG 碎片化問題
        """
        self._buffer.extend(chunk)
        
        while True:
            # 查找 JPEG 起始標記
            start_idx = self._buffer.find(self.JPEG_START)
            if start_idx == -1:
                # 沒有起始標記，清空 buffer 防止無限增長
                if len(self._buffer) > 100000:  # 100KB 安全閾值
                    self.log("⚠️ Buffer overflow, clearing")
                    self._buffer.clear()
                break
            
            # 跳過起始標記之前的垃圾數據
            if start_idx > 0:
                self._buffer = self._buffer[start_idx:]
            
            # 查找結束標記 (從起始標記之後開始搜索)
            end_idx = self._buffer.find(self.JPEG_END, 2)  # Skip the start marker itself
            if end_idx == -1:
                # 還沒有完整的幀，等待更多數據
                # 但如果 buffer 太大，可能是損壞的幀
                if len(self._buffer) > 200000:  # 200KB
                    self.log("⚠️ Corrupted frame detected, discarding")
                    self._buffer.clear()
                break
            
            # 提取完整的 JPEG 幀
            frame_end = end_idx + 2  # Include 0xFFD9
            frame_bytes = bytes(self._buffer[:frame_end])
            
            # 從 buffer 移除這個幀
            self._buffer = self._buffer[frame_end:]
            
            # 放入隊列（如果隊列滿了，丟棄最舊的幀以保持低延遲）
            try:
                if self.frame_queue.full():
                    try:
                        self.frame_queue.get_nowait()  # 移除最舊的幀
                    except Empty:
                        pass
                
                self.frame_queue.put_nowait(frame_bytes)
            except:
                pass  # 隊列可能已關閉，忽略錯誤
