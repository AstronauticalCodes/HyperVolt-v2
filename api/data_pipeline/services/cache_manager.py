import json
import logging
from django.core.cache import cache
from django.conf import settings

logger = logging.getLogger(__name__)

class SensorBufferManager:

    def __init__(self):
        self.buffer_size = settings.SENSOR_BUFFER_SIZE
        self.key_prefix = settings.SENSOR_BUFFER_KEY_PREFIX

    def _get_buffer_key(self, sensor_type, sensor_id):
        return f"{self.key_prefix}:{sensor_type}:{sensor_id}"

    def add_reading(self, sensor_type, sensor_id, value, timestamp):
        key = self._get_buffer_key(sensor_type, sensor_id)

        buffer = cache.get(key, [])

        reading = {
            'value': value,
            'timestamp': timestamp
        }
        buffer.append(reading)

        if len(buffer) > self.buffer_size:
            buffer = buffer[-self.buffer_size:]

        cache.set(key, buffer, 3600)

        logger.debug(f"Added reading to buffer {key}: {reading}")

    def get_latest_readings(self, sensor_type, sensor_id, count=None):
        key = self._get_buffer_key(sensor_type, sensor_id)
        buffer = cache.get(key, [])

        if count:
            return buffer[-count:]
        return buffer

    def get_all_buffers(self):
        return {}

    def clear_buffer(self, sensor_type, sensor_id):
        key = self._get_buffer_key(sensor_type, sensor_id)
        cache.delete(key)
        logger.info(f"Cleared buffer for {key}")

    def get_buffer_stats(self, sensor_type, sensor_id):
        buffer = self.get_latest_readings(sensor_type, sensor_id)

        if not buffer:
            return {
                'count': 0,
                'is_full': False
            }

        values = [r['value'] for r in buffer]

        return {
            'count': len(buffer),
            'is_full': len(buffer) >= self.buffer_size,
            'latest_value': buffer[-1]['value'],
            'latest_timestamp': buffer[-1]['timestamp'],
            'min_value': min(values),
            'max_value': max(values),
            'avg_value': sum(values) / len(values)
        }
