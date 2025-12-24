"""
Concrete Payment model for testing AbstractPayment.

Since AbstractPayment is abstract, we need a concrete implementation
to test its functionality in the database.
"""

from decimal import Decimal

from django.db import models

from easypay.models import AbstractPayment


class Payment(AbstractPayment):
    """
    Concrete Payment model for testing.

    Inherits all fields from AbstractPayment and adds
    a simple description field for test identification.
    """

    # Optional: additional fields for testing
    description = models.CharField(
        max_length=200,
        blank=True,
        default="",
        help_text="Test payment description",
    )

    # Simulate order_id field (common in real implementations)
    order_id = models.CharField(
        max_length=50,
        unique=True,
        blank=True,
        null=True,
        help_text="External order identifier",
    )

    class Meta:
        app_label = "tests"
        db_table = "tests_payment"
        verbose_name = "Test Payment"
        verbose_name_plural = "Test Payments"
        ordering = ["-created_at"]  # Inherit parent ordering

    @classmethod
    def create_test_payment(
        cls,
        amount: int = 10000,
        status: str = "pending",
        **kwargs,
    ) -> "Payment":
        """
        Factory method for creating test payments.

        Args:
            amount: Payment amount in KRW
            status: Payment status
            **kwargs: Additional fields

        Returns:
            Payment instance (not saved)
        """
        return cls(
            amount=Decimal(amount),
            status=status,
            **kwargs,
        )
