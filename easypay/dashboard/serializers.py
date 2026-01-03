"""
DRF Serializers for Dashboard API.

Provides structured serialization for dashboard statistics.
Requires djangorestframework to be installed.
"""

from __future__ import annotations

try:
    from rest_framework import serializers

    HAS_DRF = True
except ImportError:
    HAS_DRF = False
    serializers = None  # type: ignore[assignment]


if HAS_DRF:

    class SummaryCardSerializer(serializers.Serializer):
        value = serializers.IntegerField()
        formatted = serializers.CharField()
        change = serializers.FloatField(allow_null=True)
        trend = serializers.ChoiceField(choices=["up", "down", "neutral"])

    class DailyTrendSerializer(serializers.Serializer):
        date = serializers.CharField()
        revenue = serializers.IntegerField()
        count = serializers.IntegerField()

    class StatusBreakdownSerializer(serializers.Serializer):
        status = serializers.CharField()
        label = serializers.CharField()
        count = serializers.IntegerField()
        color = serializers.CharField()

    class MethodBreakdownSerializer(serializers.Serializer):
        method = serializers.CharField()
        label = serializers.CharField()
        count = serializers.IntegerField()
        revenue = serializers.IntegerField()

    class SummarySerializer(serializers.Serializer):
        total_revenue = SummaryCardSerializer()
        transaction_count = SummaryCardSerializer()
        average_value = SummaryCardSerializer()
        refund_count = SummaryCardSerializer()

    class ChartsSerializer(serializers.Serializer):
        daily_trend = DailyTrendSerializer(many=True)
        by_status = StatusBreakdownSerializer(many=True)
        by_method = MethodBreakdownSerializer(many=True)

    class ComparisonDataSerializer(serializers.Serializer):
        label = serializers.CharField()
        current = serializers.IntegerField()
        previous = serializers.IntegerField()

    class MetaSerializer(serializers.Serializer):
        date_range = serializers.CharField()
        start_date = serializers.CharField()
        end_date = serializers.CharField()
        prev_start_date = serializers.CharField()
        prev_end_date = serializers.CharField()

    class DashboardStatsSerializer(serializers.Serializer):
        summary = SummarySerializer()
        charts = ChartsSerializer()
        comparison = ComparisonDataSerializer(many=True)
        meta = MetaSerializer()
