#include "config.h"
#include "app_motor.h"
#include "app_net.h"

void setup() {
    Serial.begin(115200);
    Serial.println("\n\n=== Booting ESP8266 Arm v2.0 (Modular C++) ===");
    
    app_motor_init();
    app_net_init();
    
    Serial.println("=== System Ready ===");
}

void loop() {
    app_net_update();
    app_motor_update();
    
    // Small delay to yield?
    // Not needed if code is non-blocking, but helps stability on ESP8266 WiFi stack
    delay(1); 
}
