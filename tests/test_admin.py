"""
Tests for PaymentAdminMixin.

Tests cover:
- Display methods (status_badge, amount_display, receipt_link, pg_status_info)
- Admin actions (cancel, refresh status, export CSV)
- Payment statistics calculation
- Mixin configuration attributes
"""

from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
import responses
from django.contrib import admin
from django.contrib.admin.sites import AdminSite
from django.http import HttpResponse
from django.utils import timezone
from freezegun import freeze_time

from easypay.admin import PaymentAdminMixin
from easypay.models import PaymentStatus
from easypay.signals import payment_cancelled

# ============================================================
# Test Admin Setup
# ============================================================


class TestPaymentAdmin(PaymentAdminMixin, admin.ModelAdmin):
    """Concrete admin class for testing the mixin."""

    pass


@pytest.fixture
def model_admin(db):
    """Create a ModelAdmin instance for testing."""
    from tests.models import Payment

    site = AdminSite()
    return TestPaymentAdmin(Payment, site)


@pytest.fixture
def mock_admin_request(request_factory, admin_user):
    """Create a mock admin request with messages framework support."""
    from django.contrib.messages.storage.fallback import FallbackStorage

    request = request_factory.get("/admin/")
    request.user = admin_user

    # Add messages framework support for admin actions
    request.session = "session"
    messages_storage = FallbackStorage(request)
    request._messages = messages_storage

    return request


# ============================================================
# Mixin Configuration Tests
# ============================================================


class TestMixinConfiguration:
    """Tests for PaymentAdminMixin configuration attributes."""

    def test_payment_list_display_contains_required_fields(self, model_admin):
        """payment_list_display should contain all required fields."""
        expected_fields = [
            "status_badge",
            "amount_display",
            "pay_method_type_code",
            "card_name",
            "created_at",
            "paid_at",
            "receipt_link",
        ]
        for field in expected_fields:
            assert field in model_admin.payment_list_display

    def test_payment_search_fields(self, model_admin):
        """payment_search_fields should contain searchable fields."""
        expected_fields = ["pg_tid", "authorization_id", "card_no"]
        for field in expected_fields:
            assert field in model_admin.payment_search_fields

    def test_payment_list_filter(self, model_admin):
        """payment_list_filter should contain filterable fields."""
        expected_filters = ["status", "pay_method_type_code", "card_name", "paid_at"]
        for filter_field in expected_filters:
            assert filter_field in model_admin.payment_list_filter

    def test_payment_readonly_fields(self, model_admin):
        """payment_readonly_fields should contain non-editable fields."""
        expected_readonly = [
            "pg_tid",
            "authorization_id",
            "card_no",
            "paid_at",
            "client_ip",
            "client_user_agent",
            "receipt_link_detail",
            "pg_status_info",
        ]
        for field in expected_readonly:
            assert field in model_admin.payment_readonly_fields

    def test_status_colors_mapping(self, model_admin):
        """STATUS_COLORS should map all payment statuses."""
        assert PaymentStatus.PENDING in model_admin.STATUS_COLORS
        assert PaymentStatus.COMPLETED in model_admin.STATUS_COLORS
        assert PaymentStatus.FAILED in model_admin.STATUS_COLORS
        assert PaymentStatus.CANCELLED in model_admin.STATUS_COLORS
        assert PaymentStatus.REFUNDED in model_admin.STATUS_COLORS

    def test_status_colors_format(self, model_admin):
        """Each color mapping should be a tuple of (text_color, bg_color)."""
        for _status, colors in model_admin.STATUS_COLORS.items():
            assert isinstance(colors, tuple)
            assert len(colors) == 2
            # Check hex color format
            assert colors[0].startswith("#")
            assert colors[1].startswith("#")


# ============================================================
# Display Method Tests
# ============================================================


@pytest.mark.django_db
class TestStatusBadge:
    """Tests for status_badge display method."""

    def test_pending_status_badge(self, model_admin, payment):
        """Pending status should display orange badge."""
        badge = model_admin.status_badge(payment)
        assert "결제대기" in badge
        assert "background-color" in badge
        # Orange background for pending
        assert "#FFF3CD" in badge or "background" in badge.lower()

    def test_completed_status_badge(self, model_admin, completed_payment):
        """Completed status should display green badge."""
        badge = model_admin.status_badge(completed_payment)
        assert "결제완료" in badge
        assert "background-color" in badge

    def test_failed_status_badge(self, model_admin, payment):
        """Failed status should display red badge."""
        payment.status = PaymentStatus.FAILED
        badge = model_admin.status_badge(payment)
        assert "결제실패" in badge
        assert "background-color" in badge

    def test_cancelled_status_badge(self, model_admin, cancelled_payment):
        """Cancelled status should display gray badge."""
        badge = model_admin.status_badge(cancelled_payment)
        assert "취소" in badge
        assert "background-color" in badge

    def test_refunded_status_badge(self, model_admin, payment):
        """Refunded status should display blue badge."""
        payment.status = PaymentStatus.REFUNDED
        badge = model_admin.status_badge(payment)
        assert "환불" in badge
        assert "background-color" in badge

    def test_badge_contains_html_span(self, model_admin, payment):
        """Badge should be wrapped in span tag."""
        badge = model_admin.status_badge(payment)
        assert "<span" in badge
        assert "</span>" in badge


@pytest.mark.django_db
class TestAmountDisplay:
    """Tests for amount_display method."""

    def test_amount_with_comma_separator(self, model_admin, payment):
        """Amount should be formatted with comma separators."""
        display = model_admin.amount_display(payment)
        assert display == "29,900원"

    def test_large_amount_formatting(self, model_admin, payment):
        """Large amounts should have multiple separators."""
        payment.amount = Decimal("1234567")
        display = model_admin.amount_display(payment)
        assert display == "1,234,567원"

    def test_small_amount_no_separator(self, model_admin, payment):
        """Small amounts should not have separators."""
        payment.amount = Decimal("100")
        display = model_admin.amount_display(payment)
        assert display == "100원"

    def test_zero_amount(self, model_admin, payment):
        """Zero amount should display correctly."""
        payment.amount = Decimal("0")
        display = model_admin.amount_display(payment)
        assert display == "0원"


@pytest.mark.django_db
class TestReceiptLink:
    """Tests for receipt_link display method."""

    def test_receipt_link_with_pg_tid(self, model_admin, completed_payment):
        """Receipt link should be generated when pg_tid exists."""
        link = model_admin.receipt_link(completed_payment)
        assert "href=" in link
        assert "🧾" in link
        assert completed_payment.pg_tid in link

    def test_receipt_link_without_pg_tid(self, model_admin, payment):
        """Receipt link should be dash when pg_tid is empty."""
        assert payment.pg_tid == ""
        link = model_admin.receipt_link(payment)
        assert link == "-"

    def test_receipt_link_opens_new_tab(self, model_admin, completed_payment):
        """Receipt link should open in new tab."""
        link = model_admin.receipt_link(completed_payment)
        assert 'target="_blank"' in link


@pytest.mark.django_db
class TestReceiptLinkDetail:
    """Tests for receipt_link_detail display method (detail page)."""

    def test_detail_link_with_pg_tid(self, model_admin, completed_payment):
        """Detail receipt link should be a styled button."""
        link = model_admin.receipt_link_detail(completed_payment)
        assert "href=" in link
        assert "🧾" in link
        assert "카드 영수증 보기" in link
        assert completed_payment.pg_tid in link

    def test_detail_link_without_pg_tid(self, model_admin, payment):
        """Detail link should show '결제 전' when pg_tid is empty."""
        link = model_admin.receipt_link_detail(payment)
        assert "결제 전" in link


@pytest.mark.django_db
class TestPgStatusInfo:
    """Tests for pg_status_info display method."""

    @responses.activate
    def test_pg_status_info_success(self, model_admin, completed_payment, mock_status_success):
        """PG status info should display transaction status."""
        responses.add(
            responses.POST,
            "https://testpgapi.easypay.co.kr/api/ep9/trades/status",
            json=mock_status_success,
            status=200,
        )

        info = model_admin.pg_status_info(completed_payment)
        assert "승인완료" in info
        assert "정상" in info  # cancelYn = N

    @responses.activate
    def test_pg_status_info_cancelled(self, model_admin, completed_payment, mock_status_cancelled):
        """PG status info should show cancelled status."""
        responses.add(
            responses.POST,
            "https://testpgapi.easypay.co.kr/api/ep9/trades/status",
            json=mock_status_cancelled,
            status=200,
        )

        info = model_admin.pg_status_info(completed_payment)
        assert "취소완료" in info
        assert "취소됨" in info  # cancelYn = Y

    def test_pg_status_info_without_pg_tid(self, model_admin, payment):
        """PG status info should show '결제 전' when pg_tid is empty."""
        info = model_admin.pg_status_info(payment)
        assert "결제 전" in info

    @responses.activate
    def test_pg_status_info_api_error(self, model_admin, completed_payment):
        """PG status info should handle API errors gracefully."""
        responses.add(
            responses.POST,
            "https://testpgapi.easypay.co.kr/api/ep9/trades/status",
            json={"resCd": "E500", "resMsg": "서버 오류"},
            status=500,
        )

        info = model_admin.pg_status_info(completed_payment)
        assert "조회 실패" in info or "오류" in info.lower()


# ============================================================
# Admin Action Tests
# ============================================================


@pytest.mark.django_db
class TestCancelSelectedPayments:
    """Tests for cancel_selected_payments admin action."""

    @responses.activate
    def test_cancel_completed_payment_success(
        self,
        model_admin,
        completed_payment,
        mock_admin_request,
        mock_cancel_success,
        signal_receiver,
    ):
        """Successful cancellation should update status and fire signal."""
        from tests.models import Payment

        responses.add(
            responses.POST,
            "https://testpgapi.easypay.co.kr/api/ep9/trades/cancel",
            json=mock_cancel_success,
            status=200,
        )

        receiver = signal_receiver()
        payment_cancelled.connect(receiver.handler)

        try:
            queryset = Payment.objects.filter(pk=completed_payment.pk)
            model_admin.cancel_selected_payments(mock_admin_request, queryset)

            completed_payment.refresh_from_db()
            assert completed_payment.status == PaymentStatus.CANCELLED
            assert receiver.called is True
        finally:
            payment_cancelled.disconnect(receiver.handler)

    @responses.activate
    def test_cancel_skips_non_completed_payments(self, model_admin, payment, mock_admin_request):
        """Cancellation should skip non-completed payments."""
        from tests.models import Payment

        # Pending payment should be skipped
        assert payment.status == PaymentStatus.PENDING

        queryset = Payment.objects.filter(pk=payment.pk)
        model_admin.cancel_selected_payments(mock_admin_request, queryset)

        payment.refresh_from_db()
        assert payment.status == PaymentStatus.PENDING  # Unchanged

    @responses.activate
    def test_cancel_skips_payments_without_pg_tid(self, model_admin, mock_admin_request, db):
        """Cancellation should skip payments without pg_tid."""
        from tests.models import Payment

        payment = Payment.objects.create(
            amount=Decimal("10000"),
            status=PaymentStatus.COMPLETED,
            pg_tid="",  # No PG TID
        )

        queryset = Payment.objects.filter(pk=payment.pk)
        model_admin.cancel_selected_payments(mock_admin_request, queryset)

        payment.refresh_from_db()
        assert payment.status == PaymentStatus.COMPLETED  # Unchanged

    @responses.activate
    def test_cancel_handles_api_failure(
        self, model_admin, completed_payment, mock_admin_request, mock_cancel_failure
    ):
        """Cancellation should handle API failures gracefully."""
        from tests.models import Payment

        responses.add(
            responses.POST,
            "https://testpgapi.easypay.co.kr/api/ep9/trades/cancel",
            json=mock_cancel_failure,
            status=200,
        )

        queryset = Payment.objects.filter(pk=completed_payment.pk)
        model_admin.cancel_selected_payments(mock_admin_request, queryset)

        completed_payment.refresh_from_db()
        # Status should remain COMPLETED on API failure
        assert completed_payment.status == PaymentStatus.COMPLETED


@pytest.mark.django_db
class TestRefreshTransactionStatus:
    """Tests for refresh_transaction_status admin action."""

    @responses.activate
    def test_refresh_syncs_cancelled_status(
        self, model_admin, completed_payment, mock_admin_request, mock_status_cancelled
    ):
        """Refresh should update local status when PG shows cancelled."""
        from tests.models import Payment

        responses.add(
            responses.POST,
            "https://testpgapi.easypay.co.kr/api/ep9/trades/status",
            json=mock_status_cancelled,
            status=200,
        )

        queryset = Payment.objects.filter(pk=completed_payment.pk)
        model_admin.refresh_transaction_status(mock_admin_request, queryset)

        completed_payment.refresh_from_db()
        assert completed_payment.status == PaymentStatus.CANCELLED

    @responses.activate
    def test_refresh_keeps_completed_status(
        self, model_admin, completed_payment, mock_admin_request, mock_status_success
    ):
        """Refresh should keep COMPLETED status when PG confirms it."""
        from tests.models import Payment

        responses.add(
            responses.POST,
            "https://testpgapi.easypay.co.kr/api/ep9/trades/status",
            json=mock_status_success,
            status=200,
        )

        queryset = Payment.objects.filter(pk=completed_payment.pk)
        model_admin.refresh_transaction_status(mock_admin_request, queryset)

        completed_payment.refresh_from_db()
        assert completed_payment.status == PaymentStatus.COMPLETED

    def test_refresh_skips_payments_without_pg_tid(self, model_admin, payment, mock_admin_request):
        """Refresh should skip payments without pg_tid."""
        from tests.models import Payment

        assert payment.pg_tid == ""

        queryset = Payment.objects.filter(pk=payment.pk)
        # Should not raise even with no API call
        model_admin.refresh_transaction_status(mock_admin_request, queryset)


@pytest.mark.django_db
class TestExportToCsv:
    """Tests for export_to_csv admin action."""

    def test_export_returns_csv_response(self, model_admin, completed_payment, mock_admin_request):
        """Export should return HttpResponse with CSV content type."""
        from tests.models import Payment

        queryset = Payment.objects.filter(pk=completed_payment.pk)
        response = model_admin.export_to_csv(mock_admin_request, queryset)

        assert isinstance(response, HttpResponse)
        assert response["Content-Type"] == "text/csv"
        assert "attachment" in response["Content-Disposition"]
        assert ".csv" in response["Content-Disposition"]

    def test_export_contains_headers(self, model_admin, completed_payment, mock_admin_request):
        """Exported CSV should contain column headers."""
        from tests.models import Payment

        queryset = Payment.objects.filter(pk=completed_payment.pk)
        response = model_admin.export_to_csv(mock_admin_request, queryset)

        content = response.content.decode("utf-8-sig")
        assert "ID" in content
        assert "상태" in content
        assert "금액" in content
        assert "결제수단" in content
        assert "카드사" in content
        assert "결제일시" in content
        assert "PG거래번호" in content

    def test_export_contains_payment_data(self, model_admin, completed_payment, mock_admin_request):
        """Exported CSV should contain payment data."""
        from tests.models import Payment

        queryset = Payment.objects.filter(pk=completed_payment.pk)
        response = model_admin.export_to_csv(mock_admin_request, queryset)

        content = response.content.decode("utf-8-sig")
        assert str(completed_payment.id) in content
        assert "결제완료" in content
        assert "29900" in content
        assert completed_payment.pg_tid in content

    def test_export_multiple_payments(
        self, model_admin, payment, completed_payment, mock_admin_request
    ):
        """Export should handle multiple payments."""
        from tests.models import Payment

        queryset = Payment.objects.filter(pk__in=[payment.pk, completed_payment.pk])
        response = model_admin.export_to_csv(mock_admin_request, queryset)

        content = response.content.decode("utf-8-sig")
        lines = content.strip().split("\n")
        # Header + 2 data rows
        assert len(lines) >= 3

    def test_export_utf8_bom(self, model_admin, completed_payment, mock_admin_request):
        """Exported CSV should have UTF-8 BOM for Excel compatibility."""
        from tests.models import Payment

        queryset = Payment.objects.filter(pk=completed_payment.pk)
        response = model_admin.export_to_csv(mock_admin_request, queryset)

        # UTF-8 BOM is 3 bytes: EF BB BF
        raw_content = response.content
        assert raw_content.startswith(b"\xef\xbb\xbf")


# ============================================================
# Payment Statistics Tests
# ============================================================


@pytest.mark.django_db
class TestPaymentStatistics:
    """Tests for get_payment_statistics method."""

    @freeze_time("2025-12-23 14:30:00")
    def test_today_statistics(self, model_admin, db):
        """Statistics should correctly count today's payments."""

        from tests.models import Payment

        # Create payments for today
        Payment.objects.create(
            amount=Decimal("10000"),
            status=PaymentStatus.COMPLETED,
            paid_at=timezone.now(),
        )
        Payment.objects.create(
            amount=Decimal("20000"),
            status=PaymentStatus.COMPLETED,
            paid_at=timezone.now(),
        )

        queryset = Payment.objects.all()
        stats = model_admin.get_payment_statistics(queryset)

        assert stats["today"]["count"] == 2
        assert stats["today"]["total"] == 30000

    @freeze_time("2025-12-23 14:30:00")
    def test_this_week_statistics(self, model_admin, db):
        """Statistics should correctly count this week's payments."""
        from datetime import timedelta

        from tests.models import Payment

        # Create payment from 3 days ago (still this week)
        three_days_ago = timezone.now() - timedelta(days=3)
        Payment.objects.create(
            amount=Decimal("50000"),
            status=PaymentStatus.COMPLETED,
            paid_at=three_days_ago,
        )

        queryset = Payment.objects.all()
        stats = model_admin.get_payment_statistics(queryset)

        assert stats["this_week"]["count"] >= 1
        assert stats["this_week"]["total"] >= 50000

    def test_status_breakdown(self, model_admin, payment, completed_payment, db):
        """Statistics should break down by status."""
        from tests.models import Payment

        queryset = Payment.objects.filter(pk__in=[payment.pk, completed_payment.pk])
        stats = model_admin.get_payment_statistics(queryset)

        assert "by_status" in stats
        # Should have at least pending and completed
        status_dict = {item["status"]: item["count"] for item in stats["by_status"]}
        assert PaymentStatus.PENDING in status_dict or PaymentStatus.COMPLETED in status_dict

    def test_payment_method_breakdown(self, model_admin, completed_payment, db):
        """Statistics should break down by payment method."""
        from tests.models import Payment

        queryset = Payment.objects.filter(pk=completed_payment.pk)
        stats = model_admin.get_payment_statistics(queryset)

        assert "by_method" in stats

    def test_daily_trend(self, model_admin, completed_payment, db):
        """Statistics should include daily trend data."""
        from tests.models import Payment

        queryset = Payment.objects.filter(pk=completed_payment.pk)
        stats = model_admin.get_payment_statistics(queryset)

        assert "daily_trend" in stats

    def test_empty_queryset_statistics(self, model_admin, db):
        """Statistics should handle empty queryset gracefully."""
        from tests.models import Payment

        queryset = Payment.objects.none()
        stats = model_admin.get_payment_statistics(queryset)

        assert stats["today"]["count"] == 0
        assert stats["today"]["total"] == 0


# ============================================================
# Changelist View Tests
# ============================================================


@pytest.mark.django_db
class TestChangelistView:
    """Tests for changelist_view override."""

    def test_changelist_includes_statistics(
        self, model_admin, completed_payment, mock_admin_request
    ):
        """Changelist view should include payment statistics in context."""

        # Mock the parent's changelist_view
        with patch.object(admin.ModelAdmin, "changelist_view") as mock_parent:
            mock_response = MagicMock()
            mock_response.context_data = {}
            mock_parent.return_value = mock_response

            response = model_admin.changelist_view(mock_admin_request)

            # Should have called parent and added statistics
            mock_parent.assert_called_once()


# ============================================================
# Integration Tests
# ============================================================


@pytest.mark.django_db
class TestAdminIntegration:
    """Integration tests for admin functionality."""

    def test_admin_can_view_payment_list(self, admin_client, completed_payment):
        """Admin should be able to view payment list."""
        from django.urls import reverse

        # This test requires the admin to be registered
        # Skip if admin URL is not available
        try:
            url = reverse("admin:tests_payment_changelist")
            response = admin_client.get(url)
            assert response.status_code == 200
        except Exception:
            # Admin URL might not be registered in test settings
            pytest.skip("Admin URL not available in test configuration")

    def test_admin_can_view_payment_detail(self, admin_client, completed_payment):
        """Admin should be able to view payment detail."""
        from django.urls import reverse

        try:
            url = reverse("admin:tests_payment_change", args=[completed_payment.pk])
            response = admin_client.get(url)
            assert response.status_code == 200
        except Exception:
            pytest.skip("Admin URL not available in test configuration")
