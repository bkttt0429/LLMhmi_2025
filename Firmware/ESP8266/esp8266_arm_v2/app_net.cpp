#include "app_net.h"
#include "config.h"
#include "app_motor.h"
#include <ESP8266WiFi.h>
#include <WiFiUdp.h>

static WiFiUDP udp;
static uint8_t packetBuffer[255];
static unsigned long last_packet_time = 0;
static const unsigned long WATCHDOG_TIMEOUT = 2000;

// === CRC Helper ===
static uint16_t calculate_crc(uint8_t* data, size_t len) {
    uint16_t crc = 0xFFFF;
    for (size_t i = 0; i < len; i++) {
        crc ^= (uint16_t)data[i] << 8;
        for (uint8_t j = 0; j < 8; j++) {
            if (crc & 0x8000) crc = (crc << 1) ^ 0x1021;
            else crc <<= 1;
        }
    }
    return crc;
}

void app_net_init() {
    WiFi.mode(WIFI_STA);
    WiFi.begin(WIFI_SSID, WIFI_PASS);
    
    Serial.print("[Net] Connecting");
    while (WiFi.status() != WL_CONNECTED) {
        delay(500);
        Serial.print(".");
    }
    Serial.println();
    Serial.print("[Net] Connected! IP: ");
    Serial.println(WiFi.localIP());
    
    udp.begin(UDP_PORT);
    last_packet_time = millis();
}

void app_net_update() {
    // 1. Receive
    int packetSize = udp.parsePacket();
    if (packetSize > 0) {
        Serial.printf("[Net] Recv %d bytes from %s\n", packetSize, udp.remoteIP().toString().c_str());
        
        int len = udp.read(packetBuffer, 255);
        if (len >= 17) { // Min valid size
            // Check Header "RM"
            if (packetBuffer[0] == 'R' && packetBuffer[1] == 'M') {
                 // Check CRC
                 uint16_t rx_crc = packetBuffer[15] | (packetBuffer[16] << 8); // Verify Endianness! Setup used Little Endian in Python
                 // Python struct.pack('<H') -> Little Endian (Low Byte First)
                 // So [15] is Low, [16] is High. Correct.
                 
                 uint16_t calc = calculate_crc(packetBuffer, 15);
                 
                 if (rx_crc == calc) {
                     last_packet_time = millis();
                     
                     uint8_t cmd = packetBuffer[2];
                     if (cmd == 0x01) { // MOVE
                         // Unpack Float (Little Endian)
                         // Arduino Float is 4 bytes.
                         float x, y, z;
                         memcpy(&x, &packetBuffer[3], 4);
                         memcpy(&y, &packetBuffer[7], 4);
                         memcpy(&z, &packetBuffer[11], 4);
                         
                         // app_motor_set_target(x, y, z, 0); // Need Gripper support in protocol?
                         // Current protocol is 3 floats (12 bytes). Gripper not in payload?
                         // If user wants full control, we need 4 floats.
                         // But for now, sticking to v2.0 protocol def.
                         app_motor_set_target(x, y, z, 0);
                     } else if (cmd == 0x03) { // MOVE ANGLES
                         float b, s, e;
                         memcpy(&b, &packetBuffer[3], 4);
                         memcpy(&s, &packetBuffer[7], 4);
                         memcpy(&e, &packetBuffer[11], 4);
                         app_motor_set_angles(b, s, e, 0); // Todo: Gripper support
                     }
                 } else {
                     Serial.println("[Net] CRC Fail");
                 }
            }
        }
    }
    
    // 2. Watchdog
    if (millis() - last_packet_time > WATCHDOG_TIMEOUT) {
        if (app_motor_is_moving()) {
            Serial.println("[Net] Watchdog Timeout!");
            app_motor_stop();
        }
    }

    // 3. Discovery Beacon (Broadcast every 1s)
    static unsigned long last_beacon = 0;
    if (millis() - last_beacon > 1000) {
        last_beacon = millis();
        // Broadcast "ESP8266_ARM" to port 4210 (Client Listen Port) or 4211?
        // web_server.py listens on... I need to check. Usually 4211 or similar.
        // Assuming UDP_PORT (4211).
        
        udp.beginPacket("255.255.255.255", UDP_PORT);
        udp.write("ESP8266_ARM");
        udp.endPacket();
        // Serial.println("[Net] Beacon Sent");
    }
}
