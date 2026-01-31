import logging
from django.utils import timezone
from django.db.models import Q

from data_pipeline.models import (
    EnergySource,
    SensorReading,
    GridData,
    AIDecision,
    UserPreferences
)

logger = logging.getLogger(__name__)

class EnergySourceOptimizer:

    PRIORITY_CRITICAL = 100
    PRIORITY_HIGH = 75
    PRIORITY_MEDIUM = 50
    PRIORITY_LOW = 25

    SOURCE_PREFERENCES = {
        'solar': 100,
        'battery': 75,
        'generator': 25,
        'grid': 50,
    }

    def __init__(self):
        self.context = {}

    def gather_context(self):
        context = {
            'timestamp': timezone.now().isoformat(),
            'energy_sources': self._get_energy_source_status(),
            'weather': self._get_weather_context(),
            'carbon_intensity': self._get_carbon_intensity(),
            'sensor_data': self._get_sensor_data(),
            'user_preferences': self._get_user_preferences(),
        }

        self.context = context
        return context

    def _get_energy_source_status(self):
        sources = {}
        for source in EnergySource.objects.all():
            sources[source.source_type] = {
                'available': source.is_available,
                'capacity': source.capacity,
                'current_output': source.current_output,
                'priority': source.priority,
            }
        return sources

    def _get_weather_context(self):
        try:
            latest_weather = GridData.objects.filter(
                data_type='weather'
            ).order_by('-timestamp').first()

            if latest_weather:
                return {
                    'temperature': latest_weather.value,
                    'cloud_cover': latest_weather.metadata.get('cloud_cover', 0),
                    'condition': latest_weather.metadata.get('weather_condition', 'Unknown'),
                    'timestamp': latest_weather.timestamp.isoformat(),
                }
        except Exception as e:
            logger.error(f"Error getting weather context: {e}")

        return None

    def _get_carbon_intensity(self):
        try:
            latest_carbon = GridData.objects.filter(
                data_type='carbon_intensity'
            ).order_by('-timestamp').first()

            if latest_carbon:
                return {
                    'value': latest_carbon.value,
                    'unit': latest_carbon.unit,
                    'timestamp': latest_carbon.timestamp.isoformat(),
                }
        except Exception as e:
            logger.error(f"Error getting carbon intensity: {e}")

        return None

    def _get_sensor_data(self):
        sensors = {}

        sensor_types = ['ldr', 'current', 'temperature', 'humidity']
        for sensor_type in sensor_types:
            try:
                latest = SensorReading.objects.filter(
                    sensor_type=sensor_type
                ).order_by('-timestamp').first()

                if latest:
                    sensors[sensor_type] = {
                        'value': latest.value,
                        'unit': latest.unit,
                        'timestamp': latest.timestamp.isoformat(),
                    }
            except Exception as e:
                logger.error(f"Error getting {sensor_type} data: {e}")

        return sensors

    def _get_user_preferences(self):
        prefs = {}
        try:
            comfort_pref = UserPreferences.objects.filter(
                preference_key='comfort_level'
            ).first()
            if comfort_pref:
                prefs['comfort_level'] = comfort_pref.preference_value

            cost_pref = UserPreferences.objects.filter(
                preference_key='cost_optimization'
            ).first()
            if cost_pref:
                prefs['cost_optimization'] = cost_pref.preference_value
        except Exception as e:
            logger.error(f"Error getting user preferences: {e}")

        return prefs

    def recommend_source_for_load(self, load_name, load_priority=PRIORITY_MEDIUM, load_power=0):
        context = self.gather_context()

        available_sources = [
            source for source, status in context['energy_sources'].items()
            if status['available'] and status['capacity'] and status['current_output'] + load_power <= status['capacity']
        ]

        if not available_sources:
            return {
                'recommended_source': None,
                'reasoning': 'No energy sources available with sufficient capacity',
                'confidence': 1.0,
                'fallback_to_grid': True,
                'context': context,
            }

        recommendation = self._rule_based_optimization(
            available_sources,
            load_name,
            load_priority,
            load_power,
            context
        )

        self._record_decision(recommendation)

        return recommendation

    def _rule_based_optimization(self, available_sources, load_name, load_priority, load_power, context):
        reasoning_parts = []
        scores = {}

        for source in available_sources:
            score = self.SOURCE_PREFERENCES.get(source, 0)

            if source == 'solar':
                weather = context.get('weather')
                if weather:
                    cloud_cover = weather.get('cloud_cover', 100)
                    if cloud_cover < 30:
                        score += 20
                        reasoning_parts.append("Clear weather favors solar")
                    elif cloud_cover < 60:
                        score += 10
                        reasoning_parts.append("Partly cloudy, solar still viable")

                ldr_data = context.get('sensor_data', {}).get('ldr')
                if ldr_data and ldr_data['value'] > 500:
                    score += 15
                    reasoning_parts.append("High light intensity detected")

            if source == 'grid':
                carbon = context.get('carbon_intensity')
                if carbon and carbon['value'] > 500:
                    score -= 30
                    reasoning_parts.append("High grid carbon intensity")
                elif carbon and carbon['value'] < 300:
                    score += 20
                    reasoning_parts.append("Low grid carbon intensity")

            if source == 'battery' and load_priority >= self.PRIORITY_HIGH:
                score += 15
                reasoning_parts.append("Battery prioritized for critical loads")

            scores[source] = score

        recommended_source = max(scores, key=scores.get)

        reasoning = f"Selected {recommended_source} for {load_name}. "
        reasoning += " ".join(reasoning_parts[:3])

        return {
            'recommended_source': recommended_source,
            'load_name': load_name,
            'load_priority': load_priority,
            'load_power': load_power,
            'reasoning': reasoning,
            'confidence': 0.7,
            'scores': scores,
            'context': context,
            'algorithm': 'rule_based',
        }

    def _record_decision(self, recommendation):
        try:
            AIDecision.objects.create(
                decision_type='power_source',
                decision={
                    'recommended_source': recommendation['recommended_source'],
                    'load_name': recommendation.get('load_name'),
                    'load_priority': recommendation.get('load_priority'),
                    'load_power': recommendation.get('load_power'),
                    'scores': recommendation.get('scores', {}),
                    'algorithm': recommendation.get('algorithm', 'rule_based'),
                },
                confidence=recommendation.get('confidence', 0.5),
                reasoning=recommendation['reasoning'],
                applied=False,
            )
        except Exception as e:
            logger.error(f"Error recording decision: {e}")

    def get_optimal_source_distribution(self):
        context = self.gather_context()

        distribution = {
            'timestamp': context['timestamp'],
            'available_sources': list(context['energy_sources'].keys()),
            'recommendations': [
                {
                    'load_category': 'HVAC',
                    'priority': self.PRIORITY_HIGH,
                    'recommended_source': 'solar',
                    'fallback_source': 'battery',
                },
                {
                    'load_category': 'Lighting',
                    'priority': self.PRIORITY_MEDIUM,
                    'recommended_source': 'grid',
                    'fallback_source': 'solar',
                },
                {
                    'load_category': 'Entertainment',
                    'priority': self.PRIORITY_LOW,
                    'recommended_source': 'grid',
                    'fallback_source': 'battery',
                },
            ],
            'note': 'Basic rule-based distribution. Module 3 will enhance with ML optimization.',
        }

        return distribution

    def should_switch_source(self, current_source, load_name, load_priority):
        recommendation = self.recommend_source_for_load(load_name, load_priority)

        recommended = recommendation['recommended_source']

        if recommended == current_source:
            return {
                'should_switch': False,
                'current_source': current_source,
                'reasoning': 'Current source is optimal',
            }

        current_score = self.SOURCE_PREFERENCES.get(current_source, 0)
        recommended_score = recommendation.get('scores', {}).get(recommended, 0)

        threshold = 20
        if recommended_score - current_score > threshold:
            return {
                'should_switch': True,
                'current_source': current_source,
                'recommended_source': recommended,
                'reasoning': recommendation['reasoning'],
                'score_improvement': recommended_score - current_score,
            }

        return {
            'should_switch': False,
            'current_source': current_source,
            'reasoning': 'Improvement not significant enough to justify switching',
            'score_difference': recommended_score - current_score,
        }
