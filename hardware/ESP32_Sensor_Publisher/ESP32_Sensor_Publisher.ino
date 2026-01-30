/*
 * HyperVolt ESP32 Sensor Publisher
 * ==================================
 *
 * This code reads sensors connected to ESP32 and publishes data to MQTT broker
 * for the HyperVolt energy management system.
 *
 * Hardware Connections:
 * - DHT11 Temperature/Humidity Sensor -> GPIO 4
 * - LDR (Light Sensor) -> GPIO 34
 * - Solar Voltage Sensor -> GPIO 35
 *
 * MQTT Topic: solar/data
 *
 * Author: HyperVolt Team
 * Date: January 30, 2026
 */

#include <DHT.h>
#include <WiFi.h>
#include <PubSubClient.h>
#include <NTPClient.h>
#include <WiFiUdp.h>

// ============================================================================
// CONFIGURATION - MODIFY THESE VALUES
// ============================================================================

// WiFi and MQTT Config
const char* ssid = "Aryan's S23 Ultra";
const char* password = "ALPHA SIERRA";
const char* mqtt_server = "10.118.115.78";

// Hardware Pins
#define DHTPIN 4
#define DHTTYPE DHT11
#define LDR_PIN 34
#define SOLAR_VOLT_PIN 35

// Constants
const float ADC_REF_VOLTAGE = 3.3;
const float ADC_RESOLUTION = 4095.0;
const float VOLTAGE_DIVIDER_RATIO = 1.0;
const float KNOWN_LOAD_RESISTANCE_OHMS = 10.0;

// ============================================================================
// GLOBAL OBJECTS
// ============================================================================

WiFiClient espClient;
PubSubClient client(espClient);
DHT dht(DHTPIN, DHTTYPE);
WiFiUDP ntpUDP;
NTPClient timeClient(ntpUDP, "pool.ntp.org", 19800); // GMT+5:30 for India

const char* mqtt_topic = "solar/data";

// ============================================================================
// FUNCTION PROTOTYPES
// ============================================================================

void setup_wifi();
void reconnect();
void publishSensor(const char* type, const char* id, float value, const char* unit);

// ============================================================================
// SETUP
// ============================================================================

void setup() {
  Serial.begin(115200);
  delay(1000);

  Serial.println("\n\n");
  Serial.println("========================================");
  Serial.println("  HyperVolt ESP32 Sensor Publisher");
  Serial.println("========================================");
  Serial.println();

  // Initialize DHT sensor
  Serial.println("Initializing DHT11 sensor...");
  dht.begin();

  // Set ADC attenuation for 0-3.3V range
  analogSetAttenuation(ADC_11db);

  // Setup WiFi
  setup_wifi();

  // Setup MQTT
  client.setServer(mqtt_server, 1883);

  Serial.println();
  Serial.println("========================================");
  Serial.println("  Setup Complete - Starting Loop");
  Serial.println("========================================");
  Serial.println();
}

// ============================================================================
// MAIN LOOP
// ============================================================================

void loop() {
  // Ensure MQTT connection
  if (!client.connected()) {
    reconnect();
  }
  client.loop();

  // Update NTP time
  timeClient.update();

  // Read Sensors
  float h = dht.readHumidity();
  float t = dht.readTemperature();
  int ldrRaw = analogRead(LDR_PIN);
  float solarVolt = analogRead(SOLAR_VOLT_PIN) * (ADC_REF_VOLTAGE / ADC_RESOLUTION);
  float solarCurr = (solarVolt / KNOWN_LOAD_RESISTANCE_OHMS) * 1000; // Current in mA

  Serial.println();
  Serial.print("Publishing sensor data at ");
  Serial.println(timeClient.getFormattedTime());

  // Publish individual sensor readings
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

  delay(5000); // 5-second interval
}

// ============================================================================
// WiFi SETUP
// ============================================================================

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

    // Start NTP client
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
      delay(1000);  // Halt execution
    }
  }
}

// ============================================================================
// MQTT RECONNECT
// ============================================================================

void reconnect() {
  int attempts = 0;
  while (!client.connected() && attempts < 5) {
    Serial.print("Attempting MQTT connection...");

    // Attempt connection
    // If you have MQTT authentication, use:
    // if (client.connect("ESP32SolarClient", MQTT_USERNAME, MQTT_PASSWORD)) {
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

// ============================================================================
// PUBLISH SENSOR DATA
// ============================================================================

void publishSensor(const char* type, const char* id, float value, const char* unit) {
  // Get current timestamp
  String timestamp = timeClient.getFormattedTime();

  // Create JSON message
  char msg[256];
  snprintf(msg, sizeof(msg),
    "{\"sensor_type\": \"%s\", \"sensor_id\": \"%s\", \"value\": %.2f, \"unit\": \"%s\", \"location\": \"solar_array\", \"timestamp\": \"%s\"}",
    type, id, value, unit, timestamp.c_str()
  );

  // Publish to MQTT
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
