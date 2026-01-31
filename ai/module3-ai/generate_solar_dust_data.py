
import os
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict

class SolarDustDataGenerator:

    def __init__(self, solar_capacity: float = 3.0):
        self.solar_capacity = solar_capacity
        self.panel_area = 20

    def calculate_expected_power(self,
                                 irradiance: float,
                                 temperature: float,
                                 hour: int) -> float:
        if hour < 6 or hour >= 18:
            return 0.0

        base_power = self.solar_capacity * irradiance

        temp_factor = 1.0 - 0.005 * max(0, temperature - 25)

        optimal_hour = 12
        angle_factor = 1.0 - 0.3 * abs(hour - optimal_hour) / 6
        angle_factor = max(0.5, angle_factor)

        expected_power = base_power * temp_factor * angle_factor

        return max(0, expected_power)

    def simulate_dust_accumulation(self, days: int = 30) -> float:

        max_dust = 80
        growth_rate = 0.3

        dust_pct = max_dust / (1 + np.exp(-growth_rate * (days - 10)))

        dust_pct += np.random.normal(0, 5)

        return np.clip(dust_pct, 0, 100)

    def calculate_actual_power(self,
                               expected_power: float,
                               dust_percentage: float) -> float:
        efficiency_loss = dust_percentage * 0.007

        actual_power = expected_power * (1 - efficiency_loss)

        actual_power += np.random.normal(0, 0.02)

        return max(0, actual_power)

    def generate_solar_dust_dataset(self, days: int = 30) -> pd.DataFrame:
        print(f"Generating solar panel dust accumulation data for {days} days...")

        all_dates = pd.date_range(
            end=datetime.now(),
            periods=days * 24 * 12,
            freq='5min'
        )

        daylight_mask = (all_dates.hour >= 6) & (all_dates.hour < 18)
        dates = all_dates[daylight_mask]

        hours = dates.hour.values
        day_of_series = np.arange(len(dates)) / (12 * 12)

        hour_angle = (hours - 12) / 6
        irradiance = np.exp(-(hour_angle ** 2) / 0.5)
        irradiance += np.random.normal(0, 0.05, len(dates))
        irradiance = np.clip(irradiance, 0, 1)

        temp_base = 28 + 3 * np.sin(2 * np.pi * day_of_series)
        temp_daily = 5 * np.sin(2 * np.pi * (hours - 10) / 12)
        temperature = temp_base + temp_daily + np.random.normal(0, 1, len(dates))

        ldr_raw = (irradiance * 1023).astype(int)
        ldr_lux = irradiance * 1000

        cleaning_schedule = []
        next_cleaning = np.random.uniform(10, 15)
        current_days = 0

        days_since_cleaning = []
        for i, day in enumerate(day_of_series):
            if day >= next_cleaning:
                current_days = 0
                next_cleaning = day + np.random.uniform(10, 15)
            else:
                current_days = day - (next_cleaning - np.random.uniform(10, 15))

            days_since_cleaning.append(max(0, current_days))

        days_since_cleaning = np.array(days_since_cleaning)

        dust_percentage = np.array([
            self.simulate_dust_accumulation(days)
            for days in days_since_cleaning
        ])

        expected_power = np.array([
            self.calculate_expected_power(irr, temp, hour)
            for irr, temp, hour in zip(irradiance, temperature, hours)
        ])

        actual_power = np.array([
            self.calculate_actual_power(exp_pwr, dust_pct)
            for exp_pwr, dust_pct in zip(expected_power, dust_percentage)
        ])

        efficiency_ratio = np.where(
            expected_power > 0.1,
            actual_power / expected_power,
            1.0
        )

        power_loss_kw = expected_power - actual_power

        revenue_loss_per_hour = power_loss_kw * 6

        df = pd.DataFrame({
            'timestamp': dates,
            'hour': hours,
            'days_since_cleaning': days_since_cleaning,
            'solar_irradiance': irradiance,
            'temperature_c': temperature,
            'ldr_raw': ldr_raw,
            'ldr_lux': ldr_lux,
            'expected_power_kw': expected_power,
            'actual_power_kw': actual_power,
            'power_loss_kw': power_loss_kw,
            'efficiency_ratio': efficiency_ratio,
            'dust_percentage': dust_percentage,
            'revenue_loss_per_hour': revenue_loss_per_hour,
            'needs_cleaning': dust_percentage > 40
        })

        df['cumulative_power_loss_kwh'] = df['power_loss_kw'].cumsum() * (5/60)
        df['cumulative_revenue_loss'] = df['cumulative_power_loss_kwh'] * 6

        return df

    def save_to_csv(self, data: pd.DataFrame, filename: str):
        output_path = f"data/raw/{filename}"
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        data.to_csv(output_path, index=False)
        print(f"Solar dust data saved to {output_path}")
        return output_path

def main():
    print("=" * 70)
    print("SOLAR PANEL DUST ACCUMULATION - DATASET GENERATION")
    print("=" * 70)

    generator = SolarDustDataGenerator(solar_capacity=3.0)

    solar_dust_data = generator.generate_solar_dust_dataset(days=30)

    output_path = generator.save_to_csv(solar_dust_data, 'solar_dust_data.csv')

    print("\n" + "=" * 70)
    print("DATASET STATISTICS")
    print("=" * 70)

    print(f"\n📊 Dataset Overview:")
    print(f"  Total records: {len(solar_dust_data):,}")
    print(f"  Time span: {solar_dust_data['timestamp'].min()} to {solar_dust_data['timestamp'].max()}")
    print(f"  Daylight hours only: 6 AM - 6 PM")

    print(f"\n☀️ Solar Panel Performance:")
    print(f"  Average irradiance: {solar_dust_data['solar_irradiance'].mean():.2f}")
    print(f"  Average expected power: {solar_dust_data['expected_power_kw'].mean():.3f} kW")
    print(f"  Average actual power: {solar_dust_data['actual_power_kw'].mean():.3f} kW")
    print(f"  Average efficiency: {solar_dust_data['efficiency_ratio'].mean():.2%}")

    print(f"\n🌫️ Dust Accumulation:")
    print(f"  Average dust level: {solar_dust_data['dust_percentage'].mean():.1f}%")
    print(f"  Max dust level: {solar_dust_data['dust_percentage'].max():.1f}%")
    print(f"  Times needs cleaning: {solar_dust_data['needs_cleaning'].sum():,} ({solar_dust_data['needs_cleaning'].mean():.1%})")

    print(f"\n💰 Economic Impact:")
    print(f"  Average power loss: {solar_dust_data['power_loss_kw'].mean():.3f} kW")
    print(f"  Total power loss (30 days): {solar_dust_data['cumulative_power_loss_kwh'].iloc[-1]:.2f} kWh")
    print(f"  Total revenue loss: ₹{solar_dust_data['cumulative_revenue_loss'].iloc[-1]:.2f}")
    print(f"  Average hourly loss: ₹{solar_dust_data['revenue_loss_per_hour'].mean():.2f}")

    print("\n" + "=" * 70)
    print("✓ DATASET GENERATION COMPLETE!")
    print("=" * 70)
    print("\nDataset saved with features:")
    print("  - Solar irradiance and temperature")
    print("  - LDR readings (raw and lux)")
    print("  - Expected vs actual power output")
    print("  - Dust accumulation percentage")
    print("  - Days since last cleaning")
    print("  - Economic impact metrics")
    print("\nReady for training dust prediction model!")

if __name__ == "__main__":
    main()
