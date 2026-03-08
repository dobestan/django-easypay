"""
EasyPay (KICC) PG API Client.

This module provides a complete client for EasyPay payment integration,
including registration, approval, cancellation, and status inquiry.

Usage:
    from easypay.client import EasyPayClient

    client = EasyPayClient()

    # Register payment (get authPageUrl)
    result = client.register_payment(
        payment=payment,
        return_url="https://example.com/callback/",
        goods_name="상품명",
        customer_name="고객명",
        device_type_code="PC"
    )
    auth_page_url = result["authPageUrl"]

    # Approve payment (after callback)
    result = client.approve_payment(payment=payment, authorization_id="id_from_callback")

    # Cancel payment (full or partial refund)
    result = client.cancel_payment(payment=payment, cancel_type="40")

    # Check transaction status
    result = client.get_transaction_status(payment=payment)
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import time
import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any, Literal, TypedDict

import requests
from django.conf import settings

from .exceptions import (
    ConfigurationError,
    EasyPayError,
    PaymentApprovalError,
    PaymentCancellationError,
    PaymentInquiryError,
    PaymentRegistrationError,
)

if TYPE_CHECKING:
    from .models import AbstractPayment

logger: logging.Logger = logging.getLogger(__name__)


# ============================================================
# TypedDict definitions for API responses
# ============================================================


class CardInfo(TypedDict, total=False):
    """Card information from EasyPay API."""

    cardName: str
    cardNo: str
    installmentMonth: str
    approvalNo: str


class TaxInfo(TypedDict, total=False):
    """Tax information for composite taxation."""

    taxAmount: int
    freeAmount: int
    vatAmount: int


class PaymentInfo(TypedDict, total=False):
    """Payment information from EasyPay approval response."""

    payMethodTypeCode: str
    approvalAmount: int
    cardInfo: CardInfo


class RegisterPaymentResponse(TypedDict, total=False):
    """Response from payment registration API."""

    resCd: str
    resMsg: str
    authPageUrl: str
    mallId: str
    shopOrderNo: str


class ApprovePaymentResponse(TypedDict, total=False):
    """Response from payment approval API."""

    resCd: str
    resMsg: str
    pgTid: str
    shopOrderNo: str
    amount: int
    paymentInfo: PaymentInfo


class CancelPaymentResponse(TypedDict, total=False):
    """Response from payment cancellation API."""

    resCd: str
    resMsg: str
    pgTid: str
    cancelAmount: int
    cancelDate: str
    cancelTime: str


class TransactionStatusResponse(TypedDict, total=False):
    """Response from transaction status inquiry API."""

    resCd: str
    resMsg: str
    pgTid: str
    shopOrderNo: str
    amount: int
    payStatusNm: str
    cancelYn: str
    approvalDt: str
    cancelDt: str


class EasyPayClient:
    """
    EasyPay PG API Client.

    Configuration (in Django settings):
        EASYPAY_MALL_ID: Merchant ID (default: "T0021792" for test)
        EASYPAY_API_URL: API base URL (default: "https://testpgapi.easypay.co.kr")

    Attributes:
        mall_id: Merchant ID from settings
        api_url: API base URL from settings
        timeout: Request timeout in seconds (default: 30)
    """

    # API Endpoints (common)
    ENDPOINT_REGISTER = "/api/ep9/trades/webpay"
    ENDPOINT_APPROVE = "/api/ep9/trades/approval"

    # Legacy endpoints (test environment)
    ENDPOINT_CANCEL_LEGACY = "/api/ep9/trades/cancel"
    ENDPOINT_STATUS_LEGACY = "/api/ep9/trades/status"

    # Production endpoints (new API)
    ENDPOINT_CANCEL_PROD = "/api/trades/revise"
    ENDPOINT_STATUS_PROD = "/api/trades/retrieveTransaction"

    # Receipt URL templates
    RECEIPT_URL_PROD = "https://pgweb.easypay.co.kr/receipt/card?pgTid={pg_tid}"
    RECEIPT_URL_TEST = "https://testpgweb.easypay.co.kr/receipt/card?pgTid={pg_tid}"

    def __init__(
        self,
        mall_id: str | None = None,
        api_url: str | None = None,
        timeout: int = 30,
    ):
        """
        Initialize EasyPay client.

        Args:
            mall_id: Override merchant ID (default: from settings)
            api_url: Override API URL (default: from settings)
            timeout: Request timeout in seconds

        Raises:
            ConfigurationError: If mall_id is empty string or not configured
        """
        # Check for explicitly empty mall_id (not just None)
        if mall_id is not None and not mall_id:
            raise ConfigurationError("EASYPAY_MALL_ID is not configured")

        self.mall_id = (
            mall_id if mall_id is not None else getattr(settings, "EASYPAY_MALL_ID", "T0021792")
        )
        self.api_url = (
            api_url
            if api_url is not None
            else getattr(settings, "EASYPAY_API_URL", "https://testpgapi.easypay.co.kr")
        )
        self.secret_key: str = getattr(settings, "EASYPAY_SECRET_KEY", "easypay!KICCTEST")
        self.timeout = timeout

        if not self.mall_id:
            raise ConfigurationError("EASYPAY_MALL_ID is not configured")

    @property
    def is_test_mode(self) -> bool:
        return "testpgapi" in self.api_url

    def _generate_msg_auth_value(self, data: str) -> str:
        """
        Generate HMAC SHA256 message authentication value.

        Required for cancel/revise API calls in production environment.

        Args:
            data: Data string to hash (e.g., "pgCno|shopTransactionId")

        Returns:
            HMAC SHA256 hash as hexadecimal string
        """
        return hmac.new(
            self.secret_key.encode("utf-8"),
            data.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

    # Transport-layer exceptions that are safe to retry.
    # These indicate network/infrastructure failures, NOT business logic errors.
    _RETRYABLE_EXCEPTIONS: tuple[type[Exception], ...] = (
        requests.exceptions.Timeout,
        requests.exceptions.ConnectionError,
        OSError,
        ConnectionError,
    )

    # Max retries for transient network failures (1s → 2s → 4s backoff)
    _MAX_RETRIES: int = 3
    _RETRY_BACKOFF_BASE: float = 1.0

    def _is_retryable_http_status(self, status_code: int) -> bool:
        """Check if an HTTP status code is safe to retry (server-side errors only)."""
        return status_code in (502, 503, 504)

    def _request(self, endpoint: str, payload: dict[str, Any]) -> dict[str, Any]:
        """
        Send API request to EasyPay with retry for transient network failures.

        Retries up to 3 times with exponential backoff (1s, 2s, 4s) for
        transport-layer failures only: timeouts, connection errors, and
        HTTP 502/503/504. Business logic errors (payment declined, invalid
        card, duplicate transaction, etc.) are NEVER retried.

        Args:
            endpoint: API endpoint path
            payload: Request payload

        Returns:
            API response as dict

        Raises:
            EasyPayError: On API error or network failure (after retries exhausted)
        """
        url = f"{self.api_url}{endpoint}"

        logger.info(
            "EasyPay API request",
            extra={
                "endpoint": endpoint,
                "mall_id": self.mall_id,
                "shop_order_no": payload.get("shopOrderNo"),
            },
        )

        last_exception: Exception | None = None

        for attempt in range(1, self._MAX_RETRIES + 1):
            try:
                response = requests.post(
                    url,
                    json=payload,
                    headers={"Content-Type": "application/json"},
                    timeout=self.timeout,
                )

                # Retry on server-side HTTP errors (502, 503, 504)
                if self._is_retryable_http_status(response.status_code):
                    logger.warning(
                        "EasyPay API server error (retryable)",
                        extra={
                            "endpoint": endpoint,
                            "status_code": response.status_code,
                            "attempt": attempt,
                            "max_retries": self._MAX_RETRIES,
                        },
                    )
                    last_exception = requests.exceptions.HTTPError(
                        f"HTTP {response.status_code}", response=response
                    )
                    if attempt < self._MAX_RETRIES:
                        backoff = self._RETRY_BACKOFF_BASE * (2 ** (attempt - 1))
                        time.sleep(backoff)
                        continue
                    # Final attempt failed — fall through to raise
                    raise EasyPayError(
                        message=f"API request failed after {self._MAX_RETRIES} retries: "
                        f"HTTP {response.status_code}",
                        code="REQUEST_ERROR",
                    ) from last_exception

                response.raise_for_status()
                data = response.json()

                # Business logic errors — NEVER retry these
                if data.get("resCd") != "0000":
                    safe_payload = {
                        k: v
                        for k, v in payload.items()
                        if k not in ("msgAuthValue", "authorizationId")
                    }
                    logger.warning(
                        "EasyPay API error",
                        extra={
                            "endpoint": endpoint,
                            "res_cd": data.get("resCd"),
                            "res_msg": data.get("resMsg"),
                            "request_payload": safe_payload,
                        },
                    )
                    raise EasyPayError(
                        message=data.get("resMsg", "Unknown error"),
                        code=data.get("resCd", "UNKNOWN"),
                        response=data,
                    )

                logger.info(
                    "EasyPay API success",
                    extra={
                        "endpoint": endpoint,
                        "res_cd": data.get("resCd"),
                        **({"attempt": attempt} if attempt > 1 else {}),
                    },
                )
                return dict(data)

            except self._RETRYABLE_EXCEPTIONS as e:
                last_exception = e
                logger.warning(
                    "EasyPay API transient failure",
                    extra={
                        "endpoint": endpoint,
                        "error": str(e),
                        "error_type": type(e).__name__,
                        "attempt": attempt,
                        "max_retries": self._MAX_RETRIES,
                    },
                )

                if attempt < self._MAX_RETRIES:
                    backoff = self._RETRY_BACKOFF_BASE * (2 ** (attempt - 1))
                    time.sleep(backoff)
                    continue

                # All retries exhausted
                if isinstance(e, requests.exceptions.Timeout):
                    raise EasyPayError(
                        message=f"API request timeout after {self._MAX_RETRIES} retries",
                        code="TIMEOUT",
                    ) from None
                raise EasyPayError(
                    message=f"API request failed after {self._MAX_RETRIES} retries: {e}",
                    code="REQUEST_ERROR",
                ) from e

            except requests.exceptions.RequestException as e:
                # Non-retryable request errors (e.g., invalid URL, SSL cert error)
                # Fail immediately — do not retry
                logger.error(
                    "EasyPay API request failed (non-retryable)",
                    extra={"endpoint": endpoint, "error": str(e)},
                )
                raise EasyPayError(
                    message=f"API request failed: {e}",
                    code="REQUEST_ERROR",
                ) from e

        # Should not reach here, but guard against it
        raise EasyPayError(
            message="API request failed: unexpected retry loop exit",
            code="REQUEST_ERROR",
        )

    def register_payment(
        self,
        payment: AbstractPayment,
        return_url: str,
        goods_name: str,
        customer_name: str = "",
        device_type_code: Literal["PC", "MOBILE"] = "PC",
        pay_method_type_code: str = "11",
    ) -> dict[str, Any]:
        """
        Register payment with EasyPay and get authPageUrl.

        This is the first step in the payment flow. The returned authPageUrl
        should be used to redirect the user to EasyPay's payment page.

        Args:
            payment: Payment instance (must have amount and a unique identifier)
            return_url: URL to redirect after payment (must include payment identifier)
            goods_name: Product name (max 80 bytes)
            customer_name: Customer name for display
            device_type_code: EasyPay deviceTypeCode - "PC" or "MOBILE"
            pay_method_type_code: EasyPay payMethodTypeCode ("11"=card, "21"=bank, "31"=phone)

        Returns:
            dict containing:
                - authPageUrl: URL to redirect user to payment page
                - and other response fields

        Raises:
            PaymentRegistrationError: On registration failure
        """
        # Get order identifier (hash_id, order_id, or pk)
        order_id = self._get_order_id(payment)

        payload: dict[str, Any] = {
            "mallId": self.mall_id,
            "shopOrderNo": order_id,
            "amount": int(payment.amount),
            "payMethodTypeCode": pay_method_type_code,
            "currency": "00",
            "clientTypeCode": "00",
            "deviceTypeCode": device_type_code,
            "returnUrl": return_url,
            "orderInfo": {
                "goodsName": goods_name[:80],
                "customerInfo": {
                    "customerName": customer_name or order_id[-4:],
                },
            },
        }

        # Tax information (taxInfo) is OPTIONAL
        # Only include for composite taxation (복합과세) - mix of taxable + tax-free items
        # For simple taxable payments, EasyPay auto-calculates using merchant settings
        tax_free_amount = getattr(payment, "tax_free_amount", None) or 0

        # Only send taxInfo when there's a tax-free portion (composite taxation)
        if tax_free_amount and int(tax_free_amount) > 0:
            supply_amount = getattr(payment, "supply_amount", None) or 0
            vat_amount = getattr(payment, "vat_amount", None) or 0
            tax_amount = int(supply_amount) + int(vat_amount)
            free_amount = int(tax_free_amount)

            payload["taxInfo"] = {
                "taxAmount": tax_amount,
                "freeAmount": free_amount,
                "vatAmount": int(vat_amount),
            }

        try:
            result = self._request(self.ENDPOINT_REGISTER, payload)

            logger.info(
                "Payment %s registered with EasyPay",
                payment.pk,
                extra={
                    "payment_id": payment.pk,
                    "order_id": order_id,
                    "amount": int(payment.amount),
                    "device_type_code": device_type_code,
                    "has_auth_page_url": bool(result.get("authPageUrl")),
                },
            )

            # Fire signal with error isolation — receiver failures must not
            # prevent the payment flow from completing.
            from .signals import payment_registered

            self._send_signal_safe(
                payment_registered,
                sender=payment.__class__,
                payment=payment,
                auth_page_url=result.get("authPageUrl"),
            )

            return result
        except EasyPayError as e:
            logger.warning(
                "Payment registration failed",
                extra={
                    "payment_id": payment.pk,
                    "order_id": order_id,
                    "error_code": e.code,
                    "error_message": e.message,
                },
            )
            raise PaymentRegistrationError(
                message=e.message,
                code=e.code,
                response=e.response,
            ) from e

    def approve_payment(
        self,
        payment: AbstractPayment,
        authorization_id: str,
    ) -> dict[str, Any]:
        """
        Approve payment after user completes authentication.

        This is called after the user returns from EasyPay's payment page
        with an authorizationId in the callback URL.

        Args:
            payment: Payment instance
            authorization_id: EasyPay authorizationId from callback URL parameter

        Returns:
            dict containing:
                - pgTid: PG transaction ID
                - paymentInfo: Payment details (card info, etc.)
                - and other response fields

        Raises:
            PaymentApprovalError: On approval failure
        """
        order_id = self._get_order_id(payment)

        payload = {
            "mallId": self.mall_id,
            "shopTransactionId": uuid.uuid4().hex[:32],  # Required unique ID
            "shopOrderNo": order_id,
            "authorizationId": authorization_id,
            "approvalReqDate": datetime.now().strftime("%Y%m%d"),
        }

        try:
            result = self._request(self.ENDPOINT_APPROVE, payload)

            pg_tid = result.get("pgTid") or result.get("pgCno") or ""
            payment_info = result.get("paymentInfo", {})
            pay_method_type_code = payment_info.get("payMethodTypeCode", "")
            card_info = payment_info.get("cardInfo", {})
            card_name = card_info.get("cardName") or card_info.get("issuerName") or ""
            card_no = card_info.get("cardNo", "")

            approved_amount = int(payment_info.get("approvalAmount") or result.get("amount") or 0)
            expected_amount = int(payment.amount)

            if approved_amount != expected_amount:
                logger.error(
                    "Payment amount mismatch detected",
                    extra={
                        "payment_id": payment.pk,
                        "order_id": order_id,
                        "expected_amount": expected_amount,
                        "approved_amount": approved_amount,
                        "pg_tid": pg_tid,
                    },
                )

            logger.info(
                "Payment approved by EasyPay",
                extra={
                    "payment_id": payment.pk,
                    "order_id": order_id,
                    "amount": int(payment.amount),
                    "pg_tid": pg_tid,
                    "pay_method_type_code": pay_method_type_code,
                    "card_name": card_name,
                },
            )

            from .signals import payment_approved

            self._send_signal_safe(
                payment_approved,
                sender=payment.__class__,
                payment=payment,
                approval_data={
                    "pg_tid": pg_tid,
                    "pay_method_type_code": pay_method_type_code,
                    "card_name": card_name,
                    "card_no": card_no,
                },
            )

            result["pg_tid"] = pg_tid
            result["pay_method_type_code"] = pay_method_type_code
            result["card_name"] = card_name
            result["card_no"] = card_no

            return result
        except EasyPayError as e:
            # Audit log: payment approval failure
            logger.warning(
                "Payment approval failed",
                extra={
                    "payment_id": payment.pk,
                    "order_id": order_id,
                    "error_code": e.code,
                    "error_message": e.message,
                },
            )

            # Fire failure signal with error isolation
            from .signals import payment_failed

            self._send_signal_safe(
                payment_failed,
                sender=payment.__class__,
                payment=payment,
                error_code=e.code,
                error_message=e.message,
                stage="approval",
            )

            raise PaymentApprovalError(
                message=e.message,
                code=e.code,
                response=e.response,
            ) from e

    def cancel_payment(
        self,
        payment: AbstractPayment,
        cancel_type_code: Literal["40", "41"] = "40",
        cancel_amount: int | None = None,
        cancel_reason: str = "",
    ) -> dict[str, Any]:
        """
        Cancel or refund a completed payment.

        Test environment uses legacy /api/ep9/trades/cancel endpoint.
        Production uses /api/trades/revise with HMAC SHA256 authentication.

        Args:
            payment: Payment instance (must have pg_tid)
            cancel_type_code: "40" for full cancel, "41" for partial
            cancel_amount: Amount to cancel (required for partial cancel)
            cancel_reason: Optional reason for cancellation

        Returns:
            dict containing cancellation response

        Raises:
            PaymentCancellationError: On cancellation failure
        """
        if not payment.pg_tid:
            raise PaymentCancellationError(
                message="PG transaction ID not found",
                code="NO_PG_TID",
            )

        order_id = self._get_order_id(payment)

        if cancel_type_code == "41" and not cancel_amount:
            raise PaymentCancellationError(
                message="Cancel amount required for partial cancellation",
                code="NO_CANCEL_AMOUNT",
            )

        if self.is_test_mode:
            endpoint = self.ENDPOINT_CANCEL_LEGACY
            payload: dict[str, Any] = {
                "mallId": self.mall_id,
                "shopOrderNo": order_id,
                "pgTid": payment.pg_tid,
                "cancelReqDate": datetime.now().strftime("%Y%m%d"),
                "cancelTypeCode": cancel_type_code,
            }
            if cancel_type_code == "41":
                payload["cancelAmount"] = cancel_amount
            if cancel_reason:
                payload["cancelReason"] = cancel_reason[:100]
        else:
            endpoint = self.ENDPOINT_CANCEL_PROD
            shop_transaction_id = uuid.uuid4().hex[:32]
            msg_auth_data = f"{payment.pg_tid}|{shop_transaction_id}"
            msg_auth_value = self._generate_msg_auth_value(msg_auth_data)

            req_date = datetime.now().strftime("%Y%m%d")
            payload = {
                "mallId": self.mall_id,
                "shopTransactionId": shop_transaction_id,
                "shopOrderNo": order_id,
                "pgCno": payment.pg_tid,
                "reviseTypeCode": cancel_type_code,
                "reviseReqDate": req_date,
                "cancelReqDate": req_date,
                "msgAuthValue": msg_auth_value,
            }
            if cancel_type_code == "41":
                payload["reviseAmount"] = cancel_amount
            if cancel_reason:
                payload["reviseMessage"] = cancel_reason[:100]

        effective_cancel_amount = cancel_amount or int(payment.amount)
        logger.warning(
            "Payment cancellation initiated",
            extra={
                "payment_id": payment.pk,
                "order_id": order_id,
                "pg_tid": payment.pg_tid,
                "cancel_type_code": cancel_type_code,
                "cancel_amount": effective_cancel_amount,
                "original_amount": int(payment.amount),
                "is_test_mode": self.is_test_mode,
            },
        )

        try:
            result = self._request(endpoint, payload)

            logger.info(
                "Payment cancelled successfully",
                extra={
                    "payment_id": payment.pk,
                    "order_id": order_id,
                    "pg_tid": payment.pg_tid,
                    "cancel_amount": effective_cancel_amount,
                },
            )

            from .signals import payment_cancelled

            self._send_signal_safe(
                payment_cancelled,
                sender=payment.__class__,
                payment=payment,
                cancel_type_code=cancel_type_code,
                cancel_amount=effective_cancel_amount,
                cancel_data=result,
            )

            return result
        except EasyPayError as e:
            logger.error(
                "Payment cancellation failed",
                extra={
                    "payment_id": payment.pk,
                    "order_id": order_id,
                    "pg_tid": payment.pg_tid,
                    "error_code": e.code,
                    "error_message": e.message,
                },
            )
            raise PaymentCancellationError(
                message=e.message,
                code=e.code,
                response=e.response,
            ) from e

    def get_transaction_status(
        self,
        payment: AbstractPayment,
        transaction_date: str | None = None,
    ) -> dict[str, Any]:
        """
        Query transaction status from PG.

        Test environment uses legacy /api/ep9/trades/status endpoint.
        Production uses /api/trades/retrieveTransaction.

        Args:
            payment: Payment instance
            transaction_date: Transaction date (YYYYMMDD), defaults to payment creation date

        Returns:
            dict containing transaction status information

        Raises:
            PaymentInquiryError: On inquiry failure
        """
        order_id = self._get_order_id(payment)

        if not transaction_date:
            created_at = getattr(payment, "created_at", None)
            if created_at:
                transaction_date = created_at.strftime("%Y%m%d")
            else:
                transaction_date = datetime.now().strftime("%Y%m%d")

        if self.is_test_mode:
            endpoint = self.ENDPOINT_STATUS_LEGACY
            payload: dict[str, Any] = {
                "mallId": self.mall_id,
                "shopOrderNo": order_id,
                "transactionDate": transaction_date,
            }
        else:
            endpoint = self.ENDPOINT_STATUS_PROD
            shop_transaction_id = uuid.uuid4().hex[:32]
            payload = {
                "mallId": self.mall_id,
                "shopTransactionId": shop_transaction_id,
                "shopOrderNo": order_id,
                "transactionDate": transaction_date,
            }

        logger.debug(
            "Querying transaction status",
            extra={
                "payment_id": payment.pk,
                "order_id": order_id,
                "pg_tid": payment.pg_tid,
                "transaction_date": transaction_date,
                "is_test_mode": self.is_test_mode,
            },
        )

        try:
            result = self._request(endpoint, payload)

            logger.debug(
                "Transaction status received",
                extra={
                    "payment_id": payment.pk,
                    "pay_status": result.get("payStatusNm"),
                    "cancel_yn": result.get("cancelYn"),
                },
            )

            return result
        except EasyPayError as e:
            logger.warning(
                "Transaction status inquiry failed",
                extra={
                    "payment_id": payment.pk,
                    "order_id": order_id,
                    "error_code": e.code,
                    "error_message": e.message,
                },
            )
            raise PaymentInquiryError(
                message=e.message,
                code=e.code,
                response=e.response,
            ) from e

    def get_receipt_url(self, pg_tid: str) -> str:
        """
        Generate card receipt URL for a transaction.

        Args:
            pg_tid: PG transaction ID

        Returns:
            Receipt URL string
        """
        # Use production URL if API URL is production
        if "testpgapi" in self.api_url:
            return self.RECEIPT_URL_TEST.format(pg_tid=pg_tid)
        return self.RECEIPT_URL_PROD.format(pg_tid=pg_tid)

    def _send_signal_safe(self, signal: Any, **kwargs: Any) -> None:
        """
        Send a Django signal with error isolation.

        If a signal receiver raises an exception, it is logged but does NOT
        propagate. This prevents a failing webhook handler or notification
        service from crashing the payment flow.

        Args:
            signal: Django Signal instance to send
            **kwargs: Arguments to pass to signal.send()
        """
        try:
            signal.send(**kwargs)
        except Exception:
            logger.exception(
                "Signal receiver error (isolated)",
                extra={
                    "signal": getattr(signal, "providing_args", signal.__class__.__name__),
                    "payment_id": getattr(kwargs.get("payment"), "pk", None),
                },
            )

    def _get_order_id(self, payment: AbstractPayment) -> str:
        """
        Extract order identifier from payment instance.

        Tries common identifier field names in order:
        - hash_id (sajudoctor style)
        - order_id (UUID style)
        - id/pk (fallback)

        Args:
            payment: Payment instance

        Returns:
            Order identifier as string
        """
        # Try common identifier fields
        for field in ("hash_id", "order_id", "id", "pk"):
            value = getattr(payment, field, None)
            if value:
                return str(value)

        # Fallback to primary key
        return str(payment.pk)


# Default singleton instance
# Import this for convenience: from easypay.client import easypay_client
easypay_client = EasyPayClient()
