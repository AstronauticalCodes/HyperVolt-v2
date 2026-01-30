# ESP32 Setup Guide for HyperVolt (Your Hardware)

## ✅ Your Current Setup

- **WiFi:** Aryan's S23 Ultra
- **MQTT Broker IP:** 10.118.115.78
- **Sensors:** DHT11, LDR, Solar Voltage Sensor
- **Pins:** DHT11 on GPIO 4, LDR on GPIO 34, Voltage on GPIO 35

---

## 📦 Required Libraries (Install via Arduino IDE)

1. **DHT sensor library** by Adafruit
2. **Adafruit Unified Sensor** (dependency for DHT)
3. **PubSubClient** by Nick O'Leary
4. **NTPClient** by Fabrice Weinberg

### How to Install:
1. Open Arduino IDE
2. Go to **Sketch → Include Library → Manage Libraries**
3. Search for each library name and click **Install**

---

## 📤 Upload to ESP32

### Step 1: Select Board
- Go to **Tools → Board → ESP32 Arduino → ESP32 Dev Module**

### Step 2: Select Port
- Go to **Tools → Port → COM3** (or whichever COM port your ESP32 is on)

### Step 3: Upload
- Click the **Upload** button (→ icon)
- Wait for "Hard resetting via RTS pin..."

### Step 4: Open Serial Monitor
- Go to **Tools → Serial Monitor**
- Set baud rate to **115200**

---

## ✅ Expected Serial Monitor Output

```
========================================
  HyperVolt ESP32 Sensor Publisher
========================================

Initializing DHT11 sensor...
Connecting to WiFi: Aryan's S23 Ultra
..........
✓ WiFi Connected!
  IP Address: 10.118.115.X
  Signal Strength: -45 dBm
Synchronizing time with NTP server...
  Current time: 17:30:05
Connecting to MQTT broker: 10.118.115.78:1883
Attempting MQTT connection... Connected!
  Publishing to topic: solar/data

========================================
  Setup Complete - Starting Loop
========================================

Publishing sensor data at 17:30:10
  ✓ Published: temperature = 24.5Celsius
  ✓ Published: humidity = 45.2%
  ✓ Published: light = 750.0raw
  ✓ Published: voltage = 1.2V
  ✓ Published: current = 120.0mA
  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

---

## 🧪 Testing

### Test 1: Verify MQTT Messages

On your PC, open PowerShell:

```powershell
mosquitto_sub -h localhost -t "solar/data" -v
```

You should see JSON messages every 5 seconds:

```json
solar/data {"sensor_type":"temperature","sensor_id":"temp_1","value":24.50,"unit":"Celsius","location":"solar_array","timestamp":"17:30:10"}
solar/data {"sensor_type":"humidity","sensor_id":"hum_1","value":45.20,"unit":"%","location":"solar_array","timestamp":"17:30:10"}
```

### Test 2: Check Django MQTT Listener

In your terminal running `mqtt_listener`, you should see:

```
✓ Processed sensor reading: temperature=24.5Celsius
✓ Processed sensor reading: humidity=45.2%
✓ Processed sensor reading: light=750raw
✓ Processed sensor reading: voltage=1.2V
✓ Processed sensor reading: current=120.0mA
```

### Test 3: Verify Database

```powershell
cd D:\Projects\HyperVolt\api
python manage.py shell
```

```python
from data_pipeline.models import SensorReading
print(f"Total readings: {SensorReading.objects.count()}")
print(f"Latest: {SensorReading.objects.order_by('-timestamp').first()}")
```

Should show increasing count!

---

## 🚀 Run the Complete System

### Prerequisites (Start these first):

**Terminal 1: Mosquitto**
```powershell
cd "C:\Program Files\mosquitto"
.\mosquitto.exe -v
```

**Terminal 2: Django API**
```powershell
cd D:\Projects\HyperVolt\api
.\.venv\Scripts\activate
daphne -b 0.0.0.0 -p 8000 hypervolt_backend.asgi:application
```

**Terminal 3: MQTT Listener**
```powershell
cd D:\Projects\HyperVolt\api
.\.venv\Scripts\activate
python manage.py mqtt_listener
```

**Terminal 4: Run Simulation**
```powershell
cd D:\Projects\HyperVolt\scripts
python run_simulation_with_sensors.py
```

---

## 📊 Expected Simulation Output

```
============================================================
  HYPERVOLT SIMULATION - WITH REAL SENSORS
============================================================

✅ API is available!
✅ Connected to MQTT broker at localhost:1883
📡 Subscribed to: HyperVolt/sensors/#
📡 Subscribed to: solar/data

============================================================
  Real-Time Sensor Simulation - 17:30:15
  MQTT Connected: ✅
  Iteration: 1
============================================================

📥 Received: temperature = 24.50 Celsius from solar_array
📥 Received: humidity = 45.20 % from solar_array
📥 Received: light = 750.00 raw from solar_array
📥 Received: voltage = 1.20 V from solar_array
📥 Received: current = 120.00 mA from solar_array

📊 Latest Sensor Readings:
   temperature: 24.50 Celsius (solar_array)
   humidity: 45.20 % (solar_array)
   light: 750.00 raw (solar_array)
   voltage: 1.20 V (solar_array)
   current: 120.00 mA (solar_array)

🌍 Current Conditions (for AI):
   Hour: 17
   Temperature: 24.5°C
   Solar Radiation: 183.1 W/m²

📈 Cumulative Stats:
   Total Sensor Readings: 5
   Successful API Calls: 5
   AI Decisions: 0
   Total Cost: ₹0.00
   Total Carbon: 0.00 kg CO2
```

At **iteration 6** (3 minutes), you'll see AI decisions!

---

## 🛠️ Troubleshooting

### ESP32 Won't Connect to WiFi

**Check:**
- WiFi SSID is correct: `Aryan's S23 Ultra`
- Password is correct: `ALPHA SIERRA`
- ESP32 is within WiFi range
- Your hotspot is turned on

### ESP32 Won't Connect to MQTT

**Error Code Meanings:**

| Error | Meaning | Solution |
|-------|---------|----------|
| -2 | Network failure | Check PC IP: `10.118.115.78` is correct |
| -4 | Timeout | Check firewall, allow port 1883 |
| 2 | Refused | Mosquitto not running |
| 5 | Auth failed | Check username/password if enabled |

**Fix Firewall (Windows):**
```powershell
netsh advfirewall firewall add rule name="Mosquitto MQTT" dir=in action=allow protocol=TCP localport=1883
```

### DHT11 Shows NaN (Not a Number)

**Check:**
- DHT11 is connected to GPIO 4
- VCC → 3.3V
- GND → GND
- Try different DHT11 sensor (might be faulty)

### LDR Always Shows Same Value

**Solution:**
- Expose LDR to light / cover with hand
- Value should change (higher = more light)
- Adjust `KNOWN_LOAD_RESISTANCE_OHMS` if needed

### Current/Voltage Always Zero

**Check:**
- Solar panel is connected
- Voltage sensor is connected to GPIO 35
- Solar panel is exposed to light
- Check wiring connections

---

## 📝 Notes

### Current Calculation

Your code calculates current using:
```
Current (mA) = (Voltage / 10Ω) × 1000
```

This assumes a **10Ω load resistor** is in series with the solar panel.

### Timestamp Format

NTP Client returns time in **HH:MM:SS** format (e.g., `17:30:45`).

Django has been **fixed** to handle this format correctly by converting it to a full datetime.

### Publish Interval

Your ESP32 publishes every **5 seconds** (5000 ms).

---

## ✅ Quick Checklist

Before running, ensure:

- [x] ESP32 code uploaded successfully
- [x] Serial Monitor shows "Connected!" for WiFi and MQTT
- [x] Mosquitto running on PC
- [x] Django API running
- [x] Django MQTT listener running
- [x] Firewall allows port 1883
- [x] All sensors connected properly

---

## 🎯 What Happens Next

1. **ESP32 publishes** sensor data every 5 seconds to `solar/data`
2. **Django MQTT Listener** receives and saves data to database
3. **Simulation script** fetches data and calls AI
4. **AI makes decisions** every 30 seconds (at iteration 6)
5. **Frontend displays** real-time sensor data

---

**Your real ESP32 is now fully integrated with HyperVolt!** 🎉

The Arduino file is located at:
```
D:\Projects\HyperVolt\hardware\ESP32_Sensor_Publisher\ESP32_Sensor_Publisher.ino
```

Just upload it to your ESP32 and run the simulation!
