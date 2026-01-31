import json
import time
import random
from datetime import datetime
import paho.mqtt.client as mqtt

class SensorSimulator:

    def __init__(self, broker_host='localhost', broker_port=1883):
        self.broker_host = broker_host
        self.broker_port = broker_port
        self.client = mqtt.Client(client_id='sensor_simulator')
        self.topic_prefix = 'HyperVolt/sensors'

    def connect(self):
        print(f"Connecting to MQTT broker at {self.broker_host}:{self.broker_port}")
        self.client.connect(self.broker_host, self.broker_port, keepalive=60)
        self.client.loop_start()
        time.sleep(1)
        print("Connected!")

    def disconnect(self):
        self.client.loop_stop()
        self.client.disconnect()
        print("Disconnected!")

    def simulate_ldr_reading(self):
        value = random.randint(200, 900)

        return {
            'sensor_type': 'ldr',
            'sensor_id': 'ldr_1',
            'value': value,
            'unit': 'lux',
            'location': 'living_room',
            'timestamp': datetime.utcnow().isoformat() + 'Z'
        }

    def simulate_current_reading(self):
        value = round(random.uniform(0.5, 5.0), 2)

        return {
            'sensor_type': 'current',
            'sensor_id': 'current_1',
            'value': value,
            'unit': 'amperes',
            'location': 'living_room',
            'timestamp': datetime.utcnow().isoformat() + 'Z'
        }

    def simulate_temperature_reading(self):
        value = round(random.uniform(22.0, 32.0), 1)

        return {
            'sensor_type': 'temperature',
            'sensor_id': 'temp_1',
            'value': value,
            'unit': 'celsius',
            'location': 'living_room',
            'timestamp': datetime.utcnow().isoformat() + 'Z'
        }

    def simulate_humidity_reading(self):
        value = round(random.uniform(45.0, 75.0), 1)

        return {
            'sensor_type': 'humidity',
            'sensor_id': 'humidity_1',
            'value': value,
            'unit': 'percent',
            'location': 'living_room',
            'timestamp': datetime.utcnow().isoformat() + 'Z'
        }

    def simulate_voltage_reading(self):
        value = round(random.uniform(10.0, 22.0), 1)

        return {
            'sensor_type': 'voltage',
            'sensor_id': 'solar_voltage_1',
            'value': value,
            'unit': 'volts',
            'location': 'solar_panel',
            'timestamp': datetime.utcnow().isoformat() + 'Z'
        }

    def publish_reading(self, reading):
        topic = f"{self.topic_prefix}/{reading['location']}/{reading['sensor_type']}"
        payload = json.dumps(reading)

        self.client.publish(topic, payload)
        print(f"Published to {topic}: {reading['value']} {reading['unit']}")

    def run_simulation(self, duration_seconds=60, interval_seconds=3):
        print(f"\nStarting sensor simulation for {duration_seconds} seconds")
        print(f"Publishing every {interval_seconds} seconds")
        print("Press Ctrl+C to stop\n")

        start_time = time.time()
        sensor_publish_time = 0.3
        num_sensors = 5

        try:
            while time.time() - start_time < duration_seconds:
                self.publish_reading(self.simulate_ldr_reading())
                time.sleep(sensor_publish_time)

                self.publish_reading(self.simulate_current_reading())
                time.sleep(sensor_publish_time)

                self.publish_reading(self.simulate_temperature_reading())
                time.sleep(sensor_publish_time)

                self.publish_reading(self.simulate_humidity_reading())
                time.sleep(sensor_publish_time)

                self.publish_reading(self.simulate_voltage_reading())

                remaining_time = interval_seconds - (num_sensors * sensor_publish_time)
                if remaining_time > 0:
                    time.sleep(remaining_time)

        except KeyboardInterrupt:
            print("\n\nSimulation stopped by user")

def main():
    print("=" * 60)
    print("HyperVolt Sensor Simulator")
    print("=" * 60)

    BROKER_HOST = 'localhost'
    BROKER_PORT = 1883
    DURATION = 300
    INTERVAL = 3

    simulator = SensorSimulator(BROKER_HOST, BROKER_PORT)

    try:
        simulator.connect()
        simulator.run_simulation(DURATION, INTERVAL)
    except Exception as e:
        print(f"Error: {e}")
    finally:
        simulator.disconnect()

    print("\nSimulation complete!")

if __name__ == '__main__':
    main()
