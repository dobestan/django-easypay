"""
Abstract models for EasyPay payment integration.

Usage:
    from easypay.models import AbstractPayment, PaymentStatus

    class Payment(AbstractPayment):
        user = models.ForeignKey(User, on_delete=models.CASCADE)
        product = models.ForeignKey(Product, on_delete=models.CASCADE)

        class Meta:
            db_table = 'payments_payment'
"""

from __future__ import annotations

import logging
import uuid
from decimal import ROUND_HALF_UP, Decimal
from typing import TYPE_CHECKING, Any, Self

from django.db import models
from django.utils import timezone

if TYPE_CHECKING:
    pass

logger: logging.Logger = logging.getLogger(__name__)


class PaymentStatus(models.TextChoices):
    """Payment status choices for EasyPay transactions."""

    PENDING = "pending", "결제대기"
    COMPLETED = "completed", "결제완료"
    FAILED = "failed", "결제실패"
    CANCELLED = "cancelled", "취소"
    REFUNDED = "refunded", "환불"


PAY_METHOD_TYPE_CODES: dict[str, str] = {
    "11": "신용카드",
    "21": "계좌이체",
    "22": "가상계좌",
    "31": "휴대폰",
    "41": "선불결제",
    "42": "도서상품권",
    "43": "컬처상품권",
    "44": "스마트문화상품권",
    "45": "해피머니",
    "46": "틴캐시",
    "50": "간편결제",
}


def get_pay_method_display(code: str) -> str:
    return PAY_METHOD_TYPE_CODES.get(code, f"기타({code})" if code else "")


class AbstractPayment(models.Model):
    """
    Abstract base model for EasyPay payment integration.

    This model provides common fields for PG transaction tracking.
    Inherit from this model in your project and add your own fields
    (e.g., user, product, order references).

    Fields:
        hash_id: External-facing unique identifier (12-char UUID hex, for URLs)
        pg_tid: PG transaction ID from EasyPay (pgTid)
        authorization_id: Authorization ID from payment callback (authorizationId)
        amount: Payment amount in KRW
        status: Payment status (pending, completed, failed, cancelled, refunded)
        pay_method_type_code: Payment method code (payMethodTypeCode: 11=card, 21=bank, 31=phone)
        card_name: Card issuer name
        card_no: Card number (masked, e.g., "1234-****-****-5678")
        client_ip: Client IP address for fraud detection
        client_user_agent: User agent string
        created_at: When the payment was initiated
        paid_at: When the payment was completed
    """

    # External-facing Identifier (for URLs)
    hash_id = models.CharField(
        "해시 ID",
        max_length=12,
        unique=True,
        db_index=True,
        editable=False,
        help_text="External-facing unique identifier for URLs (auto-generated)",
    )

    # PG Transaction Information
    pg_tid = models.CharField(
        "PG 거래번호",
        max_length=100,
        blank=True,
        default="",
        db_index=True,
        help_text="EasyPay transaction ID (pgTid)",
    )
    authorization_id = models.CharField(
        "인증번호",
        max_length=100,
        blank=True,
        default="",
        db_index=True,
        help_text="EasyPay authorizationId from payment callback",
    )

    # Payment Amount
    amount = models.DecimalField(
        "결제금액",
        max_digits=10,
        decimal_places=0,
        help_text="Payment amount in KRW (total including tax)",
    )

    # Tax Information (Korean VAT: 10%)
    supply_amount = models.DecimalField(
        "공급가액",
        max_digits=10,
        decimal_places=0,
        default=0,
        help_text="Supply amount excluding VAT",
    )
    vat_amount = models.DecimalField(
        "부가세액",
        max_digits=10,
        decimal_places=0,
        default=0,
        help_text="VAT amount (10% of supply_amount for taxable)",
    )
    tax_free_amount = models.DecimalField(
        "면세금액",
        max_digits=10,
        decimal_places=0,
        default=0,
        help_text="Tax-free amount",
    )
    is_taxable = models.BooleanField(
        "과세 여부",
        default=True,
        help_text="True for taxable, False for tax-free transactions",
    )

    # Payment Status
    status = models.CharField(
        "결제상태",
        max_length=20,
        choices=PaymentStatus.choices,
        default=PaymentStatus.PENDING,
        db_index=True,
    )

    # Payment Method Information
    pay_method_type_code = models.CharField(
        "결제수단",
        max_length=20,
        blank=True,
        default="",
        help_text="EasyPay payMethodTypeCode (11=card, 21=bank, 31=phone)",
    )
    card_name = models.CharField(
        "카드사",
        max_length=50,
        blank=True,
        default="",
        help_text="Card issuer name",
    )
    card_no = models.CharField(
        "카드번호",
        max_length=20,
        blank=True,
        default="",
        help_text="Masked card number",
    )

    # Client Tracking (for fraud detection)
    client_ip = models.GenericIPAddressField(
        "클라이언트 IP",
        null=True,
        blank=True,
        help_text="Client IP address at payment time",
    )
    client_user_agent = models.CharField(
        "User Agent",
        max_length=500,
        blank=True,
        default="",
        help_text="Browser user agent string",
    )

    # Timestamps
    created_at = models.DateTimeField(
        "생성일시",
        auto_now_add=True,
        db_index=True,
    )
    paid_at = models.DateTimeField(
        "결제일시",
        null=True,
        blank=True,
        db_index=True,
    )

    class Meta:
        abstract = True
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"Payment {self.pk} - {self.get_status_display()} ({self.amount:,.0f}원)"

    def save(self, *args: Any, **kwargs: Any) -> None:
        if not self.hash_id:
            self.hash_id = uuid.uuid4().hex[:12]

        if self._should_calculate_tax():
            self.calculate_tax()

        super().save(*args, **kwargs)

    def _should_calculate_tax(self) -> bool:
        """Check if tax should be auto-calculated."""
        if not self.amount:
            return False
        return not (self.supply_amount and self.vat_amount)

    def calculate_tax(self) -> None:
        """Calculate supply_amount and vat_amount from total amount (Korean VAT 10%)."""
        if not self.amount:
            return

        amount = Decimal(str(self.amount))

        if self.is_taxable:
            self.supply_amount = (amount / Decimal("1.1")).quantize(
                Decimal("1"), rounding=ROUND_HALF_UP
            )
            self.vat_amount = amount - self.supply_amount
            self.tax_free_amount = Decimal("0")
        else:
            self.supply_amount = Decimal("0")
            self.vat_amount = Decimal("0")
            self.tax_free_amount = amount

    @property
    def is_paid(self) -> bool:
        """Check if payment is completed."""
        return self.status == PaymentStatus.COMPLETED

    @property
    def is_pending(self) -> bool:
        """Check if payment is pending."""
        return self.status == PaymentStatus.PENDING

    @property
    def is_cancelled(self) -> bool:
        """Check if payment is cancelled or refunded."""
        return self.status in (PaymentStatus.CANCELLED, PaymentStatus.REFUNDED)

    @property
    def can_cancel(self) -> bool:
        """Check if payment can be cancelled."""
        return self.status == PaymentStatus.COMPLETED and bool(self.pg_tid)

    def get_pay_method_type_display(self) -> str:
        return get_pay_method_display(self.pay_method_type_code)

    def mark_as_paid(
        self, pg_tid: str = "", authorization_id: str = "", **extra_fields: Any
    ) -> None:
        """
        Mark payment as completed.

        Args:
            pg_tid: PG transaction ID (EasyPay pgTid)
            authorization_id: Authorization ID (EasyPay authorizationId)
            **extra_fields: Additional fields to update (card_name, card_no, etc.)
        """
        previous_status = self.status
        self.status = PaymentStatus.COMPLETED
        self.paid_at = timezone.now()

        if pg_tid:
            self.pg_tid = pg_tid
        if authorization_id:
            self.authorization_id = authorization_id

        # Get valid field names for this model
        valid_field_names = {f.name for f in self._meta.get_fields() if f.concrete}

        # Only update fields that exist on the model
        valid_extra_fields = []
        for field, value in extra_fields.items():
            if field in valid_field_names:
                setattr(self, field, value)
                valid_extra_fields.append(field)

        update_fields = [
            "status",
            "paid_at",
            "pg_tid",
            "authorization_id",
        ] + valid_extra_fields
        self.save(update_fields=update_fields)

        # Audit log: payment marked as paid
        logger.info(
            "Payment marked as paid",
            extra={
                "payment_id": self.pk,
                "previous_status": previous_status,
                "amount": int(self.amount),
                "pg_tid": pg_tid,
                # Note: authorization_id is intentionally excluded (sensitive PG token)
            },
        )

    def mark_as_failed(self, error_message: str = "") -> None:
        """
        Mark payment as failed.

        Args:
            error_message: Optional error message for logging
        """
        previous_status = self.status
        self.status = PaymentStatus.FAILED
        self.save(update_fields=["status"])

        # Audit log: payment marked as failed
        logger.warning(
            "Payment marked as failed",
            extra={
                "payment_id": self.pk,
                "previous_status": previous_status,
                "amount": int(self.amount),
                "error_message": error_message,
            },
        )

    def mark_as_cancelled(self) -> None:
        """Mark payment as cancelled."""
        previous_status = self.status
        self.status = PaymentStatus.CANCELLED
        self.save(update_fields=["status"])

        # Audit log: payment cancelled
        logger.info(
            "Payment marked as cancelled",
            extra={
                "payment_id": self.pk,
                "previous_status": previous_status,
                "amount": int(self.amount),
                "pg_tid": self.pg_tid,
            },
        )

    def mark_as_refunded(self) -> None:
        """Mark payment as refunded."""
        previous_status = self.status
        self.status = PaymentStatus.REFUNDED
        self.save(update_fields=["status"])

        # Audit log: payment refunded
        logger.info(
            "Payment marked as refunded",
            extra={
                "payment_id": self.pk,
                "previous_status": previous_status,
                "amount": int(self.amount),
                "pg_tid": self.pg_tid,
            },
        )

    def get_receipt_url(self, *, use_test_url: bool = False) -> str | None:
        """
        Get the card receipt URL from EasyPay.

        Args:
            use_test_url: Use test environment URL (default: False)

        Returns:
            Receipt URL if pg_tid exists, None otherwise.
        """
        if self.pg_tid:
            if use_test_url:
                return f"https://testpgweb.easypay.co.kr/receipt/card?pgTid={self.pg_tid}"
            return f"https://pgweb.easypay.co.kr/receipt/card?pgTid={self.pg_tid}"
        return None

    # -------------------------------------------------------------------------
    # Client Info Helpers
    # -------------------------------------------------------------------------

    def set_client_info(self, request: Any) -> None:
        """
        Set client IP and user agent from the request object.

        This is a convenience method to populate client tracking fields
        for fraud detection and audit purposes.

        Usage:
            order = Order(amount=29900, product=product)
            order.set_client_info(request)
            order.save()

        Args:
            request: Django HttpRequest object
        """
        from .utils import get_client_ip, get_user_agent

        self.client_ip = get_client_ip(request)
        self.client_user_agent = get_user_agent(request)

    @classmethod
    def create_with_request(cls, request: Any, **kwargs: Any) -> Self:
        """
        Create a payment instance with client info automatically populated.

        This factory method creates a new payment object and automatically
        sets client_ip and client_user_agent from the request.

        Usage:
            order = Order.create_with_request(
                request,
                amount=29900,
                product=product,
                user=request.user,
            )
            # client_ip and client_user_agent are already set

        Args:
            request: Django HttpRequest object
            **kwargs: Fields to pass to the model constructor

        Returns:
            Created and saved model instance
        """
        from .utils import get_client_ip, get_user_agent

        kwargs.setdefault("client_ip", get_client_ip(request))
        kwargs.setdefault("client_user_agent", get_user_agent(request))
        # Note: This method should only be called on concrete subclasses
        return cls.objects.create(**kwargs)  # type: ignore[attr-defined, no-any-return]
