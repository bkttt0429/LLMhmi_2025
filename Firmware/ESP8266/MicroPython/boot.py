# boot.py (優化版)
import network
import time

SSID = "Bk"
PASSWORD = "........."
MAX_RETRIES = 20  # Increase retries for slow hotspots
TIMEOUT_MS = 1000 # 1s per retry

def connect_wifi():
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    
    mac = wlan.config('mac')
    print('MAC:', ':'.join(['%02X' % b for b in mac]))
    
    if wlan.isconnected():
        print('Already connected!')
        cfg = wlan.ifconfig()
        print('IP:', cfg[0])
        return True
    
    print('Connecting to "' + SSID + '"...')
    wlan.connect(SSID, PASSWORD)
    
    retry = 0
    while not wlan.isconnected() and retry < MAX_RETRIES:
        status = wlan.status()
        
        status_msg = ["IDLE", "CONNECTING", "WRONG_PASSWORD", 
                     "NO_AP_FOUND", "CONNECT_FAIL", "GOT_IP"]
        if status < len(status_msg):
            print('[' + str(retry) + '] ' + status_msg[status])
        
        # 快速失敗
        if status in [2, 3]:  # WRONG_PASSWORD, NO_AP_FOUND
            print('ERROR: Cannot connect (' + status_msg[status] + ')')
            print('Starting in OFFLINE mode...')
            return False
        
        time.sleep_ms(TIMEOUT_MS)
        retry += 1
        
    if wlan.isconnected():
        print('\n=== WiFi Connected ===')
        cfg = wlan.ifconfig()
        print('IP: ' + cfg[0])
        print('Gateway: ' + cfg[2])
        print('=====================')
        return True
    else:
        print('\nWiFi timeout. Starting in OFFLINE mode...')
        return False

# Execute
wifi_ok = connect_wifi()

# [NEW] 導出狀態給 main.py
try:
    with open('.wifi_status', 'w') as f:
        f.write('1' if wifi_ok else '0')
except:
    pass