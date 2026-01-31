
import os
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List, Tuple
import json

import sys
sys.path.append(os.path.dirname(__file__))
from train_demand_model import EnergyDemandForecaster
from optimize_sources import SourceOptimizer, EnergySource

class LoadType:
    CRITICAL = "critical"
    DEFERRABLE = "deferrable"

class LoadManager:

    DEFAULT_CARBON_THRESHOLD = 700
    CLEAN_CARBON_BASELINE = 400
    NORMAL_GRID_PRICE = 5.0

    def __init__(self, carbon_threshold: float = DEFAULT_CARBON_THRESHOLD):
        self.carbon_threshold = carbon_threshold

        self.loads = {
            'lights': {'type': LoadType.CRITICAL, 'power_kw': 0.2},
            'router': {'type': LoadType.CRITICAL, 'power_kw': 0.05},
            'refrigerator': {'type': LoadType.CRITICAL, 'power_kw': 0.15},
            'washing_machine': {'type': LoadType.DEFERRABLE, 'power_kw': 1.5},
            'ev_charger': {'type': LoadType.DEFERRABLE, 'power_kw': 3.0},
            'air_conditioner': {'type': LoadType.DEFERRABLE, 'power_kw': 2.0},
            'dishwasher': {'type': LoadType.DEFERRABLE, 'power_kw': 1.2}
        }

    def should_defer_load(self, load_name: str, carbon_intensity: float, grid_price: float) -> Dict:
        if load_name not in self.loads:
            return {'defer': False, 'reason': 'Unknown load'}

        load = self.loads[load_name]

        if load['type'] == LoadType.CRITICAL:
            return {
                'defer': False,
                'reason': 'Critical load - cannot defer',
                'load_type': LoadType.CRITICAL
            }

        if carbon_intensity > self.carbon_threshold:
            return {
                'defer': True,
                'reason': f'High carbon intensity ({carbon_intensity:.0f} gCO2eq/kWh) - defer until cleaner',
                'load_type': LoadType.DEFERRABLE,
                'carbon_savings': load['power_kw'] * (carbon_intensity - self.CLEAN_CARBON_BASELINE)
            }

        if grid_price > 8.0:
            return {
                'defer': True,
                'reason': f'High grid price (₹{grid_price:.2f}/kWh) - defer until cheaper',
                'load_type': LoadType.DEFERRABLE,
                'cost_savings': load['power_kw'] * (grid_price - self.NORMAL_GRID_PRICE)
            }

        return {
            'defer': False,
            'reason': 'Good conditions - proceed with load',
            'load_type': LoadType.DEFERRABLE
        }

    def get_load_shedding_recommendation(self, carbon_intensity: float, grid_price: float) -> Dict:
        recommendations = {}
        total_deferred_power = 0
        total_carbon_saved = 0

        for load_name in self.loads:
            decision = self.should_defer_load(load_name, carbon_intensity, grid_price)
            recommendations[load_name] = decision

            if decision['defer']:
                total_deferred_power += self.loads[load_name]['power_kw']
                if 'carbon_savings' in decision:
                    total_carbon_saved += decision['carbon_savings']

        return {
            'recommendations': recommendations,
            'total_deferred_power_kw': total_deferred_power,
            'total_carbon_saved_g': total_carbon_saved,
            'summary': f"Defer {total_deferred_power:.1f} kW to save {total_carbon_saved:.0f}g CO2" if total_deferred_power > 0 else "All loads can proceed"
        }

class VestaDecisionEngine:

    def __init__(self):
        self.forecaster = EnergyDemandForecaster(lookback_hours=24, forecast_horizon=6)
        self.optimizer = SourceOptimizer(
            carbon_weight=0.5,
            cost_weight=0.5,
            solar_capacity=3.0,
            battery_capacity=10.0,
            battery_max_discharge=2.0
        )
        self.load_manager = LoadManager(carbon_threshold=700)
        self.decision_log = []

    def load_models(self) -> bool:
        print("Loading pre-trained models...")
        success = self.forecaster.load_model()
        if success:
            print("✓ Demand forecasting model loaded")
        else:
            print("✗ No pre-trained forecasting model found")
        return success

    def train_models(self, data_path: str = 'data/raw/integrated_dataset.csv'):
        print("=" * 70)
        print("VESTA DECISION ENGINE - MODEL TRAINING")
        print("=" * 70)

        df = pd.read_csv(data_path)
        df['timestamp'] = pd.to_datetime(df['timestamp'])

        print(f"\nDataset: {len(df)} records")
        print(f"Date range: {df['timestamp'].min()} to {df['timestamp'].max()}")

        print("\n" + "-" * 70)
        print("PHASE 1: Training Demand Forecasting Model")
        print("-" * 70)
        self.forecaster.train(df, epochs=50, batch_size=32)

        print("\n" + "-" * 70)
        print("PHASE 2: Source Optimization Algorithm")
        print("-" * 70)
        print("✓ Optimization algorithm initialized (rule-based, no training needed)")

        print("\n" + "=" * 70)
        print("✓ ALL MODELS READY!")
        print("=" * 70)

    def retrain_on_new_data(self, new_data_path: str):
        print("=" * 70)
        print("RETRAINING MODELS ON NEW DATA")
        print("=" * 70)

        print("\nRetraining demand forecasting model...")
        self.forecaster.retrain(new_data_path, epochs=20)

        print("\n✓ Models updated with new data!")

    def make_decision(self, recent_data: pd.DataFrame, current_conditions: Dict) -> Dict:
        forecast = self.forecaster.predict(recent_data)

        current_power_needed = forecast[0]

        grid_price = current_conditions.get('grid_price', 6.0)
        battery_level = self.optimizer.battery_current_charge
        battery_pct = (battery_level / self.optimizer.battery_capacity) * 100

        high_price_threshold = 8.0
        low_price_threshold = 4.0

        grid_action = None
        grid_revenue = 0.0

        if grid_price > high_price_threshold and battery_pct > 80:
            sellable_power = min(
                self.optimizer.battery_max_discharge,
                battery_level - (self.optimizer.battery_capacity * 0.5)
            )
            if sellable_power > 0:
                grid_action = "DISCHARGE_TO_GRID"
                grid_revenue = sellable_power * grid_price
                self.optimizer.battery_current_charge -= sellable_power

        elif grid_price < low_price_threshold and battery_pct < 60:
            charge_amount = min(
                2.0,
                self.optimizer.battery_capacity - battery_level
            )
            if charge_amount > 0:
                grid_action = "CHARGE_FROM_GRID"
                grid_revenue = -charge_amount * grid_price
                self.optimizer.battery_current_charge += charge_amount

        allocation, metrics = self.optimizer.optimize_source(
            current_power_needed,
            current_conditions
        )

        load_recommendations = self.load_manager.get_load_shedding_recommendation(
            current_conditions.get('carbon_intensity', 500),
            grid_price
        )

        decision = {
            'timestamp': datetime.now().isoformat(),
            'forecast_6h': forecast.tolist(),
            'current_hour': {
                'predicted_demand': float(current_power_needed),
                'source_allocation': [(s.value, float(p)) for s, p in allocation],
                'cost': float(metrics['cost']),
                'carbon': float(metrics['carbon']),
                'battery_charge': float(metrics['battery_charge']),
                'grid_action': grid_action,
                'grid_revenue': float(grid_revenue)
            },
            'load_shedding': load_recommendations,
            'recommendation': self._generate_recommendation(forecast, allocation, metrics, grid_action, grid_revenue, load_recommendations)
        }

        self.decision_log.append(decision)

        return decision

    def _generate_recommendation(self, forecast: np.ndarray,
                                 allocation: List[Tuple[EnergySource, float]],
                                 metrics: Dict,
                                 grid_action: str = None,
                                 grid_revenue: float = 0.0,
                                 load_recommendations: Dict = None) -> str:
        sources = [s.value for s, _ in allocation]

        rec = []

        if grid_action == "DISCHARGE_TO_GRID":
            rec.append(f"💰 SELLING to grid! Revenue: ₹{grid_revenue:.2f}")
        elif grid_action == "CHARGE_FROM_GRID":
            rec.append(f"🔌 BUYING from grid (low price). Cost: ₹{abs(grid_revenue):.2f}")

        if load_recommendations and load_recommendations['total_deferred_power_kw'] > 0:
            rec.append(f"⚡ Load Shedding: {load_recommendations['summary']}")

        if EnergySource.SOLAR in [s for s, _ in allocation]:
            rec.append("Using solar power (cleanest option)")
        if EnergySource.BATTERY in [s for s, _ in allocation]:
            rec.append("Drawing from battery (cost-effective)")
        if EnergySource.GRID in [s for s, _ in allocation]:
            rec.append("Supplementing with grid power")

        avg_demand = forecast.mean()
        if forecast[1] > forecast[0] * 1.2:
            rec.append("⚠ Demand will increase significantly in next hour")

        battery_pct = (metrics['battery_charge'] / self.optimizer.battery_capacity) * 100
        if battery_pct < 20:
            rec.append("⚠ Battery low - consider charging during low-cost hours")
        elif battery_pct > 80:
            rec.append("✓ Battery well charged")

        return " | ".join(rec)

    def simulate_realtime(self, df: pd.DataFrame, hours: int = 24) -> pd.DataFrame:
        print("=" * 70)
        print(f"SIMULATING REAL-TIME OPERATION ({hours} hours)")
        print("=" * 70)

        decisions = []

        for i in range(24, min(24 + hours, len(df))):
            recent_data = df.iloc[i-24:i].copy()

            current = df.iloc[i]
            conditions = {
                'shortwave_radiation': current.get('shortwave_radiation', current.get('solar_radiation_proxy', 0) * 800),
                'cloud_cover': current['cloud_cover'],
                'hour': current['hour'],
                'carbon_intensity': current['carbon_intensity'],
                'grid_price': current['grid_price_per_kwh']
            }

            decision = self.make_decision(recent_data, conditions)

            decision['actual_demand'] = float(current['total_energy_kwh'])
            decision['timestamp_hour'] = current['timestamp']

            decisions.append(decision)

            if (i - 24) % 6 == 0:
                print(f"  Processed hour {i-24}/{hours}")

        print("\n✓ Simulation complete!")

        results = []
        for d in decisions:
            results.append({
                'timestamp': d['timestamp_hour'],
                'predicted_demand': d['current_hour']['predicted_demand'],
                'actual_demand': d['actual_demand'],
                'sources': str(d['current_hour']['source_allocation']),
                'cost': d['current_hour']['cost'],
                'carbon': d['current_hour']['carbon'],
                'battery_charge': d['current_hour']['battery_charge'],
                'recommendation': d['recommendation']
            })

        return pd.DataFrame(results)

    def save_decision_log(self, path: str = 'data/decision_log.json'):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w') as f:
            json.dump(self.decision_log, f, indent=2)
        print(f"✓ Decision log saved to: {path}")

def main():
    engine = VestaDecisionEngine()

    if not engine.load_models():
        print("\nNo pre-trained models found. Training new models...")
        engine.train_models()

    data_path = 'data/raw/integrated_dataset.csv'
    df = pd.read_csv(data_path)
    df['timestamp'] = pd.to_datetime(df['timestamp'])

    print("\n" + "=" * 70)
    print("REAL-TIME SIMULATION")
    print("=" * 70)

    results = engine.simulate_realtime(df, hours=48)

    print("\n" + "=" * 70)
    print("SIMULATION RESULTS")
    print("=" * 70)

    print(f"\nForecast Accuracy:")
    mae = np.abs(results['predicted_demand'] - results['actual_demand']).mean()
    mape = (np.abs(results['predicted_demand'] - results['actual_demand']) / results['actual_demand']).mean() * 100
    print(f"  Mean Absolute Error: {mae:.3f} kWh")
    print(f"  Mean Absolute % Error: {mape:.1f}%")

    print(f"\nCost & Carbon:")
    print(f"  Total Cost: ₹{results['cost'].sum():.2f}")
    print(f"  Total Carbon: {results['carbon'].sum()/1000:.2f} kg CO2")
    print(f"  Average Cost per hour: ₹{results['cost'].mean():.2f}")

    print(f"\nBattery Usage:")
    print(f"  Initial charge: {results['battery_charge'].iloc[0]:.2f} kWh")
    print(f"  Final charge: {results['battery_charge'].iloc[-1]:.2f} kWh")
    print(f"  Min charge: {results['battery_charge'].min():.2f} kWh")
    print(f"  Max charge: {results['battery_charge'].max():.2f} kWh")

    output_path = 'data/simulation_results.csv'
    results.to_csv(output_path, index=False)
    print(f"\n✓ Simulation results saved to: {output_path}")

    engine.save_decision_log()

    print("\n" + "=" * 70)
    print("✓ VESTA DECISION ENGINE READY FOR DEPLOYMENT!")
    print("=" * 70)
    print("\nThe engine can now:")
    print("  1. Predict energy demand 6 hours ahead")
    print("  2. Optimize source selection (Grid/Solar/Battery)")
    print("  3. Minimize both cost and carbon footprint")
    print("  4. Adapt to new data through retraining")

    print("\n" + "-" * 70)
    print("RETRAINING CAPABILITY")
    print("-" * 70)
    print("\nTo retrain the model on new data:")
    print("  1. Collect new data (e.g., next 7 days)")
    print("  2. Save to CSV with same format as training data")
    print("  3. Run: engine.retrain_on_new_data('path/to/new_data.csv')")
    print("\nThis allows the system to adapt to:")
    print("  - Seasonal changes")
    print("  - New usage patterns")
    print("  - Updated appliances")
    print("  - Grid conditions")

if __name__ == "__main__":
    main()
