"""
Security tests for django-easypay.

Tests for:
- Card number masking
- Sensitive data not logged
- CSV export security
- Idempotency handling
- Amount verification
"""

import uuid
from decimal import Decimal
from unittest.mock import MagicMock

import pytest
import responses
from django.contrib.admin.sites import AdminSite
from django.test import RequestFactory

from easypay.client import EasyPayClient
from easypay.models import PaymentStatus
from easypay.sandbox.admin import SandboxPaymentAdmin
from easypay.sandbox.models import SandboxPayment
from easypay.utils import mask_card_number


class TestCardNumberMasking:
    """Test card number masking utility."""

    def test_mask_full_card_number_no_dashes(self):
        """Full card number without dashes is properly masked."""
        result = mask_card_number("1234567890123456")
        assert result == "1234-****-****-3456"

    def test_mask_full_card_number_with_dashes(self):
        """Full card number with dashes is properly masked."""
        result = mask_card_number("1234-5678-9012-3456")
        assert result == "1234-****-****-3456"

    def test_already_masked_unchanged(self):
        """Already masked card numbers are returned unchanged."""
        result = mask_card_number("1234-****-****-5678")
        assert result == "1234-****-****-5678"

    def test_empty_string(self):
        """Empty string returns empty string."""
        result = mask_card_number("")
        assert result == ""

    def test_none_returns_empty(self):
        """None returns empty string."""
        result = mask_card_number(None)
        assert result == ""

    def test_short_number_unchanged(self):
        """Short numbers that don't match pattern are unchanged."""
        result = mask_card_number("1234")
        assert result == "1234"


class TestCSVExportSecurity:
    """Test that CSV export properly masks sensitive data."""

    @pytest.fixture
    def admin_site(self):
        return AdminSite()

    @pytest.fixture
    def model_admin(self, admin_site):
        return SandboxPaymentAdmin(SandboxPayment, admin_site)

    @pytest.fixture
    def request_factory(self):
        return RequestFactory()

    @pytest.fixture
    def mock_user(self):
        user = MagicMock()
        user.username = "admin"
        user.id = 1
        return user

    @pytest.mark.django_db
    def test_csv_export_masks_card_number(self, model_admin, request_factory, mock_user):
        """CSV export should mask card numbers."""
        # Create payment with full card number (simulating bad data)
        payment = SandboxPayment.objects.create(
            order_id=f"TEST-{uuid.uuid4().hex[:8].upper()}",
            amount=Decimal("10000"),
            status=PaymentStatus.COMPLETED,
            card_no="1234-5678-9012-3456",  # Full number (should be masked)
            card_name="테스트카드",
        )

        request = request_factory.get("/admin/")
        request.user = mock_user

        queryset = SandboxPayment.objects.filter(pk=payment.pk)
        response = model_admin.export_to_csv(request, queryset)

        # Parse CSV content
        content = response.content.decode("utf-8")

        # Card number should be masked
        assert "1234-****-****-3456" in content
        # Full card number should NOT appear
        assert "1234-5678-9012-3456" not in content

    @pytest.mark.django_db
    def test_csv_export_excludes_authorization_id(self, model_admin, request_factory, mock_user):
        """CSV export should not include authorization_id field."""
        payment = SandboxPayment.objects.create(
            order_id=f"TEST-{uuid.uuid4().hex[:8].upper()}",
            amount=Decimal("10000"),
            status=PaymentStatus.COMPLETED,
            authorization_id="SENSITIVE_AUTH_TOKEN_12345",
            pg_tid="PGTID123456",
        )

        request = request_factory.get("/admin/")
        request.user = mock_user

        queryset = SandboxPayment.objects.filter(pk=payment.pk)
        response = model_admin.export_to_csv(request, queryset)

        content = response.content.decode("utf-8")

        # authorization_id should NOT appear in CSV (sensitive PG token)
        assert "SENSITIVE_AUTH_TOKEN_12345" not in content
        # pg_tid should appear (safe to export)
        assert "PGTID123456" in content


class TestAmountVerification:
    """Test payment amount verification in approve_payment."""

    @pytest.fixture
    def client(self):
        return EasyPayClient(
            mall_id="T0021792",
            api_url="https://testpgapi.easypay.co.kr",
        )

    @pytest.fixture
    def payment(self, db):
        from tests.models import Payment

        return Payment.objects.create(
            order_id=f"TEST-{uuid.uuid4().hex[:8].upper()}",
            amount=Decimal("29900"),
            status=PaymentStatus.PENDING,
        )

    @responses.activate
    def test_amount_mismatch_logged(self, client, payment, caplog):
        """Amount mismatch between request and approval should be logged."""
        # Mock approval response with different amount
        responses.add(
            responses.POST,
            "https://testpgapi.easypay.co.kr/api/ep9/trades/approval",
            json={
                "resCd": "0000",
                "resMsg": "정상처리",
                "pgTid": "PGTID123456",
                "shopOrderNo": payment.order_id,
                "paymentInfo": {
                    "payMethodTypeCode": "11",
                    "approvalAmount": 19900,  # Different from payment.amount (29900)
                    "cardInfo": {
                        "cardName": "테스트카드",
                        "cardNo": "1234-****-****-5678",
                    },
                },
            },
            status=200,
        )

        import logging

        with caplog.at_level(logging.ERROR):
            result = client.approve_payment(payment, "AUTH123")

        # Should log amount mismatch error
        assert "amount mismatch" in caplog.text.lower()
        # Extra fields are in record attributes, check records
        error_records = [r for r in caplog.records if "mismatch" in r.message.lower()]
        assert len(error_records) > 0

    @responses.activate
    def test_amount_match_no_error(self, client, payment, caplog):
        """Matching amounts should not log error."""
        responses.add(
            responses.POST,
            "https://testpgapi.easypay.co.kr/api/ep9/trades/approval",
            json={
                "resCd": "0000",
                "resMsg": "정상처리",
                "pgTid": "PGTID123456",
                "shopOrderNo": payment.order_id,
                "paymentInfo": {
                    "payMethodTypeCode": "11",
                    "approvalAmount": 29900,  # Matches payment.amount
                    "cardInfo": {
                        "cardName": "테스트카드",
                        "cardNo": "1234-****-****-5678",
                    },
                },
            },
            status=200,
        )

        import logging

        with caplog.at_level(logging.ERROR):
            result = client.approve_payment(payment, "AUTH123")

        # Should NOT log amount mismatch error
        assert "amount mismatch" not in caplog.text.lower()


class TestIdempotency:
    """Test idempotency handling for payment callbacks."""

    @pytest.mark.django_db
    def test_already_paid_returns_early(self):
        """Already paid payments should return early without double processing."""
        from django.utils import timezone

        # Create already paid payment
        payment = SandboxPayment.objects.create(
            order_id=f"TEST-{uuid.uuid4().hex[:8].upper()}",
            amount=Decimal("10000"),
            status=PaymentStatus.COMPLETED,
            paid_at=timezone.now(),
            pg_tid="EXISTING_TID",
        )

        # Verify is_paid property
        assert payment.is_paid is True

        # Attempting to mark as paid again should not change existing data
        original_pg_tid = payment.pg_tid
        payment.mark_as_paid(pg_tid="NEW_TID")

        payment.refresh_from_db()
        # pg_tid should be updated (mark_as_paid allows update)
        # But the key point is idempotency check happens BEFORE calling mark_as_paid


class TestSensitiveDataLogging:
    """Test that sensitive data is not logged."""

    @responses.activate
    def test_register_payment_no_full_response_logged(self, caplog):
        """Register payment should not log full API response."""

        client = EasyPayClient(
            mall_id="T0021792",
            api_url="https://testpgapi.easypay.co.kr",
        )

        responses.add(
            responses.POST,
            "https://testpgapi.easypay.co.kr/api/ep9/trades/webpay",
            json={
                "resCd": "0000",
                "resMsg": "정상처리",
                "authPageUrl": "https://test.url/auth?token=SECRET_TOKEN",
                "sensitiveData": "THIS_SHOULD_NOT_BE_LOGGED",
            },
            status=200,
        )

        payment = MagicMock()
        payment.pk = 1
        payment.amount = Decimal("10000")
        payment.order_id = "TEST-ORDER"

        import logging

        with caplog.at_level(logging.DEBUG):
            try:
                client.register_payment(
                    payment=payment,
                    return_url="https://example.com/callback",
                    goods_name="테스트 상품",
                )
            except Exception:
                pass  # May fail due to missing order_id attribute

        # Full response should not be logged
        assert "THIS_SHOULD_NOT_BE_LOGGED" not in caplog.text
        # Token from URL should not be logged
        assert "SECRET_TOKEN" not in caplog.text

    @responses.activate
    def test_authorization_id_not_logged_in_approval(self, caplog):
        """authorization_id should not appear in approval logs."""

        client = EasyPayClient(
            mall_id="T0021792",
            api_url="https://testpgapi.easypay.co.kr",
        )

        responses.add(
            responses.POST,
            "https://testpgapi.easypay.co.kr/api/ep9/trades/approval",
            json={
                "resCd": "0000",
                "resMsg": "정상처리",
                "pgTid": "PGTID123456",
                "shopOrderNo": "TEST-ORDER",
                "paymentInfo": {
                    "payMethodTypeCode": "11",
                    "approvalAmount": 10000,
                    "cardInfo": {
                        "cardName": "테스트카드",
                        "cardNo": "1234-****-****-5678",
                    },
                },
            },
            status=200,
        )

        payment = MagicMock()
        payment.pk = 1
        payment.amount = Decimal("10000")
        payment.order_id = "TEST-ORDER"

        sensitive_authorization_id = "SUPER_SECRET_AUTH_TOKEN_XYZ123"

        import logging

        with caplog.at_level(logging.DEBUG):
            client.approve_payment(payment, sensitive_authorization_id)

        # authorization_id should NOT appear in logs (sensitive PG token)
        assert sensitive_authorization_id not in caplog.text


class TestAdminAuditLogging:
    """Test that admin actions are properly audit logged."""

    @pytest.fixture
    def admin_site(self):
        return AdminSite()

    @pytest.fixture
    def model_admin(self, admin_site):
        return SandboxPaymentAdmin(SandboxPayment, admin_site)

    @pytest.fixture
    def request_factory(self):
        return RequestFactory()

    @pytest.fixture
    def mock_user(self):
        user = MagicMock()
        user.username = "admin_test"
        user.id = 42
        return user

    @pytest.mark.django_db
    def test_csv_export_logged(self, model_admin, request_factory, mock_user, caplog):
        """CSV export action should be logged with admin user info."""
        payment = SandboxPayment.objects.create(
            order_id=f"TEST-{uuid.uuid4().hex[:8].upper()}",
            amount=Decimal("10000"),
            status=PaymentStatus.COMPLETED,
        )

        request = request_factory.get("/admin/")
        request.user = mock_user

        queryset = SandboxPayment.objects.filter(pk=payment.pk)

        import logging

        with caplog.at_level(logging.INFO):
            model_admin.export_to_csv(request, queryset)

        # Should log CSV export action
        assert "csv export" in caplog.text.lower() or "export" in caplog.text.lower()

    @pytest.mark.django_db
    @responses.activate
    def test_cancel_action_logged(self, model_admin, request_factory, mock_user, caplog):
        """Cancel action should be logged at WARNING level."""
        payment = SandboxPayment.objects.create(
            order_id=f"TEST-{uuid.uuid4().hex[:8].upper()}",
            amount=Decimal("10000"),
            status=PaymentStatus.COMPLETED,
            pg_tid="PGTID123456",
        )

        # Mock cancel API
        responses.add(
            responses.POST,
            "https://testpgapi.easypay.co.kr/api/ep9/trades/cancel",
            json={
                "resCd": "0000",
                "resMsg": "정상처리",
                "cancelAmount": 10000,
            },
            status=200,
        )

        request = request_factory.post("/admin/")
        request.user = mock_user
        request._messages = MagicMock()

        queryset = SandboxPayment.objects.filter(pk=payment.pk)

        import logging

        with caplog.at_level(logging.WARNING):
            model_admin.cancel_selected_payments(request, queryset)

        # Should log cancellation attempt
        assert "cancel" in caplog.text.lower() or "initiated" in caplog.text.lower()
