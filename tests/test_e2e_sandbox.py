"""
E2E Tests for EasyPay Sandbox module.

Tests cover complete payment flows from form submission to callback processing,
verifying data persistence across requests and EasyPay API call chaining.

Unlike unit tests (test_sandbox.py), these tests verify:
- Full multi-step payment flows
- Request-to-request data persistence
- EasyPay API call orchestration (register → approve)
- Redirect URL handling and validation
"""

from decimal import Decimal

import pytest
import responses
from django.test import override_settings
from django.urls import reverse

from easypay.models import PaymentStatus
from easypay.sandbox.models import SandboxPayment


# All tests except security tests require DEBUG=True
# Apply @override_settings(DEBUG=True) to ensure sandbox views are accessible


# ============================================================
# Helper Constants
# ============================================================

EASYPAY_WEBPAY_URL = "https://testpgapi.easypay.co.kr/api/ep9/trades/webpay"
EASYPAY_APPROVAL_URL = "https://testpgapi.easypay.co.kr/api/ep9/trades/approval"
EASYPAY_AUTH_PAGE = "https://testpgapi.easypay.co.kr/webpay/auth?token=TEST_TOKEN"


# ============================================================
# E2E Flow Tests (Critical Path)
# ============================================================


@pytest.mark.django_db
class TestCompletePaymentFlow:
    """E2E tests for complete payment flows."""

    @override_settings(DEBUG=True)
    @responses.activate
    def test_complete_payment_flow_success(self, client):
        """
        Test complete happy path:
        Form → Register → EasyPay Redirect → Callback → Success
        """
        # Mock EasyPay register API
        responses.add(
            responses.POST,
            EASYPAY_WEBPAY_URL,
            json={
                "resCd": "0000",
                "resMsg": "정상처리",
                "authPageUrl": EASYPAY_AUTH_PAGE,
            },
            status=200,
        )

        # Mock EasyPay approve API
        responses.add(
            responses.POST,
            EASYPAY_APPROVAL_URL,
            json={
                "resCd": "0000",
                "resMsg": "정상처리",
                "pgTid": "PGTID123456789012",
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

        # Step 1: Load form page
        response = client.get(reverse("easypay_sandbox:index"))
        assert response.status_code == 200
        content = response.content.decode()
        assert "EasyPay Sandbox" in content

        # Step 2: Submit payment form
        response = client.post(
            reverse("easypay_sandbox:pay"),
            {"amount": "5000", "goods_name": "E2E 테스트 상품"},
        )

        # Verify redirect to EasyPay
        assert response.status_code == 302
        assert "easypay.co.kr" in response.url

        # Verify payment created with correct status
        payment = SandboxPayment.objects.first()
        assert payment is not None
        assert payment.amount == Decimal("5000")
        assert payment.goods_name == "E2E 테스트 상품"
        assert payment.status == PaymentStatus.PENDING
        assert payment.order_id.startswith("SB")

        # Step 3: Simulate EasyPay callback
        callback_url = reverse("easypay_sandbox:callback")
        response = client.get(
            f"{callback_url}?payment_id={payment.pk}&authorizationId=AUTH_E2E_TEST"
        )

        # Verify success page
        assert response.status_code == 200
        content = response.content.decode()
        assert "결제 완료" in content or "success" in content.lower()
        assert "PGTID123456789012" in content or payment.order_id in content

        # Verify payment updated
        payment.refresh_from_db()
        assert payment.status == PaymentStatus.COMPLETED
        assert payment.is_paid is True
        assert payment.pg_tid == "PGTID123456789012"
        assert payment.auth_id == "AUTH_E2E_TEST"
        assert payment.card_name == "신한카드"
        assert payment.card_no == "1234-****-****-5678"
        assert payment.paid_at is not None

    @override_settings(DEBUG=True)
    @responses.activate
    def test_complete_flow_registration_api_error(self, client):
        """
        Test error path:
        Form → Register API Error → Error Page (no redirect)
        """
        # Mock EasyPay register API with error
        responses.add(
            responses.POST,
            EASYPAY_WEBPAY_URL,
            json={
                "resCd": "E500",
                "resMsg": "서버 내부 오류",
            },
            status=200,
        )

        # Submit payment form
        response = client.post(
            reverse("easypay_sandbox:pay"),
            {"amount": "5000", "goods_name": "에러 테스트"},
        )

        # Should NOT redirect, show error page
        assert response.status_code == 200
        content = response.content.decode()
        assert "E500" in content or "오류" in content

        # Payment should be marked as failed
        payment = SandboxPayment.objects.first()
        assert payment is not None
        assert payment.status == PaymentStatus.FAILED

    @override_settings(DEBUG=True)
    @responses.activate
    def test_complete_flow_user_cancellation(self, client):
        """
        Test cancellation path:
        Form → Register → User cancels at EasyPay → Callback without authId → Failure
        """
        # Mock EasyPay register API
        responses.add(
            responses.POST,
            EASYPAY_WEBPAY_URL,
            json={
                "resCd": "0000",
                "authPageUrl": EASYPAY_AUTH_PAGE,
            },
            status=200,
        )

        # Submit payment form
        response = client.post(
            reverse("easypay_sandbox:pay"),
            {"amount": "3000"},
        )
        assert response.status_code == 302

        # Get payment
        payment = SandboxPayment.objects.first()
        assert payment.status == PaymentStatus.PENDING

        # Simulate callback without authorizationId (user cancelled)
        callback_url = reverse("easypay_sandbox:callback")
        response = client.get(f"{callback_url}?payment_id={payment.pk}")

        # Should show cancellation message
        assert response.status_code == 200
        content = response.content.decode()
        assert "취소" in content or "인증" in content

        # Payment should be marked as failed
        payment.refresh_from_db()
        assert payment.status == PaymentStatus.FAILED


# ============================================================
# Form & Display Tests
# ============================================================


@pytest.mark.django_db
class TestSandboxFormDisplay:
    """Tests for form display and interaction."""

    @override_settings(DEBUG=True)
    def test_form_displays_with_defaults(self, client):
        """Form should display with default values."""
        response = client.get(reverse("easypay_sandbox:index"))

        assert response.status_code == 200
        content = response.content.decode()

        # Check page title
        assert "EasyPay Sandbox" in content or "Sandbox" in content

        # Check form elements exist
        assert "amount" in content
        assert "goods_name" in content or "상품" in content

    @override_settings(DEBUG=True)
    def test_form_displays_test_environment_info(self, client):
        """Form should display test environment information."""
        response = client.get(reverse("easypay_sandbox:index"))

        assert response.status_code == 200
        content = response.content.decode()

        # Check test environment info
        assert "T0021792" in content or "testpgapi" in content

    @override_settings(DEBUG=True)
    @responses.activate
    def test_form_accepts_custom_amount(self, client):
        """Form should process custom amount."""
        responses.add(
            responses.POST,
            EASYPAY_WEBPAY_URL,
            json={"resCd": "0000", "authPageUrl": EASYPAY_AUTH_PAGE},
            status=200,
        )

        response = client.post(
            reverse("easypay_sandbox:pay"),
            {"amount": "99000"},
        )

        payment = SandboxPayment.objects.first()
        assert payment.amount == Decimal("99000")

    @override_settings(DEBUG=True)
    @responses.activate
    def test_form_accepts_custom_goods_name(self, client):
        """Form should process custom goods name."""
        responses.add(
            responses.POST,
            EASYPAY_WEBPAY_URL,
            json={"resCd": "0000", "authPageUrl": EASYPAY_AUTH_PAGE},
            status=200,
        )

        response = client.post(
            reverse("easypay_sandbox:pay"),
            {"amount": "1000", "goods_name": "커스텀 상품명"},
        )

        payment = SandboxPayment.objects.first()
        assert payment.goods_name == "커스텀 상품명"

    @override_settings(DEBUG=True)
    @responses.activate
    def test_form_submission_creates_payment(self, client):
        """Form submission should create payment in database."""
        responses.add(
            responses.POST,
            EASYPAY_WEBPAY_URL,
            json={"resCd": "0000", "authPageUrl": EASYPAY_AUTH_PAGE},
            status=200,
        )

        # Initially no payments
        assert SandboxPayment.objects.count() == 0

        response = client.post(
            reverse("easypay_sandbox:pay"),
            {"amount": "7500", "goods_name": "생성 테스트"},
        )

        # Payment should be created
        assert SandboxPayment.objects.count() == 1
        payment = SandboxPayment.objects.first()
        assert payment.amount == Decimal("7500")


# ============================================================
# Payment Registration Tests
# ============================================================


@pytest.mark.django_db
class TestPaymentRegistration:
    """Tests for payment registration step."""

    @override_settings(DEBUG=True)
    @responses.activate
    def test_registration_redirects_to_easypay(self, client):
        """Successful registration should redirect to EasyPay authPageUrl."""
        responses.add(
            responses.POST,
            EASYPAY_WEBPAY_URL,
            json={
                "resCd": "0000",
                "authPageUrl": "https://testpgapi.easypay.co.kr/custom/path",
            },
            status=200,
        )

        response = client.post(
            reverse("easypay_sandbox:pay"),
            {"amount": "1000"},
        )

        assert response.status_code == 302
        assert "easypay.co.kr" in response.url
        assert "custom/path" in response.url

    @override_settings(DEBUG=True)
    @responses.activate
    def test_registration_stores_client_ip(self, client):
        """Registration should extract and store client IP."""
        responses.add(
            responses.POST,
            EASYPAY_WEBPAY_URL,
            json={"resCd": "0000", "authPageUrl": EASYPAY_AUTH_PAGE},
            status=200,
        )

        # Simulate CloudFlare IP header
        response = client.post(
            reverse("easypay_sandbox:pay"),
            {"amount": "1000"},
            HTTP_CF_CONNECTING_IP="203.0.113.50",
        )

        payment = SandboxPayment.objects.first()
        assert payment.client_ip == "203.0.113.50"

    @override_settings(DEBUG=True)
    @responses.activate
    def test_registration_stores_user_agent(self, client):
        """Registration should store User-Agent."""
        responses.add(
            responses.POST,
            EASYPAY_WEBPAY_URL,
            json={"resCd": "0000", "authPageUrl": EASYPAY_AUTH_PAGE},
            status=200,
        )

        user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0"
        response = client.post(
            reverse("easypay_sandbox:pay"),
            {"amount": "1000"},
            HTTP_USER_AGENT=user_agent,
        )

        payment = SandboxPayment.objects.first()
        assert user_agent in payment.client_user_agent

    @override_settings(DEBUG=True)
    @responses.activate
    def test_registration_api_error_shows_error(self, client):
        """API error should show error page, not redirect."""
        responses.add(
            responses.POST,
            EASYPAY_WEBPAY_URL,
            json={"resCd": "E101", "resMsg": "필수 파라미터 누락"},
            status=200,
        )

        response = client.post(
            reverse("easypay_sandbox:pay"),
            {"amount": "1000"},
        )

        # Should render error page, not redirect
        assert response.status_code == 200
        content = response.content.decode()
        assert "E101" in content or "필수" in content

    @override_settings(DEBUG=True)
    @responses.activate
    def test_registration_api_error_marks_failed(self, client):
        """API error should mark payment as failed."""
        responses.add(
            responses.POST,
            EASYPAY_WEBPAY_URL,
            json={"resCd": "E500", "resMsg": "서버 오류"},
            status=200,
        )

        response = client.post(
            reverse("easypay_sandbox:pay"),
            {"amount": "1000"},
        )

        payment = SandboxPayment.objects.first()
        assert payment.status == PaymentStatus.FAILED

    @override_settings(DEBUG=True)
    @responses.activate
    def test_registration_missing_auth_url_shows_error(self, client):
        """Missing authPageUrl should show error."""
        responses.add(
            responses.POST,
            EASYPAY_WEBPAY_URL,
            json={"resCd": "0000"},  # No authPageUrl
            status=200,
        )

        response = client.post(
            reverse("easypay_sandbox:pay"),
            {"amount": "1000"},
        )

        # Should show error, not redirect
        assert response.status_code == 200
        content = response.content.decode()
        assert "URL" in content or "오류" in content


# ============================================================
# Callback Processing Tests
# ============================================================


@pytest.mark.django_db
class TestCallbackProcessing:
    """Tests for callback processing step."""

    @override_settings(DEBUG=True)
    @responses.activate
    def test_callback_approves_payment(self, client):
        """Valid callback should approve payment."""
        # Create pending payment
        payment = SandboxPayment.objects.create(
            amount=Decimal("5000"),
            status=PaymentStatus.PENDING,
        )

        # Mock approve API
        responses.add(
            responses.POST,
            EASYPAY_APPROVAL_URL,
            json={
                "resCd": "0000",
                "pgTid": "PGTID_CALLBACK_TEST",
                "paymentInfo": {
                    "payMethodTypeCode": "11",
                    "cardInfo": {
                        "cardName": "삼성카드",
                        "cardNo": "9999-****-****-1111",
                    },
                },
            },
            status=200,
        )

        # Simulate callback
        callback_url = reverse("easypay_sandbox:callback")
        response = client.get(
            f"{callback_url}?payment_id={payment.pk}&authorizationId=AUTH_CALLBACK"
        )

        assert response.status_code == 200

        payment.refresh_from_db()
        assert payment.status == PaymentStatus.COMPLETED
        assert payment.is_paid is True

    @override_settings(DEBUG=True)
    @responses.activate
    def test_callback_stores_pg_tid(self, client):
        """Callback should store PG transaction ID."""
        payment = SandboxPayment.objects.create(amount=Decimal("1000"))

        responses.add(
            responses.POST,
            EASYPAY_APPROVAL_URL,
            json={
                "resCd": "0000",
                "pgTid": "UNIQUE_PG_TID_12345",
                "paymentInfo": {},
            },
            status=200,
        )

        callback_url = reverse("easypay_sandbox:callback")
        client.get(f"{callback_url}?payment_id={payment.pk}&authorizationId=AUTH123")

        payment.refresh_from_db()
        assert payment.pg_tid == "UNIQUE_PG_TID_12345"

    @override_settings(DEBUG=True)
    @responses.activate
    def test_callback_stores_card_info(self, client):
        """Callback should store card information."""
        payment = SandboxPayment.objects.create(amount=Decimal("1000"))

        responses.add(
            responses.POST,
            EASYPAY_APPROVAL_URL,
            json={
                "resCd": "0000",
                "pgTid": "PGTID123",
                "paymentInfo": {
                    "payMethodTypeCode": "11",
                    "cardInfo": {
                        "cardName": "현대카드",
                        "cardNo": "5555-****-****-6666",
                    },
                },
            },
            status=200,
        )

        callback_url = reverse("easypay_sandbox:callback")
        client.get(f"{callback_url}?payment_id={payment.pk}&authorizationId=AUTH123")

        payment.refresh_from_db()
        assert payment.card_name == "현대카드"
        assert payment.card_no == "5555-****-****-6666"
        assert payment.pay_method == "11"

    @override_settings(DEBUG=True)
    def test_callback_without_auth_id_marks_failed(self, client):
        """Callback without authorizationId should mark as failed."""
        payment = SandboxPayment.objects.create(amount=Decimal("1000"))

        callback_url = reverse("easypay_sandbox:callback")
        response = client.get(f"{callback_url}?payment_id={payment.pk}")

        assert response.status_code == 200
        content = response.content.decode()
        assert "취소" in content or "인증" in content

        payment.refresh_from_db()
        assert payment.status == PaymentStatus.FAILED

    @override_settings(DEBUG=True)
    def test_callback_invalid_payment_id_shows_error(self, client):
        """Invalid payment_id should show error."""
        callback_url = reverse("easypay_sandbox:callback")
        response = client.get(
            f"{callback_url}?payment_id=99999&authorizationId=AUTH123"
        )

        assert response.status_code == 200
        content = response.content.decode()
        assert "찾을 수 없" in content or "99999" in content

    @override_settings(DEBUG=True)
    def test_callback_missing_payment_id_shows_error(self, client):
        """Missing payment_id should show error."""
        callback_url = reverse("easypay_sandbox:callback")
        response = client.get(f"{callback_url}?authorizationId=AUTH123")

        assert response.status_code == 200
        content = response.content.decode()
        assert "payment_id" in content or "파라미터" in content

    @override_settings(DEBUG=True)
    @responses.activate
    def test_callback_idempotent_for_completed(self, client):
        """Callback for already completed payment should be idempotent."""
        # Create already completed payment
        payment = SandboxPayment.objects.create(
            amount=Decimal("1000"),
            status=PaymentStatus.COMPLETED,
            pg_tid="ALREADY_PAID_TID",
            auth_id="ALREADY_PAID_AUTH",
        )
        payment.mark_as_paid(pg_tid="ALREADY_PAID_TID", auth_id="ALREADY_PAID_AUTH")

        # Callback again
        callback_url = reverse("easypay_sandbox:callback")
        response = client.get(
            f"{callback_url}?payment_id={payment.pk}&authorizationId=NEW_AUTH"
        )

        assert response.status_code == 200
        content = response.content.decode()
        assert "이미" in content or "완료" in content

        # Should NOT call approve API again (no responses mock = would fail)
        # Payment should remain unchanged
        payment.refresh_from_db()
        assert payment.pg_tid == "ALREADY_PAID_TID"
        assert payment.auth_id == "ALREADY_PAID_AUTH"

    @override_settings(DEBUG=True)
    @responses.activate
    def test_callback_approval_error_shows_error(self, client):
        """Approval API error should show error page."""
        payment = SandboxPayment.objects.create(amount=Decimal("1000"))

        responses.add(
            responses.POST,
            EASYPAY_APPROVAL_URL,
            json={"resCd": "E401", "resMsg": "인증 실패"},
            status=200,
        )

        callback_url = reverse("easypay_sandbox:callback")
        response = client.get(
            f"{callback_url}?payment_id={payment.pk}&authorizationId=BAD_AUTH"
        )

        assert response.status_code == 200
        content = response.content.decode()
        assert "E401" in content or "인증" in content

        payment.refresh_from_db()
        assert payment.status == PaymentStatus.FAILED


# ============================================================
# Security & Edge Cases Tests
# ============================================================


@pytest.mark.django_db
class TestSecurityAndEdgeCases:
    """Tests for security restrictions and edge cases."""

    @override_settings(DEBUG=False)
    def test_debug_mode_required_index(self, client):
        """Index should return 403 when DEBUG=False."""
        response = client.get(reverse("easypay_sandbox:index"))
        assert response.status_code == 403
        assert "DEBUG" in response.content.decode()

    @override_settings(DEBUG=False)
    def test_debug_mode_required_pay(self, client):
        """Pay should return 403 when DEBUG=False."""
        response = client.post(
            reverse("easypay_sandbox:pay"),
            {"amount": "1000"},
        )
        assert response.status_code == 403

    @override_settings(DEBUG=False)
    def test_debug_mode_required_callback(self, client):
        """Callback should return 403 when DEBUG=False."""
        response = client.get(
            reverse("easypay_sandbox:callback") + "?payment_id=1&authorizationId=AUTH"
        )
        assert response.status_code == 403

    @override_settings(DEBUG=True)
    @responses.activate
    def test_form_amount_type_coercion(self, client):
        """Invalid amount should default to 1000."""
        responses.add(
            responses.POST,
            EASYPAY_WEBPAY_URL,
            json={"resCd": "0000", "authPageUrl": EASYPAY_AUTH_PAGE},
            status=200,
        )

        response = client.post(
            reverse("easypay_sandbox:pay"),
            {"amount": "invalid_number"},
        )

        payment = SandboxPayment.objects.first()
        assert payment.amount == Decimal("1000")  # Default value

    @override_settings(DEBUG=True)
    @responses.activate
    def test_form_empty_goods_name_defaults(self, client):
        """Empty goods_name should default to '테스트 상품'."""
        responses.add(
            responses.POST,
            EASYPAY_WEBPAY_URL,
            json={"resCd": "0000", "authPageUrl": EASYPAY_AUTH_PAGE},
            status=200,
        )

        response = client.post(
            reverse("easypay_sandbox:pay"),
            {"amount": "1000", "goods_name": ""},
        )

        payment = SandboxPayment.objects.first()
        assert payment.goods_name == "테스트 상품"

    @override_settings(DEBUG=True)
    @responses.activate
    def test_cloudflare_ip_header_extraction(self, client):
        """Should extract IP from CF-Connecting-IP header."""
        responses.add(
            responses.POST,
            EASYPAY_WEBPAY_URL,
            json={"resCd": "0000", "authPageUrl": EASYPAY_AUTH_PAGE},
            status=200,
        )

        response = client.post(
            reverse("easypay_sandbox:pay"),
            {"amount": "1000"},
            HTTP_CF_CONNECTING_IP="203.0.113.100",
            HTTP_X_FORWARDED_FOR="203.0.113.100, 10.0.0.1",
            REMOTE_ADDR="10.0.0.1",
        )

        payment = SandboxPayment.objects.first()
        # CloudFlare header should take precedence
        assert payment.client_ip == "203.0.113.100"

    @override_settings(DEBUG=True)
    @responses.activate
    def test_nginx_ip_header_extraction(self, client):
        """Should extract IP from X-Real-IP header when no CF header."""
        responses.add(
            responses.POST,
            EASYPAY_WEBPAY_URL,
            json={"resCd": "0000", "authPageUrl": EASYPAY_AUTH_PAGE},
            status=200,
        )

        response = client.post(
            reverse("easypay_sandbox:pay"),
            {"amount": "1000"},
            HTTP_X_REAL_IP="198.51.100.25",
            REMOTE_ADDR="10.0.0.1",
        )

        payment = SandboxPayment.objects.first()
        assert payment.client_ip == "198.51.100.25"

    @override_settings(DEBUG=True)
    @responses.activate
    def test_retry_after_failure(self, client):
        """User should be able to retry after a failed payment."""
        # First attempt - fails
        responses.add(
            responses.POST,
            EASYPAY_WEBPAY_URL,
            json={"resCd": "E500", "resMsg": "서버 오류"},
            status=200,
        )

        response = client.post(
            reverse("easypay_sandbox:pay"),
            {"amount": "5000", "goods_name": "재시도 테스트"},
        )

        first_payment = SandboxPayment.objects.first()
        assert first_payment.status == PaymentStatus.FAILED

        # Second attempt - succeeds
        responses.replace(
            responses.POST,
            EASYPAY_WEBPAY_URL,
            json={"resCd": "0000", "authPageUrl": EASYPAY_AUTH_PAGE},
            status=200,
        )

        response = client.post(
            reverse("easypay_sandbox:pay"),
            {"amount": "5000", "goods_name": "재시도 테스트"},
        )

        # Should have two payments now
        assert SandboxPayment.objects.count() == 2

        # Second payment should be pending (successful registration)
        second_payment = SandboxPayment.objects.order_by("-pk").first()
        assert second_payment.status == PaymentStatus.PENDING
        assert response.status_code == 302  # Redirect to EasyPay

    @override_settings(DEBUG=True)
    @responses.activate
    def test_multiple_payments_in_sequence(self, client):
        """Multiple sequential payments should work independently."""
        responses.add(
            responses.POST,
            EASYPAY_WEBPAY_URL,
            json={"resCd": "0000", "authPageUrl": EASYPAY_AUTH_PAGE},
            status=200,
        )

        # Create multiple payments
        for i in range(3):
            responses.add(
                responses.POST,
                EASYPAY_WEBPAY_URL,
                json={"resCd": "0000", "authPageUrl": EASYPAY_AUTH_PAGE},
                status=200,
            )
            client.post(
                reverse("easypay_sandbox:pay"),
                {"amount": str(1000 * (i + 1)), "goods_name": f"상품 {i + 1}"},
            )

        # All should be created
        assert SandboxPayment.objects.count() == 3

        # All should have unique order_ids
        order_ids = list(SandboxPayment.objects.values_list("order_id", flat=True))
        assert len(order_ids) == len(set(order_ids))

        # Amounts should be different
        amounts = list(SandboxPayment.objects.values_list("amount", flat=True))
        assert Decimal("1000") in amounts
        assert Decimal("2000") in amounts
        assert Decimal("3000") in amounts
