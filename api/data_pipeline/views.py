from django.shortcuts import render
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.utils import timezone
from datetime import timedelta
from django.http import JsonResponse
from .models import SensorReading
from django.utils import timezone

from .models import SensorReading, GridData, UserPreferences, AIDecision, EnergySource, Load, SourceSwitchEvent
from .serializers import (
    SensorReadingSerializer,
    GridDataSerializer,
    UserPreferencesSerializer,
    AIDecisionSerializer,
    EnergySourceSerializer,
    LoadSerializer,
    SourceSwitchEventSerializer
)
from .services.cache_manager import SensorBufferManager
from .services.energy_optimizer import EnergySourceOptimizer
from .services.simple_ai import SimpleAIService

class SensorReadingViewSet(viewsets.ModelViewSet):
    queryset = SensorReading.objects.all()
    serializer_class = SensorReadingSerializer
    filterset_fields = ['sensor_type', 'sensor_id', 'location']
    ordering_fields = ['timestamp', 'created_at']

    @action(detail=False, methods=['get'])
    def all_latest(self, request):
        sensor_types = ['temperature', 'humidity', 'light', 'current', 'voltage']
        sensor_data = {}
        last_updated = None

        for s_type in sensor_types:
            reading = SensorReading.objects.filter(
                sensor_type=s_type
            ).order_by('-timestamp').first()

            if reading:
                sensor_data[s_type] = float(reading.value)
                if not last_updated or reading.timestamp > last_updated:
                    last_updated = reading.timestamp
            else:
                sensor_data[s_type] = 0.0

        return Response({
            'timestamp': timezone.now().isoformat(),
            'last_sensor_update': last_updated.isoformat() if last_updated else None,
            'sensors': sensor_data,
            'source': 'live_database_query'
        })

    @action(detail=False, methods=['get'])
    def recent(self, request):
        hours = int(request.query_params.get('hours', 1))
        sensor_type = request.query_params.get('sensor_type')
        sensor_id = request.query_params.get('sensor_id')

        start_time = timezone.now() - timedelta(hours=hours)
        queryset = self.queryset.filter(timestamp__gte=start_time)

        if sensor_type:
            queryset = queryset.filter(sensor_type=sensor_type)
        if sensor_id:
            queryset = queryset.filter(sensor_id=sensor_id)

        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def buffer(self, request):
        sensor_type = request.query_params.get('sensor_type')
        sensor_id = request.query_params.get('sensor_id')

        if not sensor_type or not sensor_id:
            return Response(
                {'error': 'sensor_type and sensor_id are required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        buffer_manager = SensorBufferManager()
        readings = buffer_manager.get_latest_readings(sensor_type, sensor_id)
        stats = buffer_manager.get_buffer_stats(sensor_type, sensor_id)

        return Response({
            'readings': readings,
            'stats': stats
        })

class GridDataViewSet(viewsets.ModelViewSet):
    queryset = GridData.objects.all()
    serializer_class = GridDataSerializer
    filterset_fields = ['data_type', 'zone']
    ordering_fields = ['timestamp', 'created_at']

    @action(detail=False, methods=['get'])
    def latest(self, request):
        data_type = request.query_params.get('data_type')

        queryset = self.queryset
        if data_type:
            queryset = queryset.filter(data_type=data_type)

        latest_data = []
        seen_types = set()

        for data in queryset:
            if data.data_type not in seen_types:
                latest_data.append(data)
                seen_types.add(data.data_type)

        serializer = self.get_serializer(latest_data, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def carbon_intensity(self, request):
        hours = int(request.query_params.get('hours', 24))
        start_time = timezone.now() - timedelta(hours=hours)

        queryset = self.queryset.filter(
            data_type='carbon_intensity',
            timestamp__gte=start_time
        )

        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def weather(self, request):
        hours = int(request.query_params.get('hours', 24))
        start_time = timezone.now() - timedelta(hours=hours)

        queryset = self.queryset.filter(
            data_type='weather',
            timestamp__gte=start_time
        )

        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

class UserPreferencesViewSet(viewsets.ModelViewSet):
    queryset = UserPreferences.objects.all()
    serializer_class = UserPreferencesSerializer
    lookup_field = 'preference_key'

    @action(detail=False, methods=['get'])
    def get_preference(self, request):
        key = request.query_params.get('key')
        if not key:
            return Response(
                {'error': 'key parameter is required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            preference = self.queryset.get(preference_key=key)
            serializer = self.get_serializer(preference)
            return Response(serializer.data)
        except UserPreferences.DoesNotExist:
            return Response(
                {'error': 'Preference not found'},
                status=status.HTTP_404_NOT_FOUND
            )

class AIDecisionViewSet(viewsets.ModelViewSet):
    queryset = AIDecision.objects.all()
    serializer_class = AIDecisionSerializer
    filterset_fields = ['decision_type', 'applied']
    ordering_fields = ['timestamp', 'created_at', 'confidence']

    @action(detail=False, methods=['get'])
    def recent(self, request):
        hours = int(request.query_params.get('hours', 24))
        decision_type = request.query_params.get('decision_type')

        start_time = timezone.now() - timedelta(hours=hours)
        queryset = self.queryset.filter(timestamp__gte=start_time)

        if decision_type:
            queryset = queryset.filter(decision_type=decision_type)

        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def latest(self, request):
        decision_type = request.query_params.get('decision_type')

        queryset = self.queryset
        if decision_type:
            queryset = queryset.filter(decision_type=decision_type)

        latest = queryset.order_by('-timestamp').first()

        if latest:
            serializer = self.get_serializer(latest)
            return Response(serializer.data)

        return Response({'message': 'No decisions found'}, status=status.HTTP_404_NOT_FOUND)

    @action(detail=False, methods=['get'])
    def history(self, request):
        limit = int(request.query_params.get('limit', 10))
        limit = min(limit, 50)

        decisions = self.queryset.order_by('-timestamp')[:limit]

        result = []
        for decision in decisions:
            decision_data = decision.decision or {}
            current_decision = decision_data.get('current_decision', {})

            result.append({
                'id': decision.id,
                'timestamp': decision.timestamp.isoformat(),
                'decision_type': decision.decision_type,
                'reasoning': decision.reasoning,
                'confidence': decision.confidence,
                'applied': decision.applied,
                'primary_source': current_decision.get('primary_source', 'unknown'),
                'predicted_demand_kwh': current_decision.get('predicted_demand_kwh', 0),
                'battery_percentage': current_decision.get('battery_percentage', 0),
                'solar_available': current_decision.get('solar_available', 0),
                'cost': current_decision.get('cost', 0),
                'carbon': current_decision.get('carbon', 0),
            })

        return Response({
            'count': len(result),
            'decisions': result
        })

class EnergySourceViewSet(viewsets.ModelViewSet):
    queryset = EnergySource.objects.all()
    serializer_class = EnergySourceSerializer

    @action(detail=False, methods=['get'])
    def available(self, request):
        queryset = self.queryset.filter(is_available=True)
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

class LoadViewSet(viewsets.ModelViewSet):
    queryset = Load.objects.all()
    serializer_class = LoadSerializer
    filterset_fields = ['category', 'priority', 'is_active']
    ordering_fields = ['priority', 'rated_power', 'name']

    @action(detail=False, methods=['get'])
    def active(self, request):
        queryset = self.queryset.filter(is_active=True)
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def high_priority(self, request):
        queryset = self.queryset.filter(priority__gte=75)
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['post'])
    def recommend_source(self, request, pk=None):
        load = self.get_object()
        optimizer = EnergySourceOptimizer()

        recommendation = optimizer.recommend_source_for_load(
            load_name=load.name,
            load_priority=load.priority,
            load_power=load.rated_power
        )

        return Response(recommendation)

    @action(detail=True, methods=['post'])
    def check_switch(self, request, pk=None):
        load = self.get_object()

        if not load.current_source:
            return Response({
                'error': 'Load has no current source assigned'
            }, status=status.HTTP_400_BAD_REQUEST)

        optimizer = EnergySourceOptimizer()
        switch_recommendation = optimizer.should_switch_source(
            current_source=load.current_source,
            load_name=load.name,
            load_priority=load.priority
        )

        return Response(switch_recommendation)

class SourceSwitchEventViewSet(viewsets.ModelViewSet):
    queryset = SourceSwitchEvent.objects.all()
    serializer_class = SourceSwitchEventSerializer
    filterset_fields = ['load', 'to_source', 'triggered_by', 'success']
    ordering_fields = ['timestamp']

    @action(detail=False, methods=['get'])
    def recent(self, request):
        hours = int(request.query_params.get('hours', 24))
        start_time = timezone.now() - timedelta(hours=hours)

        queryset = self.queryset.filter(timestamp__gte=start_time)
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def by_load(self, request):
        load_id = request.query_params.get('load_id')

        if not load_id:
            return Response({
                'error': 'load_id parameter required'
            }, status=status.HTTP_400_BAD_REQUEST)

        queryset = self.queryset.filter(load_id=load_id)
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

class EnergyOptimizationViewSet(viewsets.ViewSet):

    @action(detail=False, methods=['post'])
    def recommend(self, request):
        load_name = request.data.get('load_name')
        load_priority = request.data.get('load_priority', 50)
        load_power = request.data.get('load_power', 0)

        if not load_name:
            return Response({
                'error': 'load_name is required'
            }, status=status.HTTP_400_BAD_REQUEST)

        optimizer = EnergySourceOptimizer()
        recommendation = optimizer.recommend_source_for_load(
            load_name=load_name,
            load_priority=load_priority,
            load_power=load_power
        )

        return Response(recommendation)

    @action(detail=False, methods=['get'])
    def context(self, request):
        optimizer = EnergySourceOptimizer()
        context = optimizer.gather_context()

        return Response(context)

    @action(detail=False, methods=['get'])
    def distribution(self, request):
        optimizer = EnergySourceOptimizer()
        distribution = optimizer.get_optimal_source_distribution()

        return Response(distribution)

    @action(detail=False, methods=['post'])
    def execute_switch(self, request):
        load_id = request.data.get('load_id')
        to_source = request.data.get('to_source')
        reason = request.data.get('reason', 'Automatic optimization')
        triggered_by = request.data.get('triggered_by', 'automatic')

        if not load_id or not to_source:
            return Response({
                'error': 'load_id and to_source are required'
            }, status=status.HTTP_400_BAD_REQUEST)

        try:
            load = Load.objects.get(id=load_id)
        except Load.DoesNotExist:
            return Response({
                'error': 'Load not found'
            }, status=status.HTTP_404_NOT_FOUND)

        switch_event = SourceSwitchEvent.objects.create(
            load=load,
            from_source=load.current_source,
            to_source=to_source,
            reason=reason,
            triggered_by=triggered_by,
        )

        load.current_source = to_source
        load.save()

        serializer = SourceSwitchEventSerializer(switch_event)

        return Response({
            'message': 'Switch recorded successfully',
            'switch_event': serializer.data,
            'mqtt_command': {
                'topic': f'HyperVolt/commands/load_{load.id}',
                'payload': {
                    'command': 'switch_source',
                    'load_id': load.id,
                    'load_name': load.name,
                    'to_source': to_source,
                    'timestamp': timezone.now().isoformat(),
                }
            },
            'note': 'Module 1 (Hardware) should subscribe to MQTT commands and execute the physical switch'
        }, status=status.HTTP_201_CREATED)

class AIPredictionViewSet(viewsets.ViewSet):

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.ai_service = SimpleAIService()

    @action(detail=False, methods=['get'])
    def status(self, request):
        status = self.ai_service.get_status()
        return Response(status)

    @action(detail=False, methods=['get'])
    def forecast(self, request):
        try:
            hours = int(request.query_params.get('hours', 6))
        except (ValueError, TypeError):
            hours = 6
        hours = max(1, min(hours, 24))

        result = self.ai_service.forecast_demand(hours_ahead=hours)

        try:
            AIDecision.objects.create(
                decision_type='general',
                timestamp=timezone.now(),
                decision=result,
                confidence=0.85,
                applied=False,
                reasoning=result.get('recommendation', 'Energy demand forecast')
            )
        except Exception as e:
            print(f"Warning: Could not record forecast: {e}")

        return Response(result)

    @action(detail=False, methods=['get'])
    def peak_hours(self, request):
        try:
            hours = int(request.query_params.get('hours', 24))
        except (ValueError, TypeError):
            hours = 24
        hours = max(1, min(hours, 48))

        result = self.ai_service.forecast_demand(hours_ahead=hours)

        return Response({
            'timestamp': result['timestamp'],
            'peak_hours': result['peak_hours'],
            'next_peak': result['next_peak'],
            'total_predictions': len(result['predictions']),
            'recommendation': result['recommendation']
        })

    @action(detail=False, methods=['post'])
    def recommend_source(self, request):
        load_name = request.data.get('load_name', 'Default Load')
        load_priority = request.data.get('load_priority', 50)
        load_power = request.data.get('load_power', 1000)

        result = self.ai_service.recommend_source(
            load_name=load_name,
            load_priority=load_priority,
            load_power=load_power
        )

        try:
            AIDecision.objects.create(
                decision_type='power_source',
                timestamp=timezone.now(),
                decision=result,
                confidence=result.get('confidence', 0.85),
                applied=False,
                reasoning=result.get('reasoning', '')
            )
        except Exception as e:
            print(f"Warning: Could not record recommendation: {e}")

        return Response(result)

    @action(detail=False, methods=['post'])
    def decide(self, request):
        result = self.ai_service.make_decision()

        try:
            AIDecision.objects.create(
                decision_type='general',
                timestamp=timezone.now(),
                decision=result,
                confidence=0.85,
                applied=True,
                reasoning=result.get('recommendation', '')
            )
        except Exception as e:
            print(f"Warning: Could not record decision: {e}")

        return Response(result)

    @action(detail=False, methods=['get'])
    def conditions(self, request):
        conditions = self.ai_service.get_conditions()
        return Response({
            'timestamp': timezone.now().isoformat(),
            'conditions': conditions,
            'source': conditions.get('source', 'unknown')
        })
