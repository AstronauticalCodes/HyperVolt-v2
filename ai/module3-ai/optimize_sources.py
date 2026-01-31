
import numpy as np
import pandas as pd
from datetime import datetime
from typing import Dict, Tuple, List
from enum import Enum
import json
import os

class EnergySource(Enum):
    GRID = "grid"
    SOLAR = "solar"
    BATTERY = "battery"

class SourceOptimizer:

    PANEL_EFFICIENCY = 0.20
    PEAK_IRRADIANCE = 1000

    def __init__(self,
                 carbon_weight: float = 0.5,
                 cost_weight: float = 0.5,
                 solar_capacity: float = 3.0,
                 battery_capacity: float = 10.0,
                 battery_max_discharge: float = 2.0,
                 panel_efficiency: float = PANEL_EFFICIENCY):
        self.carbon_weight = carbon_weight
        self.cost_weight = cost_weight
        self.solar_capacity = solar_capacity
        self.battery_capacity = battery_capacity
        self.battery_max_discharge = battery_max_discharge
        self.battery_current_charge = battery_capacity * 0.8
        self.panel_efficiency = panel_efficiency

        self.battery_cycle_cost = 0.10
        self.solar_maintenance_cost = 0.05

        self.battery_degradation_cost_per_cycle = 5.0

    def get_dynamic_discharge_limit(self, potential_profit: float) -> float:
        if potential_profit > self.battery_degradation_cost_per_cycle * 2:
            return 0.10
        elif potential_profit > self.battery_degradation_cost_per_cycle:
            return 0.25
        else:
            return 0.40

    def calculate_solar_available(self,
                                   shortwave_radiation: float,
                                   cloud_cover: float,
                                   hour: int) -> float:
        if hour < 6 or hour >= 18:
            return 0.0

        panel_area = self.solar_capacity / (self.PEAK_IRRADIANCE / 1000 * self.panel_efficiency)

        solar_power_kw = (shortwave_radiation / 1000) * panel_area * self.panel_efficiency

        cloud_factor = 1 - (cloud_cover / 100) * 0.1

        solar_power = solar_power_kw * cloud_factor

        return max(0, min(solar_power, self.solar_capacity))

    def calculate_cost_score(self,
                            source: EnergySource,
                            power_needed: float,
                            grid_price: float) -> float:
        if source == EnergySource.GRID:
            return power_needed * grid_price
        elif source == EnergySource.SOLAR:
            return power_needed * self.solar_maintenance_cost
        elif source == EnergySource.BATTERY:
            return power_needed * self.battery_cycle_cost

        return 0.0

    def calculate_carbon_score(self,
                               source: EnergySource,
                               power_needed: float,
                               carbon_intensity: float) -> float:
        if source == EnergySource.GRID:
            return power_needed * carbon_intensity
        elif source == EnergySource.SOLAR:
            return power_needed * 50
        elif source == EnergySource.BATTERY:
            return power_needed * carbon_intensity * 0.8

        return 0.0

    def calculate_combined_score(self,
                                 cost_score: float,
                                 carbon_score: float) -> float:
        carbon_cost_equivalent = (carbon_score / 1000) * 10

        combined = (self.cost_weight * cost_score +
                   self.carbon_weight * carbon_cost_equivalent)

        return combined

    def optimize_source(self,
                       power_needed: float,
                       conditions: Dict) -> Tuple[List[Tuple[EnergySource, float]], Dict]:
        solar_available = self.calculate_solar_available(
            conditions.get('shortwave_radiation', conditions.get('solar_radiation', 0)),
            conditions['cloud_cover'],
            conditions['hour']
        )

        potential_profit = power_needed * (conditions['grid_price'] - self.battery_cycle_cost)
        discharge_limit = self.get_dynamic_discharge_limit(potential_profit)

        battery_available = min(
            self.battery_max_discharge,
            max(0, self.battery_current_charge - (self.battery_capacity * discharge_limit))
        )

        scores = {}
        for source in EnergySource:
            cost_score = self.calculate_cost_score(
                source, power_needed, conditions['grid_price']
            )
            carbon_score = self.calculate_carbon_score(
                source, power_needed, conditions['carbon_intensity']
            )
            combined_score = self.calculate_combined_score(cost_score, carbon_score)

            scores[source] = {
                'cost': cost_score,
                'carbon': carbon_score,
                'combined': combined_score
            }

        allocation = []
        remaining_power = power_needed

        if solar_available > 0 and remaining_power > 0:
            solar_used = min(solar_available, remaining_power)
            allocation.append((EnergySource.SOLAR, solar_used))
            remaining_power -= solar_used

        if remaining_power > 0:
            if (battery_available > 0 and
                scores[EnergySource.BATTERY]['combined'] < scores[EnergySource.GRID]['combined']):
                battery_used = min(battery_available, remaining_power)
                allocation.append((EnergySource.BATTERY, battery_used))
                remaining_power -= battery_used
                self.battery_current_charge -= battery_used

        if remaining_power > 0:
            allocation.append((EnergySource.GRID, remaining_power))

        actual_cost = sum([
            self.calculate_cost_score(source, power, conditions['grid_price'])
            for source, power in allocation
        ])

        actual_carbon = sum([
            self.calculate_carbon_score(source, power, conditions['carbon_intensity'])
            for source, power in allocation
        ])

        metrics = {
            'total_power': power_needed,
            'solar_available': solar_available,
            'battery_available': battery_available,
            'battery_discharge_limit': discharge_limit,
            'allocation': [(s.value, f"{p:.3f}") for s, p in allocation],
            'cost': actual_cost,
            'carbon': actual_carbon,
            'battery_charge': self.battery_current_charge,
            'scores': {k.value: v for k, v in scores.items()}
        }

        return allocation, metrics

    def charge_battery_from_solar(self, solar_excess: float):
        charge_amount = min(
            solar_excess,
            self.battery_capacity - self.battery_current_charge
        )
        self.battery_current_charge += charge_amount
        return charge_amount

    def simulate_day(self, df_day: pd.DataFrame) -> pd.DataFrame:
        results = []

        for idx, row in df_day.iterrows():
            power_needed = row['total_energy_kwh']

            conditions = {
                'shortwave_radiation': row.get('shortwave_radiation', row.get('solar_radiation_proxy', 0) * 800),
                'cloud_cover': row['cloud_cover'],
                'hour': row['hour'],
                'carbon_intensity': row['carbon_intensity'],
                'grid_price': row['grid_price_per_kwh']
            }

            allocation, metrics = self.optimize_source(power_needed, conditions)

            solar_available = metrics['solar_available']
            solar_used = sum([p for s, p in allocation if s == EnergySource.SOLAR])
            solar_excess = solar_available - solar_used

            if solar_excess > 0:
                charged = self.charge_battery_from_solar(solar_excess)
                metrics['battery_charged'] = charged
            else:
                metrics['battery_charged'] = 0

            results.append({
                'timestamp': row['timestamp'],
                'hour': row['hour'],
                'power_needed': power_needed,
                'allocation': metrics['allocation'],
                'cost': metrics['cost'],
                'carbon': metrics['carbon'],
                'battery_charge': metrics['battery_charge'],
                'battery_charged': metrics['battery_charged']
            })

        return pd.DataFrame(results)

def main():
    print("=" * 70)
    print("ENERGY SOURCE OPTIMIZATION - DEMONSTRATION")
    print("=" * 70)

    data_path = 'data/raw/integrated_dataset.csv'
    if not os.path.exists(data_path):
        print(f"Error: Dataset not found at {data_path}")
        return

    df = pd.read_csv(data_path)
    df['timestamp'] = pd.to_datetime(df['timestamp'])

    optimizer = SourceOptimizer(
        carbon_weight=0.5,
        cost_weight=0.5,
        solar_capacity=3.0,
        battery_capacity=10.0,
        battery_max_discharge=2.0
    )

    print("\nSimulating optimal source selection for one day...")
    df_day = df.head(24)
    results = optimizer.simulate_day(df_day)

    print("\n" + "=" * 70)
    print("HOURLY OPTIMIZATION RESULTS")
    print("=" * 70)

    for idx, row in results.iterrows():
        print(f"\nHour {row['hour']:02d}:00")
        print(f"  Power needed: {row['power_needed']:.3f} kW")
        print(f"  Sources: {row['allocation']}")
        print(f"  Cost: ₹{row['cost']:.2f}")
        print(f"  Carbon: {row['carbon']:.0f} gCO2eq")
        print(f"  Battery: {row['battery_charge']:.2f} kWh", end="")
        if row['battery_charged'] > 0:
            print(f" (+{row['battery_charged']:.2f} kWh charged)")
        else:
            print()

    print("\n" + "=" * 70)
    print("DAILY SUMMARY")
    print("=" * 70)

    total_cost = results['cost'].sum()
    total_carbon = results['carbon'].sum()

    grid_only_cost = (df_day['total_energy_kwh'] * df_day['grid_price_per_kwh']).sum()
    grid_only_carbon = (df_day['total_energy_kwh'] * df_day['carbon_intensity']).sum()

    print(f"\nWith Optimization:")
    print(f"  Total Cost:   ₹{total_cost:.2f}")
    print(f"  Total Carbon: {total_carbon/1000:.2f} kg CO2")

    print(f"\nGrid Only (No Optimization):")
    print(f"  Total Cost:   ₹{grid_only_cost:.2f}")
    print(f"  Total Carbon: {grid_only_carbon/1000:.2f} kg CO2")

    print(f"\nSavings:")
    print(f"  Cost Saved:   ₹{grid_only_cost - total_cost:.2f} ({(1 - total_cost/grid_only_cost)*100:.1f}%)")
    print(f"  Carbon Saved: {(grid_only_carbon - total_carbon)/1000:.2f} kg CO2 ({(1 - total_carbon/grid_only_carbon)*100:.1f}%)")

    output_path = 'data/optimization_results.csv'
    results.to_csv(output_path, index=False)
    print(f"\n✓ Results saved to: {output_path}")

    config = {
        'carbon_weight': optimizer.carbon_weight,
        'cost_weight': optimizer.cost_weight,
        'solar_capacity': optimizer.solar_capacity,
        'battery_capacity': optimizer.battery_capacity,
        'battery_max_discharge': optimizer.battery_max_discharge,
        'simulation_date': datetime.now().isoformat()
    }

    config_path = 'models/optimizer_config.json'
    os.makedirs('models', exist_ok=True)
    with open(config_path, 'w') as f:
        json.dump(config, f, indent=2)

    print(f"✓ Configuration saved to: {config_path}")

    print("\n" + "=" * 70)
    print("✓ OPTIMIZATION DEMONSTRATION COMPLETE!")
    print("=" * 70)

if __name__ == "__main__":
    main()
