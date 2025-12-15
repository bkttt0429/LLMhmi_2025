
import network
import time

# === WiFi Configuration ===
SSID = "Bk"
PASSWORD = "........." # Correct Password
MAX_RETRIES = 40
TIMEOUT_MS = 500

def connect_wifi():
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    
    # Debug Info
    mac = wlan.config('mac')
    print('MAC:', ':'.join(['%02X' % b for b in mac]))
    
    if not wlan.isconnected():
        print('Connecting to "' + SSID + '"...')
        wlan.connect(SSID, PASSWORD)
        
        retry = 0
        while not wlan.isconnected() and retry < MAX_RETRIES:
            status = wlan.status()
            
            # Status Display
            status_msg = ["IDLE", "CONNECTING", "WRONG_PASSWORD", 
                         "NO_AP_FOUND", "CONNECT_FAIL", "GOT_IP"]
            if status < len(status_msg):
                print('[' + str(retry) + '] Status: ' + str(status) + ' (' + status_msg[status] + ')')
            else:
                print('[' + str(retry) + '] Status: ' + str(status))
            
            # Fatal Errors
            if status == 2:  # WRONG_PASSWORD
                print('ERROR: Wrong password!')
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
        print('\nWiFi Connection Failed!')
        return False

# Execute
connect_wifi()