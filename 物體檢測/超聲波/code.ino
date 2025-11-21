// 單一 SIG 腳位超聲波
const int SIG_PIN = 8;

long duration;      // 收到回波的時間（微秒）
float distance_cm;  // 距離（公分）

void setup() {
  Serial.begin(115200);  // ★ 跟 Python 一樣

  pinMode(SIG_PIN, OUTPUT);

  digitalWrite(SIG_PIN, LOW);
  delay(50);
}

void loop() {
  pinMode(SIG_PIN, OUTPUT);
  digitalWrite(SIG_PIN, LOW);
  delayMicroseconds(2);
  digitalWrite(SIG_PIN, HIGH);
  delayMicroseconds(10);
  digitalWrite(SIG_PIN, LOW);

  pinMode(SIG_PIN, INPUT);
  duration = pulseIn(SIG_PIN, HIGH, 30000);

  if (duration == 0) {
    Serial.println(-1);  // 沒回波就印 -1
  } else {
    distance_cm = duration * 0.034f / 2.0f;
    Serial.println(distance_cm);   // ★ 只印數字
  }

  delay(200);
}
