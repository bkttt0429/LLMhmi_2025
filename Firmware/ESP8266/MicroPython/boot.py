
import network
import time
from machine import Pin

# Indicate Booting (LED ON/OFF)
led = Pin(2, Pin.OUT)
led.value(0) # Logic Low = ON for built-in LED usually

ssid = "Bk"
password = "........." # TODO: Update with Real Password

def connect_wifi():
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    if not wlan.isconnected():
        print('Connecting to network...')
        wlan.connect(ssid, password)
        retry = 0
        while not wlan.isconnected() and retry < 20:
            led.value(not led.value()) # Blink
            time.sleep(0.5)
            print('.', end='')
            retry += 1
            
    if wlan.isconnected():
        print('\nNetwork config:', wlan.ifconfig())
        led.value(1) # OFF (Connected)
    else:
        print('\nWiFi Failed')
        led.value(0) # ON (Error)

connect_wifi()
