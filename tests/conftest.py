"""
pytest fixtures for django-easypay tests.

Provides reusable test fixtures for:
- Payment model instances
- Mock HTTP requests
- Mock Django requests
- EasyPay API response mocks
"""

import uuid
from decimal import Decimal
from unittest.mock import MagicMock

import pytest
import responses
from django.test import RequestFactory

from easypay.client import EasyPayClient
from easypay.models import PaymentStatus


@pytest.fixture
def payment(db):
    """Create a test payment instance."""
    from tests.models import Payment

    return Payment.objects.create(
        amount=Decimal("29900"),
        status=PaymentStatus.PENDING,
        order_id=f"TEST-{uuid.uuid4().hex[:8].upper()}",
        description="Test payment fixture",
    )


@pytest.fixture
def completed_payment(db):
    """Create a completed payment with PG data."""
    from django.utils import timezone

    from tests.models import Payment

    return Payment.objects.create(
        amount=Decimal("29900"),
        status=PaymentStatus.COMPLETED,
        order_id=f"TEST-{uuid.uuid4().hex[:8].upper()}",
        pg_tid="PGTID1234567890",
        authorization_id="AUTH1234567890",
        pay_method_type_code="11",
        card_name="신한카드",
        card_no="1234-****-****-5678",
        paid_at=timezone.now(),
        description="Completed payment fixture",
    )


@pytest.fixture
def cancelled_payment(db):
    """Create a cancelled payment."""
    from django.utils import timezone

    from tests.models import Payment

    return Payment.objects.create(
        amount=Decimal("29900"),
        status=PaymentStatus.CANCELLED,
        order_id=f"TEST-{uuid.uuid4().hex[:8].upper()}",
        pg_tid="PGTID1234567890",
        authorization_id="AUTH1234567890",
        paid_at=timezone.now(),
        description="Cancelled payment fixture",
    )


@pytest.fixture
def request_factory():
    """Django RequestFactory for creating mock requests."""
    return RequestFactory()


@pytest.fixture
def mock_request(request_factory):
    """Create a mock HTTP request with common headers."""
    request = request_factory.get("/")
    request.META["HTTP_USER_AGENT"] = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    request.META["REMOTE_ADDR"] = "192.168.1.100"
    return request


@pytest.fixture
def mock_mobile_request(request_factory):
    """Create a mock mobile HTTP request."""
    request = request_factory.get("/")
    request.META["HTTP_USER_AGENT"] = (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 14_0 like Mac OS X) AppleWebKit/605.1.15"
    )
    request.META["REMOTE_ADDR"] = "192.168.1.100"
    return request


@pytest.fixture
def mock_cloudflare_request(request_factory):
    """Create a mock request from CloudFlare."""
    request = request_factory.get("/")
    request.META["HTTP_CF_CONNECTING_IP"] = "203.0.113.50"
    request.META["HTTP_X_FORWARDED_FOR"] = "203.0.113.50, 172.16.0.1"
    request.META["REMOTE_ADDR"] = "172.16.0.1"
    return request


@pytest.fixture
def easypay_client():
    """Create an EasyPayClient instance for testing."""
    return EasyPayClient(
        mall_id="T0021792",
        api_url="https://testpgapi.easypay.co.kr",
        timeout=30,
    )


# ============================================================
# EasyPay API Response Mocks
# ============================================================


@pytest.fixture
def mock_register_success():
    """Mock successful payment registration response."""
    return {
        "resCd": "0000",
        "resMsg": "정상처리",
        "authPageUrl": "https://testpgapi.easypay.co.kr/webpay/auth?token=TEST_TOKEN",
        "mallId": "T0021792",
        "shopOrderNo": "TEST-ORDER-001",
    }


@pytest.fixture
def mock_register_failure():
    """Mock failed payment registration response."""
    return {
        "resCd": "E101",
        "resMsg": "필수 파라미터 누락",
    }


@pytest.fixture
def mock_approve_success():
    """Mock successful payment approval response."""
    return {
        "resCd": "0000",
        "resMsg": "정상처리",
        "pgTid": "PGTID1234567890123456789012",
        "shopOrderNo": "TEST-ORDER-001",
        "amount": 29900,
        "paymentInfo": {
            "payMethodTypeCode": "11",
            "cardInfo": {
                "cardName": "신한카드",
                "cardNo": "1234-****-****-5678",
                "installmentMonth": "00",
                "approvalNo": "12345678",
            },
        },
    }


@pytest.fixture
def mock_approve_failure():
    """Mock failed payment approval response."""
    return {
        "resCd": "E501",
        "resMsg": "승인 실패",
    }


@pytest.fixture
def mock_cancel_success():
    """Mock successful payment cancellation response."""
    return {
        "resCd": "0000",
        "resMsg": "정상처리",
        "pgTid": "PGTID1234567890123456789012",
        "cancelAmount": 29900,
        "cancelDate": "20251223",
        "cancelTime": "143000",
    }


@pytest.fixture
def mock_cancel_failure():
    """Mock failed payment cancellation response."""
    return {
        "resCd": "E601",
        "resMsg": "취소 실패: 이미 취소된 거래",
    }


@pytest.fixture
def mock_status_success():
    """Mock successful transaction status response."""
    return {
        "resCd": "0000",
        "resMsg": "정상처리",
        "pgTid": "PGTID1234567890123456789012",
        "shopOrderNo": "TEST-ORDER-001",
        "amount": 29900,
        "payStatusNm": "승인완료",
        "cancelYn": "N",
        "approvalDt": "2025-12-23 14:30:00",
    }


@pytest.fixture
def mock_status_cancelled():
    """Mock transaction status for cancelled payment."""
    return {
        "resCd": "0000",
        "resMsg": "정상처리",
        "pgTid": "PGTID1234567890123456789012",
        "shopOrderNo": "TEST-ORDER-001",
        "amount": 29900,
        "payStatusNm": "취소완료",
        "cancelYn": "Y",
        "approvalDt": "2025-12-23 14:30:00",
        "cancelDt": "2025-12-23 15:00:00",
    }


# ============================================================
# responses library helpers
# ============================================================


@pytest.fixture
def mocked_responses():
    """
    Activate responses mock for HTTP requests.

    Usage:
        def test_api(mocked_responses, mock_register_success):
            mocked_responses.add(
                responses.POST,
                "https://testpgapi.easypay.co.kr/api/ep9/trades/webpay",
                json=mock_register_success,
                status=200,
            )
            # ... test code
    """
    with responses.RequestsMock() as rsps:
        yield rsps


# ============================================================
# Admin Registration (for dashboard tests)
# ============================================================


def _register_test_payment_admin():
    from django.contrib import admin

    from easypay.admin import PaymentAdminMixin
    from easypay.dashboard import PaymentStatisticsMixin
    from tests.models import Payment

    if admin.site.is_registered(Payment):
        return

    @admin.register(Payment)
    class TestPaymentAdmin(PaymentStatisticsMixin, PaymentAdminMixin, admin.ModelAdmin):
        pass


_register_test_payment_admin()


# ============================================================
# Admin Test Fixtures
# ============================================================


@pytest.fixture
def admin_user(db):
    """Create an admin user for testing."""
    from django.contrib.auth import get_user_model

    User = get_user_model()
    return User.objects.create_superuser(
        username="admin",
        email="admin@test.com",
        password="adminpass123",
    )


@pytest.fixture
def admin_client(admin_user, client):
    """Create an authenticated admin client."""
    client.force_login(admin_user)
    return client


# ============================================================
# Signal Test Fixtures
# ============================================================


@pytest.fixture
def signal_receiver():
    """
    Factory for creating signal receivers that track calls.

    Usage:
        def test_signal(signal_receiver):
            receiver = signal_receiver()
            payment_approved.connect(receiver)
            # ... trigger signal
            assert receiver.called
            assert receiver.call_count == 1
    """

    def _create_receiver():
        receiver = MagicMock()
        receiver.called = False
        receiver.call_count = 0
        receiver.last_kwargs = None

        def handler(sender, **kwargs):
            receiver.called = True
            receiver.call_count += 1
            receiver.last_kwargs = kwargs

        receiver.handler = handler
        return receiver

    return _create_receiver
