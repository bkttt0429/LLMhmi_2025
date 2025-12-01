/**
 * ESP32-S3-CAM AP Mode v7.0 (Dual NIC Design)
 * Changes:
 *   1. Switched to WiFi AP Mode
 *   2. Fixed IP: 192.168.4.1
 *   3. SSID: ESP32CAM
 */

#include "esp_camera.h"
#include <WiFi.h>
#include <WiFiUdp.h>
#include <WebServer.h>

// ============= WiFi AP Settings =============
const char* ssid_ap     = "ESP32CAM";
const char* password_ap = "12345678"; // 8 chars min

// ============= IP Settings =============
IPAddress local_ip(192, 168, 4, 1);
IPAddress gateway(192, 168, 4, 1);
IPAddress subnet(255, 255, 255, 0);

// ============= Hardware Pins =============
#define PWDN_GPIO_NUM     -1
#define RESET_GPIO_NUM    -1
#define XCLK_GPIO_NUM     15
#define SIOD_GPIO_NUM     4
#define SIOC_GPIO_NUM     5
#define Y9_GPIO_NUM       16
#define Y8_GPIO_NUM       17
#define Y7_GPIO_NUM       18
#define Y6_GPIO_NUM       12
#define Y5_GPIO_NUM       10
#define Y4_GPIO_NUM       8
#define Y3_GPIO_NUM       9
#define Y2_GPIO_NUM       11
#define VSYNC_GPIO_NUM    6
#define HREF_GPIO_NUM     7
#define PCLK_GPIO_NUM     13
#define LED_PIN           48
#define SIG_PIN           21

// ============= Globals =============
WebServer server(81);
WiFiClient streamClient;
WiFiUDP udp;

bool streamActive = false;
unsigned long lastStreamFrame = 0;
const uint16_t TARGET_FPS_INTERVAL_MS = 40;  // 25 FPS
const uint16_t IP_BROADCAST_PORT = 4211;
unsigned long lastIPBroadcast = 0;

// ============= Ultrasonic =============
void init_ultrasonic() {
  pinMode(SIG_PIN, INPUT_PULLDOWN);
  Serial.println("[OK] Ultrasonic @ GPIO21");
}

float get_distance() {
  pinMode(SIG_PIN, OUTPUT);
  digitalWrite(SIG_PIN, LOW);
  delayMicroseconds(2);
  digitalWrite(SIG_PIN, HIGH);
  delayMicroseconds(10);
  digitalWrite(SIG_PIN, LOW);
  pinMode(SIG_PIN, INPUT_PULLUP);
  unsigned long duration = pulseIn(SIG_PIN, HIGH, 30000);
  if (duration == 0) return -1.0;
  return duration * 0.034 / 2.0;
}

// ============= Camera Init =============
bool init_camera() {
  camera_config_t config;
  config.ledc_channel = LEDC_CHANNEL_0;
  config.ledc_timer   = LEDC_TIMER_0;
  config.pin_d0 = Y2_GPIO_NUM;
  config.pin_d1 = Y3_GPIO_NUM;
  config.pin_d2 = Y4_GPIO_NUM;
  config.pin_d3 = Y5_GPIO_NUM;
  config.pin_d4 = Y6_GPIO_NUM;
  config.pin_d5 = Y7_GPIO_NUM;
  config.pin_d6 = Y8_GPIO_NUM;
  config.pin_d7 = Y9_GPIO_NUM;
  config.pin_xclk = XCLK_GPIO_NUM;
  config.pin_pclk = PCLK_GPIO_NUM;
  config.pin_vsync = VSYNC_GPIO_NUM;
  config.pin_href = HREF_GPIO_NUM;
  config.pin_sscb_sda = SIOD_GPIO_NUM;
  config.pin_sscb_scl = SIOC_GPIO_NUM;
  config.pin_pwdn = PWDN_GPIO_NUM;
  config.pin_reset = RESET_GPIO_NUM;
  config.xclk_freq_hz = 20000000;
  config.pixel_format = PIXFORMAT_JPEG;

  if (psramFound()) {
    Serial.println("[CAMERA] Using PSRAM mode");
    config.frame_size = FRAMESIZE_VGA;
    config.jpeg_quality = 12;
    config.fb_count = 2;
    config.fb_location = CAMERA_FB_IN_PSRAM;
    config.grab_mode = CAMERA_GRAB_LATEST;
  } else {
    Serial.println("[CAMERA] Using SRAM mode (limited)");
    config.frame_size = FRAMESIZE_QVGA;
    config.jpeg_quality = 15;
    config.fb_count = 1;
    config.fb_location = CAMERA_FB_IN_DRAM;
  }

  esp_err_t err = esp_camera_init(&config);
  if (err != ESP_OK) {
    Serial.printf("[ERROR] Camera init failed: 0x%x\n", err);
    return false;
  }

  sensor_t *s = esp_camera_sensor_get();
  if (s) {
    s->set_brightness(s, 0);
    s->set_contrast(s, 0);
    s->set_saturation(s, 0);
    s->set_special_effect(s, 0);
    s->set_whitebal(s, 1);
    s->set_awb_gain(s, 1);
    s->set_wb_mode(s, 0);
    s->set_exposure_ctrl(s, 1);
    s->set_aec2(s, 1);
    s->set_ae_level(s, 0);
    s->set_aec_value(s, 300);
    s->set_gain_ctrl(s, 1);
    s->set_agc_gain(s, 0);
    s->set_gainceiling(s, (gainceiling_t)0);
    s->set_bpc(s, 0);
    s->set_wpc(s, 1);
    s->set_raw_gma(s, 1);
    s->set_lenc(s, 1);
    s->set_hmirror(s, 0);
    s->set_vflip(s, 0);
    s->set_dcw(s, 1);
    s->set_colorbar(s, 0);
  }
  
  Serial.println("[OK] Camera initialized");
  return true;
}

// ============= UDP Broadcast (Optional in AP mode, but kept for compatibility) =============
void broadcast_ip_udp() {
  // In AP mode, we are always 192.168.4.1, but broadcasting helps some listeners
  IPAddress broadcastIp = WiFi.softAPIP();
  broadcastIp[3] = 255; // 192.168.4.255

  udp.beginPacket(broadcastIp, IP_BROADCAST_PORT);
  udp.print("ESP32S3CAM_IP:");
  udp.print(WiFi.softAPIP().toString());
  udp.print(";STREAM:http://");
  udp.print(WiFi.softAPIP().toString());
  udp.print(":81/stream");
  udp.endPacket();
}

void announce_ip(bool force = false) {
  unsigned long now = millis();
  if (force || now - lastIPBroadcast >= 1000) {
    lastIPBroadcast = now;
    broadcast_ip_udp();
  }
}

// ============= HTTP Routes =============
void handle_root() {
  String html = "<!DOCTYPE html><html><head><meta charset='UTF-8'>"
                "<title>ESP32-S3 CAM (AP)</title>"
                "<style>body{font-family:Arial;background:#000;color:#0f0;text-align:center;}"
                "img{width:100%;max-width:800px;border:3px solid #0f0;}</style></head>"
                "<body><h1>ESP32-S3 CAM ONLINE (AP)</h1>"
                "<p>IP: " + WiFi.softAPIP().toString() + "</p>"
                "<img src='/stream'></body></html>";
  server.send(200, "text/html", html);
}

void handle_capture() {
  camera_fb_t *fb = esp_camera_fb_get();
  if (!fb) {
    server.send(500, "text/plain", "Capture failed");
    return;
  }
  server.sendHeader("Content-Type", "image/jpeg");
  server.send_P(200, "image/jpeg", (const char*)fb->buf, fb->len);
  esp_camera_fb_return(fb);
}

void handle_stream() {
  if (streamActive && streamClient) {
    streamClient.stop();
    streamActive = false;
    Serial.println("[STREAM] Closing old client");
    delay(100);
  }
  
  streamClient = server.client();
  if (!streamClient || !streamClient.connected()) {
    Serial.println("[STREAM] Client connection failed");
    return;
  }
  
  streamClient.setNoDelay(true);
  streamClient.setTimeout(5000);
  
  streamClient.println("HTTP/1.1 200 OK");
  streamClient.println("Content-Type: multipart/x-mixed-replace; boundary=frame");
  streamClient.println("Access-Control-Allow-Origin: *");
  streamClient.println("Cache-Control: no-cache, no-store, must-revalidate");
  streamClient.println("Pragma: no-cache");
  streamClient.println("Expires: 0");
  streamClient.println("Connection: close");
  streamClient.println();
  
  streamActive = true;
  lastStreamFrame = millis();
  Serial.printf("[STREAM] Client: %s\n", streamClient.remoteIP().toString().c_str());
}

void handle_light() {
  if (server.hasArg("on")) {
    bool state = server.arg("on").toInt();
    digitalWrite(LED_PIN, state ? HIGH : LOW);
    server.send(200, "text/plain", state ? "ON" : "OFF");
  }
}

void handle_dist() {
  float d = get_distance();
  server.send(200, "text/plain", String(d));
}

// ============= Setup =============
void setup() {
  Serial.begin(115200);
  delay(1000);
  
  pinMode(LED_PIN, OUTPUT);
  digitalWrite(LED_PIN, LOW);
  init_ultrasonic();

  Serial.println("\n=== ESP32-S3-CAM v7.0 AP Mode ===");

  if (!init_camera()) {
    Serial.println("Camera FATAL ERROR!");
    while (1) { 
      digitalWrite(LED_PIN, !digitalRead(LED_PIN)); 
      delay(200); 
    }
  }

  // ★ Switch to AP Mode
  WiFi.mode(WIFI_AP);
  WiFi.softAPConfig(local_ip, gateway, subnet);
  if (WiFi.softAP(ssid_ap, password_ap)) {
      Serial.println("AP Created Successfully");
      Serial.print("SSID: "); Serial.println(ssid_ap);
      Serial.print("IP: "); Serial.println(WiFi.softAPIP());
      Serial.printf("Stream: http://%s:81/stream\n", WiFi.softAPIP().toString().c_str());
  } else {
      Serial.println("AP Creation Failed");
      while (1) delay(1000);
  }

  udp.begin(IP_BROADCAST_PORT);

  server.on("/", handle_root);
  server.on("/capture", handle_capture);
  server.on("/stream", handle_stream);
  server.on("/light", handle_light);
  server.on("/dist", handle_dist); // Added explicit endpoint for distance
  server.begin();

  // Blink to indicate ready
  for (int i = 0; i < 3; i++) {
    digitalWrite(LED_PIN, HIGH); delay(100);
    digitalWrite(LED_PIN, LOW);  delay(100);
  }

  Serial.println("SYSTEM READY!");
}

// ============= Loop =============
void loop() {
  server.handleClient();

  if (streamActive) {
    if (!streamClient || !streamClient.connected()) {
      streamActive = false;
      if (streamClient) streamClient.stop();
      Serial.println("[STREAM] Client disconnected");
      return;
    }

    unsigned long now = millis();
    if (now - lastStreamFrame >= TARGET_FPS_INTERVAL_MS) {
      lastStreamFrame = now;
      
      camera_fb_t *fb = esp_camera_fb_get();
      if (!fb) {
        // Serial.println("[STREAM] Frame get failed");
        return;
      }
      
      if (fb->len == 0 || fb->buf == NULL) {
        esp_camera_fb_return(fb);
        return;
      }

      if (!streamClient.print("--frame\r\n")) {
        esp_camera_fb_return(fb);
        streamActive = false;
        streamClient.stop();
        return;
      }
      
      if (!streamClient.printf("Content-Type: image/jpeg\r\nContent-Length: %u\r\n\r\n", fb->len)) {
        esp_camera_fb_return(fb);
        streamActive = false;
        streamClient.stop();
        return;
      }
      
      size_t sent = 0;
      const size_t CHUNK_SIZE = 1024;
      bool success = true;
      
      while (sent < fb->len && streamClient.connected()) {
        size_t to_send = min(CHUNK_SIZE, fb->len - sent);
        size_t written = streamClient.write(fb->buf + sent, to_send);
        
        if (written != to_send) {
          success = false;
          break;
        }
        sent += written;
        
        if (sent % (CHUNK_SIZE * 4) == 0) {
          yield();
        }
      }
      
      if (success && !streamClient.print("\r\n")) {
        success = false;
      }
      
      esp_camera_fb_return(fb);
      
      if (!success) {
        streamActive = false;
        streamClient.stop();
      }
    }
  }

  announce_ip();
  delay(1);
}
