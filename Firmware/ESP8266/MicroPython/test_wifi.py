import network
import time

print("\n" + "=" * 50)
print("ESP-12F WiFi Test")
print("=" * 50)

wlan = network.WLAN(network.STA_IF)
wlan.active(True)

# MAC Address
mac_bytes = wlan.config('mac')
mac_str = ':'.join(['%02X' % b for b in mac_bytes])
print("\nMAC Address: " + mac_str)

print("\nScanning networks...")
networks = wlan.scan()
print("Found " + str(len(networks)) + " networks:")
for net in networks:
    ssid = net[0].decode('utf-8')
    rssi = net[3]
    print("  " + ssid + " Signal: " + str(rssi) + " dBm")

print("\n" + "=" * 50)
print("Connecting to 'Bk'...")
print("=" * 50)

# 請替換成你的實際密碼
wlan.connect("Bk", ".........")

for i in range(30):
    status = wlan.status()
    status_names = ["IDLE", "CONNECTING", "WRONG_PASSWORD", "NO_AP_FOUND", "CONNECT_FAIL", "GOT_IP"]
    status_text = status_names[status] if status < len(status_names) else "UNKNOWN"
    
    print("[" + str(i) + "] Status: " + str(status) + " (" + status_text + ")")
    
    if status == 5:  # GOT_IP
        print("\n✅ SUCCESS!")
        cfg = wlan.ifconfig()
        print("IP Address: " + cfg[0])
        print("Gateway: " + cfg[2])
        break
    elif status in [2, 3, 4]:  # Error states
        print("\n❌ FAILED: " + status_text)
        break
    
    time.sleep(0.5)

print("\n" + "=" * 50)