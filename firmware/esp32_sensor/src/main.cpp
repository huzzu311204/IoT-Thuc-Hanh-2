#include <Arduino.h>
#include <WiFi.h>
#include <PubSubClient.h>
#include <DHTesp.h>
#include <time.h>
#include <sys/time.h>

const char* WIFI_SSID = "Wokwi-GUEST";
const char* WIFI_PASSWORD = "";

// Broker công cộng, đổi số 4821 thành số riêng của bạn
const char* MQTT_SERVER = "broker.hivemq.com";
const int   MQTT_PORT   = 1883;
const char* DEVICE_ID   = "esp32-wokwi";
const char* TOPIC       = "iot/lab2/huu-4821/esp32-wokwi/telemetry";

const int DHT_PIN  = 15;
const int TRIG_PIN = 5;
const int ECHO_PIN = 18;
const int LED_PIN  = 2;

const unsigned long SEND_INTERVAL_MS = 2000;

WiFiClient wifiClient;
PubSubClient mqttClient(wifiClient);
DHTesp dht;

unsigned long lastSend = 0;
unsigned long sequenceNo = 0;

void connectWiFi() {
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD, 6);
  Serial.print("Connecting WiFi");
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println("\nWiFi connected, RSSI: " + String(WiFi.RSSI()));
}

void connectMQTT() {
  while (!mqttClient.connected()) {
    String clientId = "esp32-lab2-" + String((uint32_t)ESP.getEfuseMac(), HEX);
    Serial.print("Connecting MQTT... ");
    if (mqttClient.connect(clientId.c_str())) {
      Serial.println("connected");
    } else {
      Serial.print("failed, rc = ");
      Serial.println(mqttClient.state());
      delay(2000);
    }
  }
}

float readDistanceCm() {
  digitalWrite(TRIG_PIN, LOW);
  delayMicroseconds(2);
  digitalWrite(TRIG_PIN, HIGH);
  delayMicroseconds(10);
  digitalWrite(TRIG_PIN, LOW);
  unsigned long duration = pulseIn(ECHO_PIN, HIGH, 30000);
  if (duration == 0) return NAN;
  return duration * 0.0343f / 2.0f;
}

uint64_t nowMs() {
  struct timeval tv;
  gettimeofday(&tv, NULL);
  return (uint64_t)tv.tv_sec * 1000ULL + tv.tv_usec / 1000;
}

void setup() {
  Serial.begin(115200);
  delay(1000);

  pinMode(TRIG_PIN, OUTPUT);
  pinMode(ECHO_PIN, INPUT);
  pinMode(LED_PIN, OUTPUT);
  dht.setup(DHT_PIN, DHTesp::DHT22);

  connectWiFi();

  configTime(0, 0, "pool.ntp.org");
  while (time(nullptr) < 1700000000) delay(200);
  Serial.println("Time synced");

  mqttClient.setServer(MQTT_SERVER, MQTT_PORT);
  mqttClient.setBufferSize(256);
}

void loop() {
  if (WiFi.status() != WL_CONNECTED) connectWiFi();
  if (!mqttClient.connected()) connectMQTT();
  mqttClient.loop();

  unsigned long now = millis();
  if (now - lastSend < SEND_INTERVAL_MS) return;
  lastSend = now;

  TempAndHumidity data = dht.getTempAndHumidity();
  float distance = readDistanceCm();
  sequenceNo++;

  char payload[256];
  int n = snprintf(payload, sizeof(payload),
    "{\"device_id\":\"%s\",\"ts\":%llu,\"seq\":%lu,\"rssi\":%d",
    DEVICE_ID, nowMs(), sequenceNo, WiFi.RSSI());
  if (isfinite(data.temperature))
    n += snprintf(payload + n, sizeof(payload) - n, ",\"temperature\":%.2f", data.temperature);
  if (isfinite(data.humidity))
    n += snprintf(payload + n, sizeof(payload) - n, ",\"humidity\":%.2f", data.humidity);
  if (isfinite(distance))
    n += snprintf(payload + n, sizeof(payload) - n, ",\"distance_cm\":%.2f", distance);
  snprintf(payload + n, sizeof(payload) - n, "}");

  bool ok = mqttClient.publish(TOPIC, payload);
  Serial.printf("[%lu] %s -> %s\n", sequenceNo, payload, ok ? "OK" : "FAILED");

  if (ok) {
    digitalWrite(LED_PIN, HIGH);
    delay(80);
    digitalWrite(LED_PIN, LOW);
  }
}