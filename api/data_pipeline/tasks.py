import logging
from django.utils import timezone

from .models import GridData
from .services import ElectricityMapsService, WeatherService

logger = logging.getLogger(__name__)

def fetch_carbon_intensity():
    try:
        service = ElectricityMapsService()

        data = service.get_carbon_intensity()
        if data is None:
            logger.warning("Using mock carbon intensity data")
            data = service.get_mock_carbon_intensity()

        grid_data = GridData.objects.create(
            data_type='carbon_intensity',
            value=data['carbon_intensity'],
            unit=data['unit'],
            zone=data['zone'],
            metadata={
                'fossil_free_percentage': data.get('fossil_free_percentage'),
                'renewable_percentage': data.get('renewable_percentage'),
            },
            timestamp=timezone.now()
        )

        logger.info(f"Saved carbon intensity: {grid_data}")
        return f"Successfully fetched carbon intensity: {data['carbon_intensity']} {data['unit']}"

    except Exception as e:
        logger.error(f"Failed to fetch carbon intensity: {e}")
        raise

def fetch_weather_data():
    try:
        service = WeatherService()

        data = service.get_current_weather()
        if data is None:
            logger.warning("Using mock weather data")
            data = service.get_mock_weather()

        GridData.objects.create(
            data_type='weather',
            value=data['temperature'],
            unit='celsius',
            metadata={
                'humidity': data.get('humidity'),
                'cloud_cover': data.get('cloud_cover'),
                'weather_condition': data.get('weather_condition'),
                'description': data.get('description'),
            },
            timestamp=timezone.now()
        )

        logger.info(f"Saved weather data: {data['temperature']}°C, {data.get('description')}")
        return f"Successfully fetched weather: {data['temperature']}°C"

    except Exception as e:
        logger.error(f"Failed to fetch weather data: {e}")
        raise

def cleanup_old_data():
    try:
        from datetime import timedelta
        from .models import SensorReading

        cutoff_date = timezone.now() - timedelta(days=7)

        sensor_count = SensorReading.objects.filter(timestamp__lt=cutoff_date).count()
        SensorReading.objects.filter(timestamp__lt=cutoff_date).delete()

        grid_count = GridData.objects.filter(timestamp__lt=cutoff_date).count()
        GridData.objects.filter(timestamp__lt=cutoff_date).delete()

        logger.info(f"Cleaned up {sensor_count} sensor readings and {grid_count} grid data entries")
        return f"Cleaned up {sensor_count} sensor readings and {grid_count} grid data entries"

    except Exception as e:
        logger.error(f"Failed to cleanup old data: {e}")
        raise
