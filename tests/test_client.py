"""
Tests for EasyPayClient API client.

Tests cover:
- Client initialization and configuration
- Payment registration (register_payment)
- Payment approval (approve_payment)
- Payment cancellation (cancel_payment)
- Transaction status inquiry (get_transaction_status)
- Receipt URL generation (get_receipt_url)
- Signal firing on payment events
- Error handling (timeouts, API errors, network failures)
"""

from decimal import Decimal
from unittest.mock import MagicMock

import pytest
import responses
from freezegun import freeze_time

from easypay.client import EasyPayClient, easypay_client
from easypay.exceptions import (
    ConfigurationError,
    EasyPayError,
    PaymentApprovalError,
    PaymentCancellationError,
    PaymentInquiryError,
    PaymentRegistrationError,
)


# ============================================================
# Client Initialization Tests
# ============================================================


class TestEasyPayClientInit:
    """Tests for EasyPayClient initialization."""

    def test_default_configuration(self):
        """Client uses default test configuration."""
        client = EasyPayClient()

        assert client.mall_id == "T0021792"
        assert client.api_url == "https://testpgapi.easypay.co.kr"
        assert client.timeout == 30

    def test_custom_configuration(self):
        """Client accepts custom configuration."""
        client = EasyPayClient(
            mall_id="CUSTOM_MALL",
            api_url="https://custom.api.com",
            timeout=60,
        )

        assert client.mall_id == "CUSTOM_MALL"
        assert client.api_url == "https://custom.api.com"
        assert client.timeout == 60

    def test_configuration_from_settings(self, settings):
        """Client reads configuration from Django settings."""
        settings.EASYPAY_MALL_ID = "SETTINGS_MALL"
        settings.EASYPAY_API_URL = "https://settings.api.com"

        client = EasyPayClient()

        assert client.mall_id == "SETTINGS_MALL"
        assert client.api_url == "https://settings.api.com"

    def test_explicit_overrides_settings(self, settings):
        """Explicit parameters override Django settings."""
        settings.EASYPAY_MALL_ID = "SETTINGS_MALL"

        client = EasyPayClient(mall_id="EXPLICIT_MALL")

        assert client.mall_id == "EXPLICIT_MALL"

    def test_empty_mall_id_raises_error(self, settings):
        """Empty mall_id raises ConfigurationError."""
        with pytest.raises(ConfigurationError, match="EASYPAY_MALL_ID"):
            EasyPayClient(mall_id="")

    def test_singleton_instance_exists(self):
        """Default singleton instance is available."""
        assert easypay_client is not None
        assert isinstance(easypay_client, EasyPayClient)


# ============================================================
# Payment Registration Tests
# ============================================================


class TestRegisterPayment:
    """Tests for payment registration API."""

    @responses.activate
    def test_register_success(self, easypay_client, payment, mock_register_success):
        """Successful payment registration returns authPageUrl."""
        responses.add(
            responses.POST,
            "https://testpgapi.easypay.co.kr/api/ep9/trades/webpay",
            json=mock_register_success,
            status=200,
        )

        result = easypay_client.register_payment(
            payment=payment,
            return_url="https://example.com/callback/",
            goods_name="테스트 상품",
            customer_name="홍길동",
            device_type_code="PC",
        )

        assert result["resCd"] == "0000"
        assert "authPageUrl" in result
        assert result["authPageUrl"].startswith("https://")

    @responses.activate
    def test_register_with_mobile_device(
        self, easypay_client, payment, mock_register_success
    ):
        """Registration works with MOBILE device type."""
        responses.add(
            responses.POST,
            "https://testpgapi.easypay.co.kr/api/ep9/trades/webpay",
            json=mock_register_success,
            status=200,
        )

        result = easypay_client.register_payment(
            payment=payment,
            return_url="https://example.com/callback/",
            goods_name="테스트 상품",
            device_type_code="MOBILE",
        )

        # Verify request payload
        request_body = responses.calls[0].request.body.decode()
        assert '"deviceTypeCode": "MOBILE"' in request_body

    @responses.activate
    def test_register_truncates_long_goods_name(
        self, easypay_client, payment, mock_register_success
    ):
        """Goods name is truncated to 80 characters."""
        responses.add(
            responses.POST,
            "https://testpgapi.easypay.co.kr/api/ep9/trades/webpay",
            json=mock_register_success,
            status=200,
        )

        long_name = "A" * 100  # Longer than 80 chars

        easypay_client.register_payment(
            payment=payment,
            return_url="https://example.com/callback/",
            goods_name=long_name,
        )

        request_body = responses.calls[0].request.body.decode()
        assert "A" * 80 in request_body
        assert "A" * 81 not in request_body

    @responses.activate
    def test_register_failure_raises_error(
        self, easypay_client, payment, mock_register_failure
    ):
        """Failed registration raises PaymentRegistrationError."""
        responses.add(
            responses.POST,
            "https://testpgapi.easypay.co.kr/api/ep9/trades/webpay",
            json=mock_register_failure,
            status=200,
        )

        with pytest.raises(PaymentRegistrationError) as exc_info:
            easypay_client.register_payment(
                payment=payment,
                return_url="https://example.com/callback/",
                goods_name="테스트 상품",
            )

        assert exc_info.value.code == "E101"
        assert "필수 파라미터" in exc_info.value.message

    @responses.activate
    def test_register_fires_signal(
        self, easypay_client, payment, mock_register_success
    ):
        """Successful registration fires payment_registered signal."""
        responses.add(
            responses.POST,
            "https://testpgapi.easypay.co.kr/api/ep9/trades/webpay",
            json=mock_register_success,
            status=200,
        )

        from easypay.signals import payment_registered

        receiver = MagicMock()
        payment_registered.connect(receiver)

        try:
            easypay_client.register_payment(
                payment=payment,
                return_url="https://example.com/callback/",
                goods_name="테스트 상품",
            )

            assert receiver.called
            call_kwargs = receiver.call_args[1]
            assert call_kwargs["payment"] == payment
            assert "auth_page_url" in call_kwargs
        finally:
            payment_registered.disconnect(receiver)


# ============================================================
# Payment Approval Tests
# ============================================================


class TestApprovePayment:
    """Tests for payment approval API."""

    @responses.activate
    @freeze_time("2025-12-23 14:30:00")
    def test_approve_success(self, easypay_client, payment, mock_approve_success):
        """Successful approval returns PG transaction data."""
        responses.add(
            responses.POST,
            "https://testpgapi.easypay.co.kr/api/ep9/trades/approval",
            json=mock_approve_success,
            status=200,
        )

        result = easypay_client.approve_payment(
            payment=payment,
            authorization_id="AUTH_ID_FROM_CALLBACK",
        )

        assert result["resCd"] == "0000"
        assert "pgTid" in result
        assert "paymentInfo" in result
        assert result["paymentInfo"]["cardInfo"]["cardName"] == "신한카드"

    @responses.activate
    def test_approve_includes_unique_transaction_id(
        self, easypay_client, payment, mock_approve_success
    ):
        """Approval request includes unique shopTransactionId."""
        responses.add(
            responses.POST,
            "https://testpgapi.easypay.co.kr/api/ep9/trades/approval",
            json=mock_approve_success,
            status=200,
        )

        easypay_client.approve_payment(payment=payment, authorization_id="AUTH123")

        request_body = responses.calls[0].request.body.decode()
        assert "shopTransactionId" in request_body
        # Transaction ID should be 32 chars hex
        import json

        body = json.loads(request_body)
        assert len(body["shopTransactionId"]) == 32

    @responses.activate
    def test_approve_failure_raises_error(
        self, easypay_client, payment, mock_approve_failure
    ):
        """Failed approval raises PaymentApprovalError."""
        responses.add(
            responses.POST,
            "https://testpgapi.easypay.co.kr/api/ep9/trades/approval",
            json=mock_approve_failure,
            status=200,
        )

        with pytest.raises(PaymentApprovalError) as exc_info:
            easypay_client.approve_payment(payment=payment, authorization_id="AUTH123")

        assert exc_info.value.code == "E501"

    @responses.activate
    def test_approve_fires_success_signal(
        self, easypay_client, payment, mock_approve_success
    ):
        """Successful approval fires payment_approved signal."""
        responses.add(
            responses.POST,
            "https://testpgapi.easypay.co.kr/api/ep9/trades/approval",
            json=mock_approve_success,
            status=200,
        )

        from easypay.signals import payment_approved

        receiver = MagicMock()
        payment_approved.connect(receiver)

        try:
            easypay_client.approve_payment(payment=payment, authorization_id="AUTH123")

            assert receiver.called
            call_kwargs = receiver.call_args[1]
            assert call_kwargs["payment"] == payment
            assert "approval_data" in call_kwargs
            assert (
                call_kwargs["approval_data"]["pg_tid"] == "PGTID1234567890123456789012"
            )
        finally:
            payment_approved.disconnect(receiver)

    @responses.activate
    def test_approve_failure_fires_failed_signal(
        self, easypay_client, payment, mock_approve_failure
    ):
        """Failed approval fires payment_failed signal."""
        responses.add(
            responses.POST,
            "https://testpgapi.easypay.co.kr/api/ep9/trades/approval",
            json=mock_approve_failure,
            status=200,
        )

        from easypay.signals import payment_failed

        receiver = MagicMock()
        payment_failed.connect(receiver)

        try:
            with pytest.raises(PaymentApprovalError):
                easypay_client.approve_payment(
                    payment=payment, authorization_id="AUTH123"
                )

            assert receiver.called
            call_kwargs = receiver.call_args[1]
            assert call_kwargs["payment"] == payment
            assert call_kwargs["error_code"] == "E501"
            assert call_kwargs["stage"] == "approval"
        finally:
            payment_failed.disconnect(receiver)


# ============================================================
# Payment Cancellation Tests
# ============================================================


class TestCancelPayment:
    """Tests for payment cancellation API."""

    @responses.activate
    def test_cancel_full_success(
        self, easypay_client, completed_payment, mock_cancel_success
    ):
        """Full cancellation succeeds with pg_tid."""
        responses.add(
            responses.POST,
            "https://testpgapi.easypay.co.kr/api/ep9/trades/cancel",
            json=mock_cancel_success,
            status=200,
        )

        result = easypay_client.cancel_payment(
            payment=completed_payment,
            cancel_type_code="40",
        )

        assert result["resCd"] == "0000"
        assert result["cancelAmount"] == 29900

    @responses.activate
    def test_cancel_partial_success(
        self, easypay_client, completed_payment, mock_cancel_success
    ):
        """Partial cancellation succeeds with cancel_amount."""
        partial_response = mock_cancel_success.copy()
        partial_response["cancelAmount"] = 10000

        responses.add(
            responses.POST,
            "https://testpgapi.easypay.co.kr/api/ep9/trades/cancel",
            json=partial_response,
            status=200,
        )

        result = easypay_client.cancel_payment(
            payment=completed_payment,
            cancel_type_code="41",
            cancel_amount=10000,
        )

        assert result["resCd"] == "0000"
        assert result["cancelAmount"] == 10000

        # Verify request includes cancel amount
        request_body = responses.calls[0].request.body.decode()
        assert '"cancelAmount": 10000' in request_body

    def test_cancel_without_pg_tid_raises_error(self, easypay_client, payment):
        """Cancellation without pg_tid raises error."""
        assert payment.pg_tid == ""

        with pytest.raises(PaymentCancellationError) as exc_info:
            easypay_client.cancel_payment(payment=payment)

        assert exc_info.value.code == "NO_PG_TID"

    def test_partial_cancel_without_amount_raises_error(
        self, easypay_client, completed_payment
    ):
        """Partial cancellation without amount raises error."""
        with pytest.raises(PaymentCancellationError) as exc_info:
            easypay_client.cancel_payment(
                payment=completed_payment,
                cancel_type_code="41",
                cancel_amount=None,
            )

        assert exc_info.value.code == "NO_CANCEL_AMOUNT"

    @responses.activate
    def test_cancel_with_reason(
        self, easypay_client, completed_payment, mock_cancel_success
    ):
        """Cancellation can include a reason."""
        import json

        responses.add(
            responses.POST,
            "https://testpgapi.easypay.co.kr/api/ep9/trades/cancel",
            json=mock_cancel_success,
            status=200,
        )

        easypay_client.cancel_payment(
            payment=completed_payment,
            cancel_reason="고객 요청에 의한 취소",
        )

        # Parse JSON body to check Korean text (avoids Unicode escape issues)
        request_body = json.loads(responses.calls[0].request.body.decode())
        assert request_body.get("cancelReason") == "고객 요청에 의한 취소"

    @responses.activate
    def test_cancel_truncates_long_reason(
        self, easypay_client, completed_payment, mock_cancel_success
    ):
        """Cancel reason is truncated to 100 characters."""
        responses.add(
            responses.POST,
            "https://testpgapi.easypay.co.kr/api/ep9/trades/cancel",
            json=mock_cancel_success,
            status=200,
        )

        long_reason = "R" * 150

        easypay_client.cancel_payment(
            payment=completed_payment,
            cancel_reason=long_reason,
        )

        request_body = responses.calls[0].request.body.decode()
        assert "R" * 100 in request_body
        assert "R" * 101 not in request_body

    @responses.activate
    def test_cancel_failure_raises_error(
        self, easypay_client, completed_payment, mock_cancel_failure
    ):
        """Failed cancellation raises PaymentCancellationError."""
        responses.add(
            responses.POST,
            "https://testpgapi.easypay.co.kr/api/ep9/trades/cancel",
            json=mock_cancel_failure,
            status=200,
        )

        with pytest.raises(PaymentCancellationError) as exc_info:
            easypay_client.cancel_payment(payment=completed_payment)

        assert exc_info.value.code == "E601"
        assert "이미 취소된 거래" in exc_info.value.message

    @responses.activate
    def test_cancel_fires_signal(
        self, easypay_client, completed_payment, mock_cancel_success
    ):
        """Successful cancellation fires payment_cancelled signal."""
        responses.add(
            responses.POST,
            "https://testpgapi.easypay.co.kr/api/ep9/trades/cancel",
            json=mock_cancel_success,
            status=200,
        )

        from easypay.signals import payment_cancelled

        receiver = MagicMock()
        payment_cancelled.connect(receiver)

        try:
            easypay_client.cancel_payment(payment=completed_payment)

            assert receiver.called
            call_kwargs = receiver.call_args[1]
            assert call_kwargs["payment"] == completed_payment
            assert call_kwargs["cancel_type_code"] == "40"
            assert call_kwargs["cancel_amount"] == int(completed_payment.amount)
        finally:
            payment_cancelled.disconnect(receiver)


# ============================================================
# Transaction Status Tests
# ============================================================


class TestGetTransactionStatus:
    """Tests for transaction status inquiry API."""

    @responses.activate
    def test_status_success(
        self, easypay_client, completed_payment, mock_status_success
    ):
        """Status inquiry returns transaction details."""
        responses.add(
            responses.POST,
            "https://testpgapi.easypay.co.kr/api/ep9/trades/status",
            json=mock_status_success,
            status=200,
        )

        result = easypay_client.get_transaction_status(payment=completed_payment)

        assert result["resCd"] == "0000"
        assert result["payStatusNm"] == "승인완료"
        assert result["cancelYn"] == "N"

    @responses.activate
    def test_status_with_explicit_date(
        self, easypay_client, completed_payment, mock_status_success
    ):
        """Status inquiry uses explicit transaction date."""
        responses.add(
            responses.POST,
            "https://testpgapi.easypay.co.kr/api/ep9/trades/status",
            json=mock_status_success,
            status=200,
        )

        easypay_client.get_transaction_status(
            payment=completed_payment,
            transaction_date="20251220",
        )

        request_body = responses.calls[0].request.body.decode()
        assert '"transactionDate": "20251220"' in request_body

    @responses.activate
    def test_status_uses_payment_created_date(
        self, easypay_client, completed_payment, mock_status_success
    ):
        """Status inquiry uses payment creation date when not specified."""
        responses.add(
            responses.POST,
            "https://testpgapi.easypay.co.kr/api/ep9/trades/status",
            json=mock_status_success,
            status=200,
        )

        # completed_payment has created_at set
        easypay_client.get_transaction_status(payment=completed_payment)

        request_body = responses.calls[0].request.body.decode()
        assert "transactionDate" in request_body

    @responses.activate
    def test_status_cancelled_transaction(
        self, easypay_client, cancelled_payment, mock_status_cancelled
    ):
        """Status inquiry shows cancelled status."""
        responses.add(
            responses.POST,
            "https://testpgapi.easypay.co.kr/api/ep9/trades/status",
            json=mock_status_cancelled,
            status=200,
        )

        result = easypay_client.get_transaction_status(payment=cancelled_payment)

        assert result["payStatusNm"] == "취소완료"
        assert result["cancelYn"] == "Y"

    @responses.activate
    def test_status_failure_raises_error(self, easypay_client, payment):
        """Failed status inquiry raises PaymentInquiryError."""
        responses.add(
            responses.POST,
            "https://testpgapi.easypay.co.kr/api/ep9/trades/status",
            json={"resCd": "E701", "resMsg": "거래 내역 없음"},
            status=200,
        )

        with pytest.raises(PaymentInquiryError) as exc_info:
            easypay_client.get_transaction_status(payment=payment)

        assert exc_info.value.code == "E701"


# ============================================================
# Receipt URL Tests
# ============================================================


class TestGetReceiptUrl:
    """Tests for receipt URL generation."""

    def test_receipt_url_test_environment(self):
        """Test environment uses test receipt URL."""
        client = EasyPayClient(api_url="https://testpgapi.easypay.co.kr")

        url = client.get_receipt_url("PGTID12345")

        assert "testpgweb.easypay.co.kr" in url
        assert "PGTID12345" in url

    def test_receipt_url_production_environment(self):
        """Production environment uses production receipt URL."""
        client = EasyPayClient(api_url="https://pgapi.easypay.co.kr")

        url = client.get_receipt_url("PGTID12345")

        assert "pgweb.easypay.co.kr" in url
        assert "testpgweb" not in url
        assert "PGTID12345" in url


# ============================================================
# Order ID Extraction Tests
# ============================================================


@pytest.mark.django_db
class TestGetOrderId:
    """Tests for order ID extraction from payment instance."""

    def test_order_id_from_hash_id(self, easypay_client):
        """Order ID extracted from hash_id field."""
        payment = MagicMock()
        payment.hash_id = "abc123def456"
        payment.order_id = None

        order_id = easypay_client._get_order_id(payment)

        assert order_id == "abc123def456"

    def test_order_id_from_order_id_field(self, easypay_client):
        """Order ID extracted from order_id field."""
        payment = MagicMock()
        payment.hash_id = None
        payment.order_id = "ORDER-12345"
        payment.pk = 999

        order_id = easypay_client._get_order_id(payment)

        assert order_id == "ORDER-12345"

    def test_order_id_fallback_to_pk(self, easypay_client):
        """Order ID falls back to primary key."""
        payment = MagicMock()
        payment.hash_id = None
        payment.order_id = None
        payment.id = None
        payment.pk = 12345

        order_id = easypay_client._get_order_id(payment)

        assert order_id == "12345"


# ============================================================
# Network Error Handling Tests
# ============================================================


class TestNetworkErrorHandling:
    """Tests for network error handling."""

    @responses.activate
    def test_timeout_raises_error(self, easypay_client, payment):
        """Request timeout raises EasyPayError."""
        import requests

        responses.add(
            responses.POST,
            "https://testpgapi.easypay.co.kr/api/ep9/trades/webpay",
            body=requests.exceptions.Timeout("Connection timed out"),
        )

        with pytest.raises(EasyPayError) as exc_info:
            easypay_client.register_payment(
                payment=payment,
                return_url="https://example.com/callback/",
                goods_name="테스트",
            )

        # The PaymentRegistrationError wraps EasyPayError
        assert (
            "timeout" in exc_info.value.message.lower()
            or exc_info.value.code == "TIMEOUT"
        )

    @responses.activate
    def test_connection_error_raises_error(self, easypay_client, payment):
        """Connection error raises EasyPayError."""
        import requests

        responses.add(
            responses.POST,
            "https://testpgapi.easypay.co.kr/api/ep9/trades/webpay",
            body=requests.exceptions.ConnectionError("Connection refused"),
        )

        with pytest.raises((EasyPayError, PaymentRegistrationError)):
            easypay_client.register_payment(
                payment=payment,
                return_url="https://example.com/callback/",
                goods_name="테스트",
            )

    @responses.activate
    def test_http_500_raises_error(self, easypay_client, payment):
        """HTTP 500 error raises EasyPayError."""
        responses.add(
            responses.POST,
            "https://testpgapi.easypay.co.kr/api/ep9/trades/webpay",
            json={"error": "Internal Server Error"},
            status=500,
        )

        with pytest.raises((EasyPayError, PaymentRegistrationError)):
            easypay_client.register_payment(
                payment=payment,
                return_url="https://example.com/callback/",
                goods_name="테스트",
            )


# ============================================================
# API Response Code Tests
# ============================================================


class TestApiResponseCodes:
    """Tests for various API response codes."""

    @responses.activate
    @pytest.mark.parametrize(
        "res_cd,res_msg",
        [
            ("E101", "필수 파라미터 누락"),
            ("E201", "상점 ID 오류"),
            ("E401", "인증 실패"),
            ("R106", "deviceTypeCode값이 유효하지 않습니다"),
        ],
    )
    def test_error_response_codes(self, easypay_client, payment, res_cd, res_msg):
        """Various error codes are properly handled."""
        responses.add(
            responses.POST,
            "https://testpgapi.easypay.co.kr/api/ep9/trades/webpay",
            json={"resCd": res_cd, "resMsg": res_msg},
            status=200,
        )

        with pytest.raises(PaymentRegistrationError) as exc_info:
            easypay_client.register_payment(
                payment=payment,
                return_url="https://example.com/callback/",
                goods_name="테스트",
            )

        assert exc_info.value.code == res_cd
        assert res_msg in exc_info.value.message


# ============================================================
# Integration-like Tests (with all steps)
# ============================================================


@pytest.mark.django_db
class TestPaymentFlow:
    """Tests simulating complete payment flow."""

    @responses.activate
    def test_complete_payment_flow(
        self,
        easypay_client,
        payment,
        mock_register_success,
        mock_approve_success,
    ):
        """Complete flow: register → approve."""
        # Step 1: Register
        responses.add(
            responses.POST,
            "https://testpgapi.easypay.co.kr/api/ep9/trades/webpay",
            json=mock_register_success,
            status=200,
        )

        register_result = easypay_client.register_payment(
            payment=payment,
            return_url="https://example.com/callback/",
            goods_name="테스트 상품",
        )

        assert "authPageUrl" in register_result

        # Step 2: Approve (simulating callback with auth_id)
        responses.add(
            responses.POST,
            "https://testpgapi.easypay.co.kr/api/ep9/trades/approval",
            json=mock_approve_success,
            status=200,
        )

        approve_result = easypay_client.approve_payment(
            payment=payment,
            authorization_id="AUTH_ID_FROM_CALLBACK",
        )

        assert approve_result["pgTid"] == "PGTID1234567890123456789012"
        assert approve_result["paymentInfo"]["cardInfo"]["cardName"] == "신한카드"

    @responses.activate
    def test_payment_and_cancel_flow(
        self,
        db,
        easypay_client,
        mock_approve_success,
        mock_cancel_success,
    ):
        """Complete flow: approve → cancel."""
        from tests.models import Payment

        # Create a payment that will be approved
        payment = Payment.objects.create(
            amount=Decimal("29900"),
            order_id="FLOW-TEST-001",
        )

        # Step 1: Approve
        responses.add(
            responses.POST,
            "https://testpgapi.easypay.co.kr/api/ep9/trades/approval",
            json=mock_approve_success,
            status=200,
        )

        approve_result = easypay_client.approve_payment(
            payment=payment,
            authorization_id="AUTH_ID",
        )

        # Update payment with PG data
        payment.pg_tid = approve_result["pgTid"]
        payment.save()

        # Step 2: Cancel
        responses.add(
            responses.POST,
            "https://testpgapi.easypay.co.kr/api/ep9/trades/cancel",
            json=mock_cancel_success,
            status=200,
        )

        cancel_result = easypay_client.cancel_payment(payment=payment)

        assert cancel_result["resCd"] == "0000"
        assert cancel_result["cancelAmount"] == 29900
