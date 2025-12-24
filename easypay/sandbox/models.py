"""
Sandbox Payment model for testing EasyPay integration.

This is a concrete implementation of AbstractPayment for sandbox testing.
It's used by the sandbox views to create and track test payments.
"""

import uuid
from decimal import Decimal

from django.db import models

from easypay.models import AbstractPayment


class SandboxPayment(AbstractPayment):
    """
    Concrete Payment model for sandbox testing.

    Inherits all fields from AbstractPayment and adds:
    - goods_name: Product name for display
    - order_id: Unique order identifier (auto-generated UUID)
    """

    goods_name = models.CharField(
        "상품명",
        max_length=100,
        default="테스트 상품",
        help_text="Product name for EasyPay display",
    )

    order_id = models.CharField(
        "주문번호",
        max_length=50,
        unique=True,
        blank=True,
        help_text="Unique order identifier (auto-generated)",
    )

    class Meta:
        app_label = "easypay_sandbox"
        db_table = "easypay_sandbox_payment"
        verbose_name = "Sandbox Payment"
        verbose_name_plural = "Sandbox Payments"

    def __str__(self):
        return f"Sandbox #{self.order_id} - {self.amount:,.0f}원 ({self.get_status_display()})"

    def save(self, *args, **kwargs):
        """Auto-generate order_id if not provided."""
        if not self.order_id:
            self.order_id = f"SB{uuid.uuid4().hex[:12].upper()}"
        super().save(*args, **kwargs)

    @classmethod
    def create_test_payment(
        cls,
        amount: int = 1000,
        goods_name: str = "테스트 상품",
        **kwargs,
    ) -> "SandboxPayment":
        """
        Factory method for creating sandbox payments.

        Args:
            amount: Payment amount in KRW (default: 1000)
            goods_name: Product name (default: "테스트 상품")
            **kwargs: Additional fields

        Returns:
            SandboxPayment instance (not saved)
        """
        return cls(
            amount=Decimal(amount),
            goods_name=goods_name,
            **kwargs,
        )
