"""
Tests for Payment Dashboard.

Tests cover:
- Statistics calculations with date ranges
- Dashboard mixin URL configuration
- Dashboard view rendering
- Dashboard API endpoint
"""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.contrib import admin
from django.contrib.admin.sites import AdminSite
from django.utils import timezone
from freezegun import freeze_time

from easypay.dashboard import PaymentDashboardMixin
from easypay.dashboard.statistics import (
    calculate_change,
    get_dashboard_statistics,
    parse_date_range,
)
from easypay.models import PaymentStatus


class TestDateRangeParsing:
    @freeze_time("2026-01-15")
    def test_today_range(self):
        start, end = parse_date_range("today")
        assert start.isoformat() == "2026-01-15"
        assert end.isoformat() == "2026-01-15"

    @freeze_time("2026-01-15")
    def test_7d_range(self):
        start, end = parse_date_range("7d")
        assert start.isoformat() == "2026-01-09"
        assert end.isoformat() == "2026-01-15"

    @freeze_time("2026-01-15")
    def test_30d_range(self):
        start, end = parse_date_range("30d")
        assert start.isoformat() == "2025-12-17"
        assert end.isoformat() == "2026-01-15"

    @freeze_time("2026-01-15")
    def test_90d_range(self):
        start, end = parse_date_range("90d")
        assert start.isoformat() == "2025-10-18"
        assert end.isoformat() == "2026-01-15"

    @freeze_time("2026-01-15")
    def test_invalid_range_defaults_to_month(self):
        start, end = parse_date_range("invalid")
        assert start.isoformat() == "2026-01-01"
        assert end.isoformat() == "2026-01-15"

    @freeze_time("2026-01-15")
    def test_month_range(self):
        start, end = parse_date_range("month")
        assert start.isoformat() == "2026-01-01"
        assert end.isoformat() == "2026-01-15"

    @freeze_time("2026-01-15")
    def test_custom_range(self):
        start, end = parse_date_range("custom", "2026-01-05", "2026-01-10")
        assert start.isoformat() == "2026-01-05"
        assert end.isoformat() == "2026-01-10"

    @freeze_time("2026-01-15")
    def test_custom_range_swaps_if_reversed(self):
        start, end = parse_date_range("custom", "2026-01-10", "2026-01-05")
        assert start.isoformat() == "2026-01-05"
        assert end.isoformat() == "2026-01-10"

    @freeze_time("2026-01-15")
    def test_custom_range_clamps_future_date(self):
        start, end = parse_date_range("custom", "2026-01-10", "2026-01-20")
        assert start.isoformat() == "2026-01-10"
        assert end.isoformat() == "2026-01-15"


class TestCalculateChange:
    def test_positive_change(self):
        change, trend = calculate_change(120, 100)
        assert change == 20.0
        assert trend == "up"

    def test_negative_change(self):
        change, trend = calculate_change(80, 100)
        assert change == -20.0
        assert trend == "down"

    def test_no_change(self):
        change, trend = calculate_change(100, 100)
        assert change == 0.0
        assert trend == "neutral"

    def test_zero_previous_with_current(self):
        change, trend = calculate_change(100, 0)
        assert change is None
        assert trend == "up"

    def test_both_zero(self):
        change, trend = calculate_change(0, 0)
        assert change is None
        assert trend == "neutral"


@pytest.mark.django_db
class TestDashboardStatistics:
    @freeze_time("2026-01-15 12:00:00")
    def test_empty_queryset(self, db):
        from tests.models import Payment

        queryset = Payment.objects.none()
        stats = get_dashboard_statistics(queryset, "7d")

        assert stats["summary"]["total_revenue"]["value"] == 0
        assert stats["summary"]["transaction_count"]["value"] == 0
        assert stats["summary"]["average_value"]["value"] == 0
        assert stats["summary"]["refund_count"]["value"] == 0

    @freeze_time("2026-01-15 12:00:00")
    def test_completed_payments_in_range(self, db):
        from tests.models import Payment

        Payment.objects.create(
            amount=Decimal("10000"),
            status=PaymentStatus.COMPLETED,
            paid_at=timezone.now(),
        )
        Payment.objects.create(
            amount=Decimal("20000"),
            status=PaymentStatus.COMPLETED,
            paid_at=timezone.now() - timedelta(days=1),
        )

        stats = get_dashboard_statistics(Payment.objects.all(), "7d")

        assert stats["summary"]["total_revenue"]["value"] == 30000
        assert stats["summary"]["transaction_count"]["value"] == 2
        assert stats["summary"]["average_value"]["value"] == 15000

    @freeze_time("2026-01-15 12:00:00")
    def test_payments_outside_range_excluded(self, db):
        from tests.models import Payment

        Payment.objects.create(
            amount=Decimal("10000"),
            status=PaymentStatus.COMPLETED,
            paid_at=timezone.now(),
        )
        Payment.objects.create(
            amount=Decimal("50000"),
            status=PaymentStatus.COMPLETED,
            paid_at=timezone.now() - timedelta(days=30),
        )

        stats = get_dashboard_statistics(Payment.objects.all(), "7d")

        assert stats["summary"]["total_revenue"]["value"] == 10000
        assert stats["summary"]["transaction_count"]["value"] == 1

    @freeze_time("2026-01-15 12:00:00")
    def test_refund_count(self, db):
        from tests.models import Payment

        Payment.objects.create(
            amount=Decimal("10000"),
            status=PaymentStatus.REFUNDED,
            created_at=timezone.now(),
        )
        Payment.objects.create(
            amount=Decimal("10000"),
            status=PaymentStatus.CANCELLED,
            created_at=timezone.now(),
        )

        stats = get_dashboard_statistics(Payment.objects.all(), "7d")

        assert stats["summary"]["refund_count"]["value"] == 2

    @freeze_time("2026-01-15 12:00:00")
    def test_daily_trend_fills_missing_dates(self, db):
        from tests.models import Payment

        Payment.objects.create(
            amount=Decimal("10000"),
            status=PaymentStatus.COMPLETED,
            paid_at=timezone.now(),
        )

        stats = get_dashboard_statistics(Payment.objects.all(), "7d")
        daily_trend = stats["charts"]["daily_trend"]

        assert len(daily_trend) == 7
        assert daily_trend[-1]["revenue"] == 10000
        assert daily_trend[0]["revenue"] == 0

    @freeze_time("2026-01-15 12:00:00")
    def test_status_breakdown(self, db):
        from tests.models import Payment

        Payment.objects.create(
            amount=Decimal("10000"),
            status=PaymentStatus.COMPLETED,
            paid_at=timezone.now(),
        )
        Payment.objects.create(
            amount=Decimal("10000"),
            status=PaymentStatus.PENDING,
            created_at=timezone.now(),
        )
        Payment.objects.create(
            amount=Decimal("10000"),
            status=PaymentStatus.REFUNDED,
            created_at=timezone.now(),
        )

        stats = get_dashboard_statistics(Payment.objects.all(), "7d")
        by_status = stats["charts"]["by_status"]

        assert len(by_status) == 3
        status_counts = {s["status"]: s["count"] for s in by_status}
        assert status_counts[PaymentStatus.COMPLETED] == 1
        assert status_counts[PaymentStatus.PENDING] == 1
        assert status_counts[PaymentStatus.REFUNDED] == 1

    @freeze_time("2026-01-15 12:00:00")
    def test_method_breakdown(self, db):
        from tests.models import Payment

        Payment.objects.create(
            amount=Decimal("10000"),
            status=PaymentStatus.COMPLETED,
            paid_at=timezone.now(),
            pay_method_type_code="11",
        )
        Payment.objects.create(
            amount=Decimal("20000"),
            status=PaymentStatus.COMPLETED,
            paid_at=timezone.now(),
            pay_method_type_code="11",
        )
        Payment.objects.create(
            amount=Decimal("5000"),
            status=PaymentStatus.COMPLETED,
            paid_at=timezone.now(),
            pay_method_type_code="21",
        )

        stats = get_dashboard_statistics(Payment.objects.all(), "7d")
        by_method = stats["charts"]["by_method"]

        assert len(by_method) == 2
        method_data = {m["method"]: m for m in by_method}
        assert method_data["11"]["revenue"] == 30000
        assert method_data["11"]["count"] == 2
        assert method_data["21"]["revenue"] == 5000

    @freeze_time("2026-01-15 12:00:00")
    def test_meta_contains_date_info(self, db):
        from tests.models import Payment

        stats = get_dashboard_statistics(Payment.objects.all(), "7d")

        assert stats["meta"]["date_range"] == "7d"
        assert stats["meta"]["start_date"] == "2026-01-09"
        assert stats["meta"]["end_date"] == "2026-01-15"


@pytest.mark.django_db
class TestDashboardMixin:
    @pytest.fixture
    def dashboard_admin(self, db):
        from easypay.admin import PaymentAdminMixin
        from tests.models import Payment

        class TestDashboardAdmin(PaymentDashboardMixin, PaymentAdminMixin, admin.ModelAdmin):
            pass

        site = AdminSite()
        return TestDashboardAdmin(Payment, site)

    def test_get_urls_adds_dashboard_urls(self, dashboard_admin):
        urls = dashboard_admin.get_urls()
        url_names = [u.name for u in urls if hasattr(u, "name")]

        assert "tests_payment_dashboard" in url_names
        assert "tests_payment_dashboard_api" in url_names

    def test_valid_date_ranges_constant(self, dashboard_admin):
        assert dashboard_admin.VALID_DATE_RANGES == ("today", "7d", "month", "30d", "90d", "custom")

    def test_default_range_is_month(self, dashboard_admin):
        assert dashboard_admin.dashboard_default_range == "month"

    def test_get_urls_adds_export_url(self, dashboard_admin):
        urls = dashboard_admin.get_urls()
        url_names = [u.name for u in urls if hasattr(u, "name")]
        assert "tests_payment_dashboard_export" in url_names


@pytest.mark.django_db
class TestDashboardView:
    def test_dashboard_requires_authentication(self, client, db):
        from tests.models import Payment

        Payment.objects.create(amount=Decimal("10000"), status=PaymentStatus.PENDING)

        response = client.get("/admin/tests/payment/dashboard/")
        assert response.status_code == 302
        assert "login" in response.url

    def test_dashboard_accessible_by_admin(self, admin_client, db):
        from tests.models import Payment

        Payment.objects.create(amount=Decimal("10000"), status=PaymentStatus.PENDING)

        response = admin_client.get("/admin/tests/payment/dashboard/")
        assert response.status_code == 200

    def test_dashboard_contains_chart_data(self, admin_client, db):
        from tests.models import Payment

        Payment.objects.create(
            amount=Decimal("10000"),
            status=PaymentStatus.COMPLETED,
            paid_at=timezone.now(),
        )

        response = admin_client.get("/admin/tests/payment/dashboard/")
        content = response.content.decode("utf-8")

        assert "revenueTrendChart" in content
        assert "statusChart" in content
        assert "methodChart" in content

    def test_dashboard_respects_date_range_param(self, admin_client, db):
        response = admin_client.get("/admin/tests/payment/dashboard/?range=30d")
        assert response.status_code == 200
        assert response.context["date_range"] == "30d"


@pytest.mark.django_db
class TestDashboardAPI:
    def test_api_requires_authentication(self, client, db):
        response = client.get("/admin/tests/payment/dashboard/api/?range=7d")
        assert response.status_code == 302

    def test_api_returns_json(self, admin_client, db):
        response = admin_client.get("/admin/tests/payment/dashboard/api/?range=7d")
        assert response.status_code == 200
        assert response["Content-Type"] == "application/json"

    def test_api_contains_expected_structure(self, admin_client, db):
        response = admin_client.get("/admin/tests/payment/dashboard/api/?range=7d")
        data = response.json()

        assert "summary" in data
        assert "charts" in data
        assert "meta" in data

        assert "total_revenue" in data["summary"]
        assert "daily_trend" in data["charts"]
        assert "by_status" in data["charts"]
        assert "by_method" in data["charts"]

    @freeze_time("2026-01-15 12:00:00")
    def test_api_respects_date_range(self, admin_client, db):
        from tests.models import Payment

        Payment.objects.create(
            amount=Decimal("10000"),
            status=PaymentStatus.COMPLETED,
            paid_at=timezone.now(),
        )

        response = admin_client.get("/admin/tests/payment/dashboard/api/?range=today")
        data = response.json()

        assert data["meta"]["date_range"] == "today"
        assert data["summary"]["transaction_count"]["value"] == 1


@pytest.mark.django_db
class TestDRFSerializer:
    def test_serializer_validates_stats(self):
        from easypay.dashboard.serializers import DashboardStatsSerializer

        stats = {
            "summary": {
                "total_revenue": {
                    "value": 10000,
                    "formatted": "₩10,000",
                    "change": 5.0,
                    "trend": "up",
                },
                "transaction_count": {
                    "value": 1,
                    "formatted": "1건",
                    "change": None,
                    "trend": "neutral",
                },
                "average_value": {
                    "value": 10000,
                    "formatted": "₩10,000",
                    "change": 0.0,
                    "trend": "neutral",
                },
                "refund_count": {
                    "value": 0,
                    "formatted": "0건",
                    "change": None,
                    "trend": "neutral",
                },
            },
            "charts": {
                "daily_trend": [{"date": "2026-01-15", "revenue": 10000, "count": 1}],
                "by_status": [
                    {"status": "completed", "label": "결제완료", "count": 1, "color": "#4CAF50"}
                ],
                "by_method": [{"method": "11", "label": "카드", "count": 1, "revenue": 10000}],
            },
            "comparison": [
                {"label": "매출", "current": 10000, "previous": 8000},
                {"label": "건수", "current": 1, "previous": 1},
            ],
            "meta": {
                "date_range": "7d",
                "start_date": "2026-01-09",
                "end_date": "2026-01-15",
                "prev_start_date": "2026-01-02",
                "prev_end_date": "2026-01-08",
            },
        }

        serializer = DashboardStatsSerializer(data=stats)
        assert serializer.is_valid(), serializer.errors

    def test_serializer_rejects_invalid_trend(self):
        from easypay.dashboard.serializers import DashboardStatsSerializer

        stats = {
            "summary": {
                "total_revenue": {
                    "value": 10000,
                    "formatted": "₩10,000",
                    "change": 5.0,
                    "trend": "invalid",
                },
                "transaction_count": {
                    "value": 1,
                    "formatted": "1건",
                    "change": None,
                    "trend": "neutral",
                },
                "average_value": {
                    "value": 10000,
                    "formatted": "₩10,000",
                    "change": 0.0,
                    "trend": "neutral",
                },
                "refund_count": {
                    "value": 0,
                    "formatted": "0건",
                    "change": None,
                    "trend": "neutral",
                },
            },
            "charts": {
                "daily_trend": [],
                "by_status": [],
                "by_method": [],
            },
            "comparison": [],
            "meta": {
                "date_range": "7d",
                "start_date": "2026-01-09",
                "end_date": "2026-01-15",
                "prev_start_date": "2026-01-02",
                "prev_end_date": "2026-01-08",
            },
        }

        serializer = DashboardStatsSerializer(data=stats)
        assert not serializer.is_valid()
        assert "summary" in serializer.errors


class TestDRFAPIView:
    def test_drf_api_view_exists(self):
        from easypay.dashboard.api import HAS_DRF, DashboardAPIView

        assert HAS_DRF is True
        assert DashboardAPIView is not None

    def test_create_dashboard_api_view_returns_drf_view(self):
        from easypay.dashboard.api import create_dashboard_api_view

        def get_queryset():
            from tests.models import Payment

            return Payment.objects.all()

        view = create_dashboard_api_view(get_queryset)
        assert view is not None


@pytest.mark.django_db
class TestCSVExport:
    def test_export_requires_authentication(self, client, db):
        response = client.get("/admin/tests/payment/dashboard/export/?range=7d")
        assert response.status_code == 302

    @freeze_time("2026-01-15 12:00:00")
    def test_export_returns_csv(self, admin_client, db):
        from tests.models import Payment

        Payment.objects.create(
            amount=10000,
            status=PaymentStatus.COMPLETED,
            paid_at=timezone.now(),
        )

        response = admin_client.get("/admin/tests/payment/dashboard/export/?range=7d")
        assert response.status_code == 200
        assert response["Content-Type"] == "text/csv; charset=utf-8-sig"
        assert "attachment" in response["Content-Disposition"]

    @freeze_time("2026-01-15 12:00:00")
    def test_export_contains_headers(self, admin_client, db):
        response = admin_client.get("/admin/tests/payment/dashboard/export/?range=7d")
        content = response.content.decode("utf-8-sig")
        assert "ID" in content
        assert "주문번호" in content
        assert "금액" in content
        assert "상태" in content

    @freeze_time("2026-01-15 12:00:00")
    def test_export_respects_date_range(self, admin_client, db):
        from tests.models import Payment

        Payment.objects.create(
            amount=10000,
            status=PaymentStatus.COMPLETED,
            paid_at=timezone.now(),
        )
        Payment.objects.create(
            amount=50000,
            status=PaymentStatus.COMPLETED,
            paid_at=timezone.now() - timedelta(days=30),
        )

        response = admin_client.get("/admin/tests/payment/dashboard/export/?range=7d")
        content = response.content.decode("utf-8-sig")
        assert "10000" in content
        assert "50000" not in content

    @freeze_time("2026-01-15 12:00:00")
    def test_export_custom_range(self, admin_client, db):
        from tests.models import Payment

        Payment.objects.create(
            amount=10000,
            status=PaymentStatus.COMPLETED,
            paid_at=timezone.now() - timedelta(days=5),
        )

        response = admin_client.get(
            "/admin/tests/payment/dashboard/export/?range=custom&start_date=2026-01-05&end_date=2026-01-15"
        )
        assert response.status_code == 200
        content = response.content.decode("utf-8-sig")
        assert "10000" in content


@pytest.mark.django_db
class TestComparisonData:
    @freeze_time("2026-01-15 12:00:00")
    def test_comparison_data_included(self, db):
        from tests.models import Payment

        Payment.objects.create(
            amount=10000,
            status=PaymentStatus.COMPLETED,
            paid_at=timezone.now(),
        )

        stats = get_dashboard_statistics(Payment.objects.all(), "7d")
        assert "comparison" in stats
        assert len(stats["comparison"]) == 4

    @freeze_time("2026-01-15 12:00:00")
    def test_comparison_labels(self, db):
        from tests.models import Payment

        stats = get_dashboard_statistics(Payment.objects.all(), "7d")
        labels = [c["label"] for c in stats["comparison"]]
        assert "매출" in labels
        assert "건수" in labels
        assert "평균금액" in labels
        assert "환불/취소" in labels

    @freeze_time("2026-01-15 12:00:00")
    def test_comparison_has_current_and_previous(self, db):
        from tests.models import Payment

        Payment.objects.create(
            amount=10000,
            status=PaymentStatus.COMPLETED,
            paid_at=timezone.now(),
        )
        Payment.objects.create(
            amount=5000,
            status=PaymentStatus.COMPLETED,
            paid_at=timezone.now() - timedelta(days=10),
        )

        stats = get_dashboard_statistics(Payment.objects.all(), "7d")
        revenue_comparison = next(c for c in stats["comparison"] if c["label"] == "매출")
        assert revenue_comparison["current"] == 10000
        assert revenue_comparison["previous"] == 5000

    @freeze_time("2026-01-15 12:00:00")
    def test_meta_includes_prev_dates(self, db):
        from tests.models import Payment

        stats = get_dashboard_statistics(Payment.objects.all(), "7d")
        assert "prev_start_date" in stats["meta"]
        assert "prev_end_date" in stats["meta"]
        assert stats["meta"]["prev_start_date"] == "2026-01-02"
        assert stats["meta"]["prev_end_date"] == "2026-01-08"
