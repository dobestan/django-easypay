"""
Tests for AbstractPayment model and PaymentStatus enum.

Tests cover:
- PaymentStatus enum values and choices
- AbstractPayment field defaults and constraints
- Payment state properties (is_paid, is_pending, is_cancelled, can_cancel)
- Payment state transition methods (mark_as_paid, mark_as_failed, etc.)
- String representation and receipt URL generation
"""

from decimal import Decimal

import pytest
from django.utils import timezone
from freezegun import freeze_time

from easypay.models import PaymentStatus


# ============================================================
# PaymentStatus Tests
# ============================================================


class TestPaymentStatus:
    """Tests for PaymentStatus TextChoices enum."""

    def test_status_values(self):
        """Verify all expected status values exist."""
        assert PaymentStatus.PENDING == "pending"
        assert PaymentStatus.COMPLETED == "completed"
        assert PaymentStatus.FAILED == "failed"
        assert PaymentStatus.CANCELLED == "cancelled"
        assert PaymentStatus.REFUNDED == "refunded"

    def test_status_labels(self):
        """Verify Korean labels for each status."""
        assert PaymentStatus.PENDING.label == "결제대기"
        assert PaymentStatus.COMPLETED.label == "결제완료"
        assert PaymentStatus.FAILED.label == "결제실패"
        assert PaymentStatus.CANCELLED.label == "취소"
        assert PaymentStatus.REFUNDED.label == "환불"

    def test_status_choices(self):
        """Verify choices format for Django model field."""
        choices = PaymentStatus.choices
        assert len(choices) == 5
        assert ("pending", "결제대기") in choices
        assert ("completed", "결제완료") in choices


# ============================================================
# AbstractPayment Field Tests
# ============================================================


@pytest.mark.django_db
class TestAbstractPaymentFields:
    """Tests for AbstractPayment field defaults and constraints."""

    def test_create_payment_with_minimum_fields(self, db):
        """Payment can be created with only required fields."""
        from tests.models import Payment

        payment = Payment.objects.create(amount=Decimal("10000"))

        assert payment.pk is not None
        assert payment.amount == Decimal("10000")
        assert payment.status == PaymentStatus.PENDING
        assert payment.pg_tid == ""
        assert payment.authorization_id == ""
        assert payment.card_name == ""
        assert payment.card_no == ""
        assert payment.client_ip is None
        assert payment.created_at is not None
        assert payment.paid_at is None

    def test_all_fields_populated(self, db):
        """Payment can store all PG-related data."""
        from tests.models import Payment

        payment = Payment.objects.create(
            amount=Decimal("29900"),
            status=PaymentStatus.COMPLETED,
            pg_tid="PGTID1234567890",
            authorization_id="AUTH1234567890",
            pay_method_type_code="11",
            card_name="신한카드",
            card_no="1234-****-****-5678",
            client_ip="192.168.1.100",
            client_user_agent="Mozilla/5.0 Test Browser",
            paid_at=timezone.now(),
        )

        payment.refresh_from_db()
        assert payment.pg_tid == "PGTID1234567890"
        assert payment.authorization_id == "AUTH1234567890"
        assert payment.pay_method_type_code == "11"
        assert payment.card_name == "신한카드"
        assert payment.card_no == "1234-****-****-5678"
        assert payment.client_ip == "192.168.1.100"
        assert str(payment.client_user_agent) == "Mozilla/5.0 Test Browser"

    def test_amount_precision(self, db):
        """Amount field handles Korean Won correctly (no decimals)."""
        from tests.models import Payment

        payment = Payment.objects.create(amount=Decimal("9999999"))
        payment.refresh_from_db()

        assert payment.amount == Decimal("9999999")

    def test_ordering_by_created_at_descending(self, db):
        """Payments are ordered by created_at descending (newest first)."""
        from tests.models import Payment

        p1 = Payment.objects.create(amount=Decimal("1000"))
        p2 = Payment.objects.create(amount=Decimal("2000"))
        p3 = Payment.objects.create(amount=Decimal("3000"))

        payments = list(Payment.objects.all())
        assert payments == [p3, p2, p1]


# ============================================================
# Payment State Property Tests
# ============================================================


@pytest.mark.django_db
class TestPaymentStateProperties:
    """Tests for is_paid, is_pending, is_cancelled, can_cancel properties."""

    def test_is_paid_true_when_completed(self, completed_payment):
        """is_paid returns True only for COMPLETED status."""
        assert completed_payment.is_paid is True
        assert completed_payment.status == PaymentStatus.COMPLETED

    def test_is_paid_false_for_other_statuses(self, payment):
        """is_paid returns False for non-COMPLETED statuses."""
        assert payment.is_paid is False  # PENDING

        payment.status = PaymentStatus.FAILED
        assert payment.is_paid is False

        payment.status = PaymentStatus.CANCELLED
        assert payment.is_paid is False

    def test_is_pending_true_when_pending(self, payment):
        """is_pending returns True only for PENDING status."""
        assert payment.is_pending is True

    def test_is_pending_false_for_other_statuses(self, completed_payment):
        """is_pending returns False for non-PENDING statuses."""
        assert completed_payment.is_pending is False

    def test_is_cancelled_true_for_cancelled_and_refunded(self, db):
        """is_cancelled returns True for both CANCELLED and REFUNDED."""
        from tests.models import Payment

        cancelled = Payment.objects.create(
            amount=Decimal("10000"), status=PaymentStatus.CANCELLED
        )
        refunded = Payment.objects.create(
            amount=Decimal("10000"), status=PaymentStatus.REFUNDED
        )

        assert cancelled.is_cancelled is True
        assert refunded.is_cancelled is True

    def test_is_cancelled_false_for_other_statuses(self, payment, completed_payment):
        """is_cancelled returns False for PENDING/COMPLETED/FAILED."""
        assert payment.is_cancelled is False
        assert completed_payment.is_cancelled is False

        payment.status = PaymentStatus.FAILED
        assert payment.is_cancelled is False

    def test_can_cancel_requires_completed_and_pg_tid(self, completed_payment):
        """can_cancel returns True only if COMPLETED with pg_tid."""
        assert completed_payment.can_cancel is True
        assert completed_payment.status == PaymentStatus.COMPLETED
        assert completed_payment.pg_tid != ""

    def test_can_cancel_false_without_pg_tid(self, db):
        """can_cancel returns False if COMPLETED but no pg_tid."""
        from tests.models import Payment

        payment = Payment.objects.create(
            amount=Decimal("10000"),
            status=PaymentStatus.COMPLETED,
            pg_tid="",  # No PG TID
        )

        assert payment.can_cancel is False

    def test_can_cancel_false_for_pending(self, payment):
        """can_cancel returns False for PENDING payments."""
        assert payment.can_cancel is False


# ============================================================
# Payment State Transition Method Tests
# ============================================================


@pytest.mark.django_db
class TestPaymentStateTransitions:
    """Tests for mark_as_paid, mark_as_failed, mark_as_cancelled, mark_as_refunded."""

    @freeze_time("2025-12-23 14:30:00")
    def test_mark_as_paid_basic(self, payment):
        """mark_as_paid updates status and paid_at timestamp."""
        payment.mark_as_paid()

        payment.refresh_from_db()
        assert payment.status == PaymentStatus.COMPLETED
        assert payment.paid_at is not None
        assert payment.is_paid is True

    @freeze_time("2025-12-23 14:30:00")
    def test_mark_as_paid_with_pg_data(self, payment):
        """mark_as_paid stores PG transaction data."""
        payment.mark_as_paid(
            pg_tid="PGTID12345",
            authorization_id="AUTH12345",
            card_name="신한카드",
            card_no="1234-****-****-5678",
            pay_method_type_code="11",
        )

        payment.refresh_from_db()
        assert payment.status == PaymentStatus.COMPLETED
        assert payment.pg_tid == "PGTID12345"
        assert payment.authorization_id == "AUTH12345"
        assert payment.card_name == "신한카드"
        assert payment.card_no == "1234-****-****-5678"
        assert payment.pay_method_type_code == "11"

    def test_mark_as_paid_ignores_invalid_fields(self, payment):
        """mark_as_paid ignores fields that don't exist on the model."""
        payment.mark_as_paid(
            pg_tid="PGTID12345",
            nonexistent_field="should be ignored",
        )

        payment.refresh_from_db()
        assert payment.pg_tid == "PGTID12345"
        assert not hasattr(payment, "nonexistent_field")

    def test_mark_as_failed(self, payment):
        """mark_as_failed sets status to FAILED."""
        payment.mark_as_failed(error_message="Test error")

        payment.refresh_from_db()
        assert payment.status == PaymentStatus.FAILED
        assert payment.is_paid is False

    def test_mark_as_cancelled(self, completed_payment):
        """mark_as_cancelled sets status to CANCELLED."""
        completed_payment.mark_as_cancelled()

        completed_payment.refresh_from_db()
        assert completed_payment.status == PaymentStatus.CANCELLED
        assert completed_payment.is_cancelled is True

    def test_mark_as_refunded(self, completed_payment):
        """mark_as_refunded sets status to REFUNDED."""
        completed_payment.mark_as_refunded()

        completed_payment.refresh_from_db()
        assert completed_payment.status == PaymentStatus.REFUNDED
        assert completed_payment.is_cancelled is True


# ============================================================
# String Representation Tests
# ============================================================


@pytest.mark.django_db
class TestPaymentStringRepresentation:
    """Tests for __str__ method."""

    def test_str_pending_payment(self, payment):
        """String representation shows status and amount."""
        result = str(payment)
        assert "결제대기" in result
        assert "29,900원" in result

    def test_str_completed_payment(self, completed_payment):
        """String representation shows completed status."""
        result = str(completed_payment)
        assert "결제완료" in result
        assert "29,900원" in result

    def test_str_large_amount(self, db):
        """String representation handles large amounts with commas."""
        from tests.models import Payment

        payment = Payment.objects.create(amount=Decimal("1234567"))
        result = str(payment)
        assert "1,234,567원" in result


# ============================================================
# Receipt URL Tests
# ============================================================


@pytest.mark.django_db
class TestReceiptUrl:
    """Tests for get_receipt_url method."""

    def test_get_receipt_url_with_pg_tid(self, completed_payment):
        """Receipt URL is generated when pg_tid exists."""
        url = completed_payment.get_receipt_url()

        assert url is not None
        assert "pgweb.easypay.co.kr/receipt/card" in url
        assert completed_payment.pg_tid in url

    def test_get_receipt_url_without_pg_tid(self, payment):
        """Receipt URL is None when pg_tid is empty."""
        assert payment.pg_tid == ""
        assert payment.get_receipt_url() is None


# ============================================================
# Concrete Test Model Tests
# ============================================================


@pytest.mark.django_db
class TestConcretePaymentModel:
    """Tests for the concrete Payment test model."""

    def test_create_test_payment_factory(self, db):
        """create_test_payment factory method works correctly."""
        from tests.models import Payment

        payment = Payment.create_test_payment(
            amount=50000,
            status="completed",
            description="Factory test",
        )

        assert payment.amount == Decimal("50000")
        assert payment.status == "completed"
        assert payment.description == "Factory test"
        assert payment.pk is None  # Not saved yet

        payment.save()
        assert payment.pk is not None

    def test_order_id_unique_constraint(self, db):
        """order_id field enforces uniqueness."""
        from django.db import IntegrityError

        from tests.models import Payment

        Payment.objects.create(
            amount=Decimal("10000"),
            order_id="ORDER-001",
        )

        with pytest.raises(IntegrityError):
            Payment.objects.create(
                amount=Decimal("20000"),
                order_id="ORDER-001",  # Duplicate
            )

    def test_description_field(self, db):
        """Description field stores test-specific information."""
        from tests.models import Payment

        payment = Payment.objects.create(
            amount=Decimal("10000"),
            description="Integration test payment",
        )

        payment.refresh_from_db()
        assert payment.description == "Integration test payment"
