
#include <DHT.h>
#include <WiFi.h>
#include <PubSubClient.h>
#include <NTPClient.h>
#include <WiFiUdp.h>

const char* ssid = "Aryan's S23 Ultra";
const char* password = "ALPHA SIERRA";
const char* mqtt_server = "10.118.115.78";

#define DHTPIN 4
#define DHTTYPE DHT11
#define LDR_PIN 34
#define SOLAR_VOLT_PIN 35

const float ADC_REF_VOLTAGE = 3.3;
const float ADC_RESOLUTION = 4095.0;
const float VOLTAGE_DIVIDER_RATIO = 1.0;
const float KNOWN_LOAD_RESISTANCE_OHMS = 10.0;

WiFiClient espClient;
PubSubClient client(espClient);
DHT dht(DHTPIN, DHTTYPE);
WiFiUDP ntpUDP;
NTPClient timeClient(ntpUDP, "pool.ntp.org", 19800);

const char* mqtt_topic = "solar/data";

void setup_wifi();
void reconnect();
void publishSensor(const char* type, const char* id, float value, const char* unit);

void setup() {
  Serial.begin(115200);
  delay(1000);

  Serial.println("\n\n");
  Serial.println("========================================");
  Serial.println("  HyperVolt ESP32 Sensor Publisher");
  Serial.println("========================================");
  Serial.println();

  Serial.println("Initializing DHT11 sensor...");
  dht.begin();

  analogSetAttenuation(ADC_11db);

  setup_wifi();

  client.setServer(mqtt_server, 1883);

  Serial.println();
  Serial.println("========================================");
  Serial.println("  Setup Complete - Starting Loop");
  Serial.println("========================================");
  Serial.println();
}

void loop() {
  if (!client.connected()) {
    reconnect();
  }
  client.loop();

  timeClient.update();

  float h = dht.readHumidity();
  float t = dht.readTemperature();
  int ldrRaw = analogRead(LDR_PIN);
  float solarVolt = analogRead(SOLAR_VOLT_PIN) * (ADC_REF_VOLTAGE / ADC_RESOLUTION);
  float solarCurr = (solarVolt / KNOWN_LOAD_RESISTANCE_OHMS) * 1000;

  Serial.println();
  Serial.print("Publishing sensor data at ");
  Serial.println(timeClient.getFormattedTime());

  if (!isnan(t)) {
    publishSensor("temperature", "temp_1", t, "Celsius");
  } else {
    Serial.println("  ⚠ Failed to read temperature from DHT11");
  }

  if (!isnan(h)) {
    publishSensor("humidity", "hum_1", h, "%");
  } else {
    Serial.println("  ⚠ Failed to read humidity from DHT11");
  }

  publishSensor("light", "ldr_1", (float)ldrRaw, "raw");
  publishSensor("voltage", "volt_1", solarVolt, "V");
  publishSensor("current", "curr_1", solarCurr, "mA");

  Serial.println("  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━");

  delay(5000);
}

void setup_wifi() {
  Serial.print("Connecting to WiFi: ");
  Serial.println(ssid);

  WiFi.mode(WIFI_STA);
  WiFi.begin(ssid, password);

  int attempts = 0;
  while (WiFi.status() != WL_CONNECTED && attempts < 30) {
    delay(500);
    Serial.print(".");
    attempts++;
  }

  if (WiFi.status() == WL_CONNECTED) {
    Serial.println();
    Serial.println("✓ WiFi Connected!");
    Serial.print("  IP Address: ");
    Serial.println(WiFi.localIP());
    Serial.print("  Signal Strength: ");
    Serial.print(WiFi.RSSI());
    Serial.println(" dBm");

    Serial.println("Synchronizing time with NTP server...");
    timeClient.begin();
    timeClient.update();
    Serial.print("  Current time: ");
    Serial.println(timeClient.getFormattedTime());
  } else {
    Serial.println();
    Serial.println("✗ WiFi Connection Failed!");
    Serial.println("  Please check your SSID and password.");
    while (1) {
      delay(1000);
    }
  }
}

void reconnect() {
  int attempts = 0;
  while (!client.connected() && attempts < 5) {
    Serial.print("Attempting MQTT connection...");

    if (client.connect("ESP32SolarClient")) {
      Serial.println(" Connected!");
      Serial.print("  Publishing to topic: ");
      Serial.println(mqtt_topic);
      return;
    } else {
      Serial.print(" Failed, rc=");
      Serial.print(client.state());
      Serial.println(" - Retrying in 5 seconds...");
      delay(5000);
      attempts++;
    }
  }

  if (!client.connected()) {
    Serial.println("✗ MQTT Connection Failed after 5 attempts");
    Serial.println("  Please check:");
    Serial.println("  - MQTT broker IP address: " + String(mqtt_server));
    Serial.println("  - Mosquitto is running on your PC");
    Serial.println("  - Firewall allows port 1883");
  }
}

void publishSensor(const char* type, const char* id, float value, const char* unit) {
  String timestamp = timeClient.getFormattedTime();

  char msg[256];
  snprintf(msg, sizeof(msg),
    "{\"sensor_type\": \"%s\", \"sensor_id\": \"%s\", \"value\": %.2f, \"unit\": \"%s\", \"location\": \"solar_array\", \"timestamp\": \"%s\"}",
    type, id, value, unit, timestamp.c_str()
  );

  if (client.publish(mqtt_topic, msg)) {
    Serial.print("  ✓ Published: ");
    Serial.print(type);
    Serial.print(" = ");
    Serial.print(value);
    Serial.println(unit);
  } else {
    Serial.print("  ✗ Failed to publish: ");
    Serial.println(type);
  }
}
