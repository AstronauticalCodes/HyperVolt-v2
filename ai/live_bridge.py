import requests
import pandas as pd
import sys
import os

sys.path.append(os.path.join(os.getcwd(), 'engine', 'ai'))
from optimize_sources import SourceOptimizer, EnergySource

MAC_IP = "192.168.1.5"
API_URL = f"http://{MAC_IP}:8000/api"

def get_live_data():
    try:
        grid_resp = requests.get(f"{API_URL}/grid-data/weather/?hours=24")
        grid_data = grid_resp.json()

        sensor_resp = requests.get(f"{API_URL}/sensor-readings/latest/")
        sensor_data = sensor_resp.json()

        print("✓ Connected to Mac Backend")
        return grid_data, sensor_data
    except Exception as e:
        print(f"✗ Connection failed: {e}")
        return None, None

def run_optimization():
    optimizer = SourceOptimizer(
        carbon_weight=0.5,
        cost_weight=0.5,
        solar_capacity=3.0,
        battery_capacity=10.0
    )

    print("\n--- FETCHING LIVE CONTEXT ---")
    grid, sensors = get_live_data()

    if not grid or not sensors:
        return

    current_carbon = grid.get('carbon_intensity', 450)
    current_solar = grid.get('solar_radiation', 0.8)
    current_power_need = 1.5

    conditions = {
        'solar_radiation': current_solar,
        'cloud_cover': 10,
        'hour': 14,
        'carbon_intensity': current_carbon,
        'grid_price': 12.0
    }

    print(f"Current Conditions: Carbon={current_carbon}g | Power Need={current_power_need}kW")

    allocation, metrics = optimizer.optimize_source(current_power_need, conditions)

    print("\n--- AI DECISION ---")
    print(f"Sources Selected: {allocation}")
    print(f"Cost: ₹{metrics['cost']:.2f}")
    print(f"Carbon: {metrics['carbon']:.2f}g")

if __name__ == "__main__":
    run_optimization()