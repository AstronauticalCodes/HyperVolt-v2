
import os
import sys
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import json
from django.conf import settings
from django.utils import timezone
import paho.mqtt.publish as publish
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

AI_MODULE_PATH = os.path.join(settings.BASE_DIR, '..', 'ai', 'module3-ai')
sys.path.insert(0, AI_MODULE_PATH)

try:
    from train_demand_model import EnergyDemandForecaster
    from optimize_sources import SourceOptimizer, EnergySource
    AI_AVAILABLE = True
except ImportError as e:
    print(f"Warning: AI modules not available: {e}")
    AI_AVAILABLE = False

class AIInferenceService:

    USE_SIMULATION_FILE = False
    SIMULATION_FILE_PATH = os.path.join(settings.BASE_DIR, 'data', 'simulation_sensors.csv')

    def __init__(self):
        self.forecaster = None
        self.optimizer = None
        self.models_loaded = False

        if AI_AVAILABLE:
            self._initialize_models()

    def _initialize_models(self):
        try:
            ai_models_dir = os.path.abspath(os.path.join(settings.BASE_DIR, '..', 'ai', 'models'))

            model_path = os.path.join(ai_models_dir, 'demand_forecaster.h5')
            scaler_path = os.path.join(ai_models_dir, 'demand_forecaster_scalers.pkl')

            self.forecaster = EnergyDemandForecaster(lookback_hours=24, forecast_horizon=6)

            if os.path.exists(model_path) and os.path.exists(scaler_path):
                print(f"Loading AI model from: {model_path}")
                self.forecaster.model_path = model_path
                self.forecaster.load_model()
                self.models_loaded = True
            else:
                print(f"Warning: Model files not found in {ai_models_dir}")
                print("Please run 'python ai/module3-ai/train_demand_model.py' first.")
                self.models_loaded = False

            self.optimizer = SourceOptimizer(
                carbon_weight=0.5, cost_weight=0.5,
                solar_capacity=3.0, battery_capacity=10.0
            )

        except Exception as e:
            print(f"Error initializing AI models: {e}")
            self.models_loaded = False

    def is_available(self) -> bool:
        return AI_AVAILABLE and self.models_loaded

    def _update_optimizer_weights(self):
        if not self.optimizer:
            return

        try:
            from ..models import UserPreferences

            cost_weight = 0.5
            carbon_weight = 0.5

            cost_pref = UserPreferences.objects.filter(preference_key='cost_priority').first()
            if cost_pref:
                cost_value = cost_pref.preference_value
                if isinstance(cost_value, (int, float)):
                    cost_weight = float(cost_value) / 100.0
                elif isinstance(cost_value, str):
                    cost_weight = float(cost_value) / 100.0
                carbon_weight = 1.0 - cost_weight

            self.optimizer.cost_weight = cost_weight
            self.optimizer.carbon_weight = carbon_weight

        except Exception as e:
            print(f"Error updating weights: {e}")

    def forecast_demand(self, hours_ahead: int = 6) -> Dict:
        if not self.is_available():
            return {
                'error': 'AI models not available',
                'available': False
            }

        try:
            recent_data = self._get_recent_data_for_forecasting()

            if recent_data is None or len(recent_data) < 24:
                return {
                    'error': 'Insufficient historical data (need at least 24 hours)',
                    'available': False
                }

            forecast = self.forecaster.predict(recent_data)

            return {
                'timestamp': timezone.now().isoformat(),
                'forecast_horizon': hours_ahead,
                'predictions': [
                    {
                        'hour': i + 1,
                        'predicted_kwh': float(forecast[i]),
                        'timestamp': (timezone.now() + timedelta(hours=i+1)).isoformat()
                    }
                    for i in range(min(hours_ahead, len(forecast)))
                ],
                'available': True,
                'model_type': 'lstm'
            }

        except Exception as e:
            return {
                'error': f'Forecasting failed: {str(e)}',
                'available': False
            }

    def recommend_source(self, load_name: str, load_priority: int,
                        load_power: float, current_conditions: Optional[Dict] = None) -> Dict:
        if not self.is_available():
            return {
                'error': 'AI models not available',
                'available': False,
                'fallback': 'Use rule-based optimizer from EnergySourceOptimizer'
            }

        try:
            self._update_optimizer_weights()

            if current_conditions is None:
                current_conditions = self._get_current_conditions()

            power_kw = load_power / 1000.0

            allocation, metrics = self.optimizer.optimize_source(
                power_kw,
                current_conditions
            )

            primary_source = allocation[0][0].value if allocation else 'grid'

            reasoning = self._build_reasoning(allocation, current_conditions, load_name)

            return {
                'timestamp': timezone.now().isoformat(),
                'load_name': load_name,
                'load_priority': load_priority,
                'load_power': load_power,
                'recommended_source': primary_source,
                'source_allocation': [(s.value, float(p)) for s, p in allocation],
                'metrics': {
                    'estimated_cost': float(metrics['cost']),
                    'estimated_carbon': float(metrics['carbon']),
                    'battery_charge': float(metrics['battery_charge'])
                },
                'reasoning': reasoning,
                'confidence': 0.85,
                'algorithm': 'ml_optimizer',
                'available': True
            }

        except Exception as e:
            return {
                'error': f'Source recommendation failed: {str(e)}',
                'available': False
            }

    def make_decision(self) -> Dict:
        if not self.is_available():
            return {
                'error': 'AI models not available',
                'available': False
            }

        try:
            self._update_optimizer_weights()

            forecast_result = self.forecast_demand()

            if not forecast_result.get('available'):
                return forecast_result

            conditions = self._get_current_conditions()

            next_hour_demand = forecast_result['predictions'][0]['predicted_kwh']

            allocation, metrics = self.optimizer.optimize_source(
                next_hour_demand,
                conditions
            )

            decision = {
                'timestamp': timezone.now().isoformat(),
                'forecast': forecast_result['predictions'],
                'current_decision': {
                    'predicted_demand_kwh': float(next_hour_demand),
                    'source_allocation': [(s.value, float(p)) for s, p in allocation],
                    'cost': float(metrics['cost']),
                    'carbon': float(metrics['carbon']),
                    'battery_charge': float(metrics['battery_charge'])
                },
                'recommendation': self._generate_recommendation(
                    forecast_result['predictions'],
                    allocation,
                    metrics
                ),
                'available': True
            }

            self._publish_decision_to_mqtt(decision['current_decision'])

            return decision

        except Exception as e:
            return {
                'error': f'Decision making failed: {str(e)}',
                'available': False
            }

    def _publish_decision_to_mqtt(self, decision_data: Dict):
        try:
            allocations = decision_data.get('source_allocation', [])
            if not allocations:
                return

            primary_source = allocations[0][0]

            payload = {
                'command': 'switch_source',
                'source': primary_source,
                'details': decision_data,
                'timestamp': timezone.now().isoformat()
            }

            publish.single(
                "HyperVolt/commands/control",
                payload=json.dumps(payload),
                hostname="localhost",
                port=1883
            )
            print(f"✓ Published AI decision to MQTT: {primary_source}")

            channel_layer = get_channel_layer()
            async_to_sync(channel_layer.group_send)(
                "sensors",
                {
                    "type": "sensor.update",
                    "data": {
                        "type": "ai_decision",
                        "payload": payload
                    }
                }
            )
            print(f"✓ Broadcasted AI decision to Frontend")

        except Exception as e:
            print(f"Failed to publish AI decision: {e}")

    def trigger_retraining(self) -> Dict:
        if not self.is_available():
            return {'success': False, 'error': 'AI Module not loaded'}

        try:
            csv_path = self._export_db_to_csv()

            if not csv_path:
                return {'success': False, 'error': 'Failed to export data for training'}

            try:
                from decision_engine import VestaDecisionEngine
                engine = VestaDecisionEngine()

                engine.retrain_on_new_data(csv_path)

                self.forecaster.load_model()

                return {'success': True, 'message': 'Model retrained and reloaded'}
            except ImportError:
                return {'success': False, 'error': 'VestaDecisionEngine not available'}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def _export_db_to_csv(self) -> Optional[str]:
        try:
            from ..models import SensorReading, GridData

            export_dir = os.path.join(settings.BASE_DIR, '..', 'ai', 'data', 'raw')
            os.makedirs(export_dir, exist_ok=True)

            csv_path = os.path.join(export_dir, 'latest_training.csv')

            end_time = timezone.now()
            start_time = end_time - timedelta(days=30)

            sensor_readings = SensorReading.objects.filter(
                timestamp__gte=start_time,
                timestamp__lte=end_time
            ).values('timestamp', 'sensor_type', 'value')

            if not sensor_readings:
                return None

            df = pd.DataFrame(list(sensor_readings))

            df['timestamp'] = pd.to_datetime(df['timestamp'])
            df['hour_key'] = df['timestamp'].dt.floor('H')

            df_pivot = df.pivot_table(
                index='hour_key',
                columns='sensor_type',
                values='value',
                aggfunc='mean'
            ).reset_index()

            df_pivot['hour'] = df_pivot['hour_key'].dt.hour
            df_pivot['day_of_week'] = df_pivot['hour_key'].dt.dayofweek
            df_pivot['is_weekend'] = df_pivot['day_of_week'] >= 5

            df_pivot.to_csv(csv_path, index=False)

            return csv_path

        except Exception as e:
            print(f"Error exporting data to CSV: {e}")
            return None

    def _get_recent_data_for_forecasting(self) -> Optional[pd.DataFrame]:
        try:
            from ..models import SensorReading

            end_time = timezone.now()
            start_time = end_time - timedelta(hours=24)

            readings = SensorReading.objects.filter(
                timestamp__gte=start_time,
                timestamp__lte=end_time
            ).values('timestamp', 'sensor_type', 'value')

            if not readings:
                return None

            df_raw = pd.DataFrame(list(readings))

            df_raw['timestamp'] = pd.to_datetime(df_raw['timestamp'])
            df_raw['hour_key'] = df_raw['timestamp'].dt.floor('H')

            df_pivot = df_raw.pivot_table(
                index='hour_key',
                columns='sensor_type',
                values='value',
                aggfunc='mean'
            ).reset_index()

            column_map = {
                'temperature': 'temperature',
                'humidity': 'humidity',
                'ldr': 'solar_radiation_proxy',
                'current': 'total_energy_kwh'
            }
            df_pivot.rename(columns=column_map, inplace=True)

            required_cols = ['temperature', 'total_energy_kwh', 'solar_radiation_proxy']
            for col in required_cols:
                if col not in df_pivot.columns:
                    df_pivot[col] = 0.0

            df_pivot['hour'] = df_pivot['hour_key'].dt.hour
            df_pivot['day_of_week'] = df_pivot['hour_key'].dt.dayofweek
            df_pivot['is_weekend'] = df_pivot['day_of_week'] >= 5

            df_pivot['cloud_cover'] = 30.0
            df_pivot['carbon_intensity'] = 450.0
            df_pivot['grid_price'] = 6.0

            df_final = df_pivot.sort_values('hour_key').tail(24)

            return df_final if len(df_final) >= 12 else None

        except Exception as e:
            print(f"Error fetching historical data: {e}")
            return None

    def _get_current_conditions(self) -> Dict:
        try:
            if self.USE_SIMULATION_FILE:
                return self._read_conditions_from_file()

            else:
                return self._read_conditions_from_db()

        except Exception as e:
            print(f"Error fetching conditions: {e}")
            return self._get_fallback_conditions()

    def _read_conditions_from_file(self) -> Dict:
        if not os.path.exists(self.SIMULATION_FILE_PATH):
            print("Simulation file not found, using fallback.")
            return self._get_fallback_conditions()

        try:
            df = pd.read_csv(self.SIMULATION_FILE_PATH)

            sensors = dict(zip(df['sensor_type'], df['value']))

            conditions = {
                'hour': timezone.now().hour,
                'temperature': float(sensors.get('temperature', 25.0)),
                'shortwave_radiation': (float(sensors.get('ldr', 0)) / 4095.0) * 1000.0,
                'cloud_cover': 30.0,
                'carbon_intensity': 450.0,
                'grid_price': 6.0,
                'source': 'SIMULATION_FILE'
            }
            conditions['solar_radiation'] = conditions['shortwave_radiation'] / 1000.0

            return conditions
        except Exception as e:
            print(f"Error parsing simulation file: {e}")
            return self._get_fallback_conditions()

    def _read_conditions_from_db(self) -> Dict:
        from ..models import GridData, SensorReading

        temp_sensor = SensorReading.objects.filter(sensor_type='temperature').order_by('-timestamp').first()
        ldr_sensor = SensorReading.objects.filter(sensor_type='ldr').order_by('-timestamp').first()
        carbon_data = GridData.objects.filter(data_type='carbon_intensity').order_by('-timestamp').first()

        conditions = {
            'hour': timezone.now().hour,
            'temperature': float(temp_sensor.value) if temp_sensor else 25.0,
            'shortwave_radiation': 0.0,
            'cloud_cover': 30.0,
            'carbon_intensity': 450.0,
            'grid_price': 6.0,
            'source': 'REAL_SENSORS'
        }

        if ldr_sensor:
            conditions['shortwave_radiation'] = (float(ldr_sensor.value) / 4095.0) * 1000.0

        if carbon_data and carbon_data.metadata:
            conditions['carbon_intensity'] = carbon_data.metadata.get('carbon_intensity', 450.0)
            conditions['grid_price'] = carbon_data.metadata.get('grid_price', 6.0)

        conditions['solar_radiation'] = conditions['shortwave_radiation'] / 1000.0
        return conditions

    def _get_fallback_conditions(self) -> Dict:
        return {
            'hour': timezone.now().hour,
            'temperature': 25.0,
            'shortwave_radiation': 500.0,
            'solar_radiation': 0.5,
            'cloud_cover': 30.0,
            'carbon_intensity': 450.0,
            'grid_price': 6.0,
            'source': 'FALLBACK'
        }

    def _build_reasoning(self, allocation: List[Tuple], conditions: Dict, load_name: str) -> str:
        reasons = []

        if allocation:
            primary_source = allocation[0][0].value
            reasons.append(f"Primary source: {primary_source}")

            if primary_source == 'solar':
                if conditions.get('solar_radiation', 0) > 0.5:
                    reasons.append("High solar availability")
                if conditions.get('cloud_cover', 100) < 40:
                    reasons.append("Clear weather conditions")

            if primary_source == 'grid':
                carbon = conditions.get('carbon_intensity', 0)
                if carbon < 400:
                    reasons.append("Low grid carbon intensity")
                elif carbon > 600:
                    reasons.append("High grid carbon but necessary")

        return " | ".join(reasons) if reasons else f"Optimized for {load_name}"

    def _generate_recommendation(self, forecast: List[Dict],
                                 allocation: List[Tuple], metrics: Dict) -> str:
        recommendations = []

        sources_used = [s.value for s, _ in allocation]
        if 'solar' in sources_used:
            recommendations.append("Using solar power (clean & free)")
        if 'battery' in sources_used:
            recommendations.append("Battery discharge active")
        if 'grid' in sources_used:
            recommendations.append("Grid power as backup")

        battery_pct = (metrics['battery_charge'] / 10.0) * 100
        if battery_pct < 20:
            recommendations.append("⚠ Battery low - schedule charging")
        elif battery_pct > 80:
            recommendations.append("✓ Battery well charged")

        if len(forecast) >= 2:
            if forecast[1]['predicted_kwh'] > forecast[0]['predicted_kwh'] * 1.2:
                recommendations.append("⚠ Demand increasing - prepare for higher load")

        return " | ".join(recommendations)