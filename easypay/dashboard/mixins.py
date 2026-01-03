"""
Dashboard Mixin for Django Admin.

Provides a payment analytics dashboard view integrated into the admin.
"""

from __future__ import annotations

import csv
import json
from datetime import timedelta
from typing import TYPE_CHECKING

from django.core.serializers.json import DjangoJSONEncoder
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.template.response import TemplateResponse
from django.urls import URLPattern, path
from django.utils import timezone

from .statistics import get_dashboard_statistics, parse_date_range

try:
    from .serializers import DashboardStatsSerializer

    HAS_DRF = True
except ImportError:
    HAS_DRF = False
    DashboardStatsSerializer = None  # type: ignore[assignment, misc]

if TYPE_CHECKING:
    from django.db.models import QuerySet


class PaymentDashboardMixin:
    """
    Mixin that adds a payment analytics dashboard to Django Admin.

    Provides a dedicated dashboard page with:
    - Summary cards (revenue, transactions, average, refunds)
    - Revenue trend chart (line chart)
    - Status breakdown chart (doughnut)
    - Payment method breakdown chart (bar)

    Usage:
        from easypay.admin import PaymentAdminMixin
        from easypay.dashboard import PaymentDashboardMixin

        @admin.register(Payment)
        class PaymentAdmin(PaymentDashboardMixin, PaymentAdminMixin, admin.ModelAdmin):
            pass

    Configuration:
        dashboard_template: Template path for dashboard page
        dashboard_default_range: Default date range ('today', '7d', '30d', '90d')
    """

    # Dashboard configuration
    dashboard_template: str = "easypay/dashboard/base.html"
    dashboard_default_range: str = "month"

    # Valid date ranges (including custom)
    VALID_DATE_RANGES: tuple[str, ...] = ("today", "7d", "month", "30d", "90d", "custom")

    def get_urls(self) -> list[URLPattern]:
        """Add dashboard URLs to model admin."""
        urls = super().get_urls()  # type: ignore[misc]

        # Get model info for URL naming
        info = self._get_model_info()

        dashboard_urls = [
            path(
                "dashboard/",
                self.admin_site.admin_view(self.dashboard_view),  # type: ignore[attr-defined]
                name=f"{info}_dashboard",
            ),
            path(
                "dashboard/api/",
                self.admin_site.admin_view(self.dashboard_api_view),  # type: ignore[attr-defined]
                name=f"{info}_dashboard_api",
            ),
            path(
                "dashboard/export/",
                self.admin_site.admin_view(self.dashboard_export_view),  # type: ignore[attr-defined]
                name=f"{info}_dashboard_export",
            ),
        ]
        return dashboard_urls + urls

    def _get_model_info(self) -> str:
        """Get model info string for URL naming."""
        # Access model._meta from ModelAdmin
        opts = self.model._meta  # type: ignore[attr-defined]
        return f"{opts.app_label}_{opts.model_name}"

    def _get_date_range(self, request: HttpRequest) -> str:
        """Extract and validate date range from request."""
        date_range = request.GET.get("range", self.dashboard_default_range)
        if date_range not in self.VALID_DATE_RANGES:
            date_range = self.dashboard_default_range
        return date_range

    def _get_custom_dates(self, request: HttpRequest) -> tuple[str | None, str | None]:
        """Extract custom start/end dates from request."""
        start_date = request.GET.get("start_date")
        end_date = request.GET.get("end_date")
        return start_date, end_date

    def _get_dashboard_queryset(self, request: HttpRequest) -> QuerySet:
        """Get queryset for dashboard statistics."""
        # Use the same queryset as changelist
        return self.get_queryset(request)  # type: ignore[attr-defined]

    def dashboard_view(self, request: HttpRequest) -> HttpResponse:
        """
        Render the dashboard page.

        Returns an HTML page with charts and summary cards.
        """
        date_range = self._get_date_range(request)
        start_date_str, end_date_str = self._get_custom_dates(request)
        queryset = self._get_dashboard_queryset(request)
        stats = get_dashboard_statistics(queryset, date_range, start_date_str, end_date_str)

        api_url = f"api/?range={date_range}"
        if date_range == "custom" and start_date_str and end_date_str:
            api_url += f"&start_date={start_date_str}&end_date={end_date_str}"

        today = timezone.now().date()
        default_start = (today - timedelta(days=6)).isoformat()
        default_end = today.isoformat()

        context = {
            **self.admin_site.each_context(request),  # type: ignore[attr-defined]
            "title": "결제 대시보드",
            "opts": self.model._meta,  # type: ignore[attr-defined]
            "stats": stats,
            "date_range": date_range,
            "date_ranges": self.VALID_DATE_RANGES,
            "api_url": api_url,
            "chart_data": json.dumps(stats, cls=DjangoJSONEncoder),
            "has_change_permission": self.has_change_permission(request),  # type: ignore[attr-defined]
            "custom_start_date": start_date_str or default_start,
            "custom_end_date": end_date_str or default_end,
            "today": today.isoformat(),
        }

        return TemplateResponse(request, self.dashboard_template, context)

    def dashboard_api_view(self, request: HttpRequest) -> HttpResponse:
        date_range = self._get_date_range(request)
        start_date_str, end_date_str = self._get_custom_dates(request)
        queryset = self._get_dashboard_queryset(request)
        stats = get_dashboard_statistics(queryset, date_range, start_date_str, end_date_str)

        if HAS_DRF:
            serializer = DashboardStatsSerializer(data=stats)
            serializer.is_valid(raise_exception=True)
            return JsonResponse(serializer.validated_data)

        return JsonResponse(stats, encoder=DjangoJSONEncoder)

    def dashboard_export_view(self, request: HttpRequest) -> HttpResponse:
        """Export filtered payments as CSV."""
        date_range = self._get_date_range(request)
        start_date_str, end_date_str = self._get_custom_dates(request)
        queryset = self._get_dashboard_queryset(request)

        start_date, end_date = parse_date_range(date_range, start_date_str, end_date_str)

        from django.db.models import Q

        from easypay.models import PaymentStatus

        filtered_qs = queryset.filter(
            Q(paid_at__date__gte=start_date, paid_at__date__lte=end_date)
            | Q(
                paid_at__isnull=True,
                created_at__date__gte=start_date,
                created_at__date__lte=end_date,
            )
        ).order_by("-created_at")

        response = HttpResponse(content_type="text/csv; charset=utf-8-sig")
        filename = f"payments_{start_date}_{end_date}.csv"
        response["Content-Disposition"] = f'attachment; filename="{filename}"'

        writer = csv.writer(response)
        writer.writerow(
            [
                "ID",
                "주문번호",
                "금액",
                "상태",
                "결제수단",
                "생성일시",
                "결제일시",
            ]
        )

        status_labels = dict(PaymentStatus.choices)
        for payment in filtered_qs:
            writer.writerow(
                [
                    payment.pk,
                    getattr(payment, "order_no", ""),
                    payment.amount,
                    status_labels.get(payment.status, payment.status),
                    getattr(payment, "pay_method_type_code", ""),
                    payment.created_at.strftime("%Y-%m-%d %H:%M:%S") if payment.created_at else "",
                    payment.paid_at.strftime("%Y-%m-%d %H:%M:%S") if payment.paid_at else "",
                ]
            )

        return response

    def _get_dashboard_link(self) -> str:
        """Get URL to dashboard page (for admin templates)."""
        from django.urls import reverse

        info = self._get_model_info()
        return reverse(f"admin:{info}_dashboard")
