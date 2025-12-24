"""
Tests for EasyPay Sandbox module.

Tests cover:
- SandboxPayment model (creation, order_id generation, factory method)
- debug_required decorator (DEBUG mode restriction)
- SandboxIndexView (form display)
- SandboxPaymentView (payment creation, EasyPay redirect)
- SandboxCallbackView (callback processing, approval)
"""

from decimal import Decimal

import pytest
import responses
from django.test import override_settings
from django.urls import reverse

from easypay.models import PaymentStatus
from easypay.sandbox.models import SandboxPayment
from easypay.sandbox.views import debug_required


# ============================================================
# SandboxPayment Model Tests
# ============================================================


@pytest.mark.django_db
class TestSandboxPaymentModel:
    """Tests for SandboxPayment model."""

    def test_create_payment(self):
        """Should create a sandbox payment with default values."""
        payment = SandboxPayment.objects.create(
            amount=Decimal("10000"),
            goods_name="테스트 상품",
        )
        assert payment.pk is not None
        assert payment.amount == Decimal("10000")
        assert payment.goods_name == "테스트 상품"
        assert payment.status == PaymentStatus.PENDING

    def test_auto_generates_order_id(self):
        """Should auto-generate order_id if not provided."""
        payment = SandboxPayment.objects.create(
            amount=Decimal("10000"),
        )
        assert payment.order_id is not None
        assert payment.order_id.startswith("SB")
        assert len(payment.order_id) == 14  # "SB" + 12 hex chars

    def test_preserves_custom_order_id(self):
        """Should preserve custom order_id if provided."""
        payment = SandboxPayment.objects.create(
            amount=Decimal("10000"),
            order_id="CUSTOM123",
        )
        assert payment.order_id == "CUSTOM123"

    def test_order_id_is_unique(self):
        """Order IDs should be unique."""
        SandboxPayment.objects.create(amount=Decimal("10000"))
        payment2 = SandboxPayment.objects.create(amount=Decimal("20000"))

        all_order_ids = list(SandboxPayment.objects.values_list("order_id", flat=True))
        assert len(all_order_ids) == len(set(all_order_ids))

    def test_str_representation(self):
        """String representation should include order_id and amount."""
        payment = SandboxPayment.objects.create(
            amount=Decimal("29900"),
            goods_name="테스트 상품",
        )
        str_repr = str(payment)
        assert payment.order_id in str_repr
        assert "29,900원" in str_repr
        assert "결제대기" in str_repr

    def test_factory_method_creates_unsaved_instance(self):
        """Factory method should return unsaved instance."""
        payment = SandboxPayment.create_test_payment(
            amount=5000,
            goods_name="팩토리 상품",
        )
        assert payment.pk is None
        assert payment.amount == Decimal("5000")
        assert payment.goods_name == "팩토리 상품"

    def test_factory_method_with_extra_kwargs(self):
        """Factory method should accept extra kwargs."""
        payment = SandboxPayment.create_test_payment(
            amount=3000,
            client_ip="192.168.1.1",
        )
        assert payment.client_ip == "192.168.1.1"

    def test_inherits_from_abstract_payment(self):
        """Should have all AbstractPayment fields."""
        payment = SandboxPayment.objects.create(amount=Decimal("10000"))

        # Check AbstractPayment fields exist
        assert hasattr(payment, "pg_tid")
        assert hasattr(payment, "auth_id")
        assert hasattr(payment, "status")
        assert hasattr(payment, "paid_at")
        assert hasattr(payment, "client_ip")
        assert hasattr(payment, "client_user_agent")

    def test_mark_as_paid(self):
        """mark_as_paid should update status and paid_at."""
        payment = SandboxPayment.objects.create(amount=Decimal("10000"))
        payment.mark_as_paid(pg_tid="TEST_TID_123", auth_id="AUTH123")

        payment.refresh_from_db()
        assert payment.status == PaymentStatus.COMPLETED
        assert payment.pg_tid == "TEST_TID_123"
        assert payment.auth_id == "AUTH123"
        assert payment.paid_at is not None

    def test_mark_as_failed(self):
        """mark_as_failed should update status to FAILED."""
        payment = SandboxPayment.objects.create(amount=Decimal("10000"))
        payment.mark_as_failed()

        payment.refresh_from_db()
        assert payment.status == PaymentStatus.FAILED


# ============================================================
# debug_required Decorator Tests
# ============================================================


class TestDebugRequiredDecorator:
    """Tests for debug_required decorator."""

    def test_allows_access_in_debug_mode(self, request_factory):
        """Should allow access when DEBUG=True."""

        @debug_required
        def test_view(request):
            return "OK"

        request = request_factory.get("/test/")
        with override_settings(DEBUG=True):
            response = test_view(request)

        assert response == "OK"

    def test_blocks_access_in_production(self, request_factory):
        """Should return 403 when DEBUG=False."""

        @debug_required
        def test_view(request):
            return "OK"

        request = request_factory.get("/test/")
        with override_settings(DEBUG=False):
            response = test_view(request)

        assert response.status_code == 403
        assert "DEBUG mode" in response.content.decode()


# ============================================================
# SandboxIndexView Tests
# ============================================================


@pytest.mark.django_db
class TestSandboxIndexView:
    """Tests for SandboxIndexView."""

    @override_settings(DEBUG=True)
    def test_get_returns_form(self, client):
        """GET should return sandbox form page."""
        url = reverse("easypay_sandbox:index")
        response = client.get(url)

        assert response.status_code == 200
        assert "EasyPay Sandbox" in response.content.decode()

    @override_settings(DEBUG=True)
    def test_context_contains_mall_id(self, client):
        """Context should contain mall_id."""
        url = reverse("easypay_sandbox:index")
        response = client.get(url)

        assert response.status_code == 200
        assert "T0021792" in response.content.decode()

    @override_settings(DEBUG=False)
    def test_returns_403_when_not_debug(self, client):
        """Should return 403 when DEBUG=False."""
        url = reverse("easypay_sandbox:index")
        response = client.get(url)

        assert response.status_code == 403


# ============================================================
# SandboxPaymentView Tests
# ============================================================


@pytest.mark.django_db
class TestSandboxPaymentView:
    """Tests for SandboxPaymentView."""

    @override_settings(DEBUG=True)
    @responses.activate
    def test_post_creates_payment_and_redirects(self, client):
        """POST should create payment and redirect to EasyPay."""
        # Mock EasyPay register API
        responses.add(
            responses.POST,
            "https://testpgapi.easypay.co.kr/api/ep9/trades/webpay",
            json={
                "resCd": "0000",
                "resMsg": "Success",
                "authPageUrl": "https://testpg.easypay.co.kr/auth/page",
            },
            status=200,
        )

        url = reverse("easypay_sandbox:pay")
        response = client.post(
            url,
            {
                "amount": "5000",
                "goods_name": "테스트 상품",
            },
        )

        # Should redirect to EasyPay
        assert response.status_code == 302
        assert "easypay.co.kr" in response.url

        # Should create payment in DB
        assert SandboxPayment.objects.count() == 1
        payment = SandboxPayment.objects.first()
        assert payment.amount == Decimal("5000")
        assert payment.goods_name == "테스트 상품"

    @override_settings(DEBUG=True)
    @responses.activate
    def test_post_with_default_amount(self, client):
        """POST without amount should use default 1000."""
        responses.add(
            responses.POST,
            "https://testpgapi.easypay.co.kr/api/ep9/trades/webpay",
            json={
                "resCd": "0000",
                "resMsg": "Success",
                "authPageUrl": "https://testpg.easypay.co.kr/auth/page",
            },
            status=200,
        )

        url = reverse("easypay_sandbox:pay")
        response = client.post(url, {})

        payment = SandboxPayment.objects.first()
        assert payment.amount == Decimal("1000")

    @override_settings(DEBUG=True)
    @responses.activate
    def test_post_handles_api_error(self, client):
        """POST should handle EasyPay API errors."""
        responses.add(
            responses.POST,
            "https://testpgapi.easypay.co.kr/api/ep9/trades/webpay",
            json={
                "resCd": "E500",
                "resMsg": "Server Error",
            },
            status=200,
        )

        url = reverse("easypay_sandbox:pay")
        response = client.post(url, {"amount": "5000"})

        # Should show error page, not redirect
        assert response.status_code == 200
        assert (
            "Server Error" in response.content.decode()
            or "E500" in response.content.decode()
        )

        # Payment should be marked as failed
        payment = SandboxPayment.objects.first()
        assert payment.status == PaymentStatus.FAILED

    @override_settings(DEBUG=True)
    @responses.activate
    def test_post_handles_missing_auth_page_url(self, client):
        """POST should handle response without authPageUrl."""
        responses.add(
            responses.POST,
            "https://testpgapi.easypay.co.kr/api/ep9/trades/webpay",
            json={
                "resCd": "0000",
                "resMsg": "Success",
                # No authPageUrl
            },
            status=200,
        )

        url = reverse("easypay_sandbox:pay")
        response = client.post(url, {"amount": "5000"})

        # Should show error page
        assert response.status_code == 200
        assert "결제 페이지 URL" in response.content.decode()

    @override_settings(DEBUG=False)
    def test_returns_403_when_not_debug(self, client):
        """Should return 403 when DEBUG=False."""
        url = reverse("easypay_sandbox:pay")
        response = client.post(url, {"amount": "5000"})

        assert response.status_code == 403


# ============================================================
# SandboxCallbackView Tests
# ============================================================


@pytest.mark.django_db
class TestSandboxCallbackView:
    """Tests for SandboxCallbackView."""

    @override_settings(DEBUG=True)
    def test_callback_without_payment_id(self, client):
        """Callback without payment_id should show error."""
        url = reverse("easypay_sandbox:callback")
        response = client.get(url)

        assert response.status_code == 200
        assert "payment_id" in response.content.decode()

    @override_settings(DEBUG=True)
    def test_callback_with_invalid_payment_id(self, client):
        """Callback with invalid payment_id should show error."""
        url = reverse("easypay_sandbox:callback")
        response = client.get(url, {"payment_id": "99999"})

        assert response.status_code == 200
        assert "찾을 수 없습니다" in response.content.decode()

    @override_settings(DEBUG=True)
    def test_callback_without_authorization_id(self, client):
        """Callback without authorizationId should mark payment as failed."""
        payment = SandboxPayment.objects.create(amount=Decimal("10000"))

        url = reverse("easypay_sandbox:callback")
        response = client.get(url, {"payment_id": str(payment.pk)})

        assert response.status_code == 200
        assert (
            "취소" in response.content.decode()
            or "인증 정보" in response.content.decode()
        )

        payment.refresh_from_db()
        assert payment.status == PaymentStatus.FAILED

    @override_settings(DEBUG=True)
    @responses.activate
    def test_callback_approves_payment(self, client):
        """Callback with valid authorizationId should approve payment."""
        payment = SandboxPayment.objects.create(amount=Decimal("10000"))

        # Mock EasyPay approve API
        responses.add(
            responses.POST,
            "https://testpgapi.easypay.co.kr/api/ep9/trades/approval",
            json={
                "resCd": "0000",
                "resMsg": "Success",
                "pgTid": "EASYPAY_TID_12345",
                "paymentInfo": {
                    "payMethodTypeCode": "11",
                    "cardInfo": {
                        "cardName": "신한카드",
                        "cardNo": "1234-****-****-5678",
                    },
                },
            },
            status=200,
        )

        url = reverse("easypay_sandbox:callback")
        response = client.get(
            url,
            {
                "payment_id": str(payment.pk),
                "authorizationId": "AUTH123456",
            },
        )

        assert response.status_code == 200

        payment.refresh_from_db()
        assert payment.status == PaymentStatus.COMPLETED
        assert payment.pg_tid == "EASYPAY_TID_12345"
        assert payment.auth_id == "AUTH123456"
        assert payment.card_name == "신한카드"

    @override_settings(DEBUG=True)
    @responses.activate
    def test_callback_handles_approval_error(self, client):
        """Callback should handle approval API errors."""
        payment = SandboxPayment.objects.create(amount=Decimal("10000"))

        responses.add(
            responses.POST,
            "https://testpgapi.easypay.co.kr/api/ep9/trades/approval",
            json={
                "resCd": "E401",
                "resMsg": "Authentication failed",
            },
            status=200,
        )

        url = reverse("easypay_sandbox:callback")
        response = client.get(
            url,
            {
                "payment_id": str(payment.pk),
                "authorizationId": "INVALID_AUTH",
            },
        )

        assert response.status_code == 200
        assert (
            "Authentication failed" in response.content.decode()
            or "E401" in response.content.decode()
        )

        payment.refresh_from_db()
        assert payment.status == PaymentStatus.FAILED

    @override_settings(DEBUG=True)
    @responses.activate
    def test_callback_already_paid(self, client):
        """Callback for already paid payment should show message."""
        payment = SandboxPayment.objects.create(amount=Decimal("10000"))
        payment.mark_as_paid(pg_tid="EXISTING_TID")

        url = reverse("easypay_sandbox:callback")
        response = client.get(
            url,
            {
                "payment_id": str(payment.pk),
                "authorizationId": "AUTH123",
            },
        )

        assert response.status_code == 200
        assert (
            "이미" in response.content.decode() or "완료" in response.content.decode()
        )

    @override_settings(DEBUG=False)
    def test_returns_403_when_not_debug(self, client):
        """Should return 403 when DEBUG=False."""
        url = reverse("easypay_sandbox:callback")
        response = client.get(url, {"payment_id": "1"})

        assert response.status_code == 403


# ============================================================
# URL Configuration Tests
# ============================================================


class TestSandboxUrls:
    """Tests for sandbox URL configuration."""

    def test_index_url_exists(self):
        """Index URL should be reversible."""
        url = reverse("easypay_sandbox:index")
        assert url == "/easypay/sandbox/"

    def test_pay_url_exists(self):
        """Pay URL should be reversible."""
        url = reverse("easypay_sandbox:pay")
        assert url == "/easypay/sandbox/pay/"

    def test_callback_url_exists(self):
        """Callback URL should be reversible."""
        url = reverse("easypay_sandbox:callback")
        assert url == "/easypay/sandbox/callback/"
