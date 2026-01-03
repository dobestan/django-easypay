"""
DRF API Views for Dashboard.

Provides REST API endpoints for dashboard statistics.
Falls back to JsonResponse if DRF is not installed.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.http import JsonResponse

from .statistics import get_dashboard_statistics

if TYPE_CHECKING:
    from django.db.models import QuerySet
    from django.http import HttpRequest

try:
    from rest_framework import status
    from rest_framework.permissions import IsAdminUser
    from rest_framework.response import Response
    from rest_framework.views import APIView

    from .serializers import DashboardStatsSerializer

    HAS_DRF = True
except ImportError:
    HAS_DRF = False


VALID_DATE_RANGES = ("today", "7d", "30d", "90d")
DEFAULT_DATE_RANGE = "7d"


def get_validated_date_range(request: HttpRequest) -> str:
    date_range = request.GET.get("range", DEFAULT_DATE_RANGE)
    if date_range not in VALID_DATE_RANGES:
        return DEFAULT_DATE_RANGE
    return date_range


if HAS_DRF:

    class DashboardAPIView(APIView):
        permission_classes = [IsAdminUser]
        queryset: QuerySet | None = None

        def get_queryset(self) -> QuerySet:
            if self.queryset is None:
                raise NotImplementedError("Subclass must set queryset or override get_queryset()")
            return self.queryset

        def get(self, request: HttpRequest) -> Response:
            date_range = get_validated_date_range(request)
            queryset = self.get_queryset()
            stats = get_dashboard_statistics(queryset, date_range)

            serializer = DashboardStatsSerializer(data=stats)
            serializer.is_valid(raise_exception=True)

            return Response(serializer.validated_data, status=status.HTTP_200_OK)


def create_dashboard_api_view(queryset_callback):
    """
    Factory function to create a dashboard API view.

    Works with both DRF (if installed) and plain Django.

    Args:
        queryset_callback: Callable that returns a QuerySet

    Returns:
        View function or APIView class
    """
    if HAS_DRF:

        class BoundDashboardAPIView(DashboardAPIView):
            def get_queryset(self) -> QuerySet:
                return queryset_callback()

        return BoundDashboardAPIView.as_view()
    else:

        def fallback_api_view(request: HttpRequest) -> JsonResponse:
            date_range = get_validated_date_range(request)
            queryset = queryset_callback()
            stats = get_dashboard_statistics(queryset, date_range)
            return JsonResponse(stats)

        return fallback_api_view
