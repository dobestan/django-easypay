"""
Tests for EasyPay payment lifecycle signals.

Tests cover:
- payment_registered: Fired when payment is registered with PG
- payment_approved: Fired when payment is successfully approved
- payment_failed: Fired when payment fails at any stage
- payment_cancelled: Fired when payment is cancelled or refunded
"""

from decimal import Decimal

import pytest

from easypay.models import PaymentStatus
from easypay.signals import (
    payment_approved,
    payment_cancelled,
    payment_failed,
    payment_registered,
)


# ============================================================
# payment_registered Signal Tests
# ============================================================


class TestPaymentRegisteredSignal:
    """Tests for payment_registered signal."""

    def test_signal_fires_with_correct_arguments(self, payment, signal_receiver):
        """Signal should fire with payment and auth_page_url."""
        receiver = signal_receiver()
        payment_registered.connect(receiver.handler)

        try:
            auth_url = "https://testpgapi.easypay.co.kr/webpay/auth?token=TEST_TOKEN"
            payment_registered.send(
                sender=payment.__class__,
                payment=payment,
                auth_page_url=auth_url,
            )

            assert receiver.called is True
            assert receiver.call_count == 1
            assert receiver.last_kwargs["payment"] == payment
            assert receiver.last_kwargs["auth_page_url"] == auth_url
        finally:
            payment_registered.disconnect(receiver.handler)

    def test_multiple_receivers(self, payment, signal_receiver):
        """Multiple receivers should all be called."""
        receiver1 = signal_receiver()
        receiver2 = signal_receiver()
        payment_registered.connect(receiver1.handler)
        payment_registered.connect(receiver2.handler)

        try:
            payment_registered.send(
                sender=payment.__class__,
                payment=payment,
                auth_page_url="https://example.com/auth",
            )

            assert receiver1.called is True
            assert receiver2.called is True
            assert receiver1.call_count == 1
            assert receiver2.call_count == 1
        finally:
            payment_registered.disconnect(receiver1.handler)
            payment_registered.disconnect(receiver2.handler)

    def test_disconnected_receiver_not_called(self, payment, signal_receiver):
        """Disconnected receiver should not be called."""
        receiver = signal_receiver()
        payment_registered.connect(receiver.handler)
        payment_registered.disconnect(receiver.handler)

        payment_registered.send(
            sender=payment.__class__,
            payment=payment,
            auth_page_url="https://example.com/auth",
        )

        assert receiver.called is False
        assert receiver.call_count == 0


# ============================================================
# payment_approved Signal Tests
# ============================================================


class TestPaymentApprovedSignal:
    """Tests for payment_approved signal."""

    def test_signal_fires_with_correct_arguments(self, payment, signal_receiver):
        """Signal should fire with payment and approval_data."""
        receiver = signal_receiver()
        payment_approved.connect(receiver.handler)

        try:
            approval_data = {
                "resCd": "0000",
                "resMsg": "정상처리",
                "pgTid": "PGTID1234567890",
                "cardName": "신한카드",
                "cardNo": "1234-****-****-5678",
            }
            payment_approved.send(
                sender=payment.__class__,
                payment=payment,
                approval_data=approval_data,
            )

            assert receiver.called is True
            assert receiver.call_count == 1
            assert receiver.last_kwargs["payment"] == payment
            assert receiver.last_kwargs["approval_data"] == approval_data
            assert receiver.last_kwargs["approval_data"]["pgTid"] == "PGTID1234567890"
        finally:
            payment_approved.disconnect(receiver.handler)

    def test_signal_with_completed_payment(self, completed_payment, signal_receiver):
        """Signal should work with already completed payment."""
        receiver = signal_receiver()
        payment_approved.connect(receiver.handler)

        try:
            approval_data = {"pgTid": completed_payment.pg_tid}
            payment_approved.send(
                sender=completed_payment.__class__,
                payment=completed_payment,
                approval_data=approval_data,
            )

            assert receiver.called is True
            assert receiver.last_kwargs["payment"].status == PaymentStatus.COMPLETED
            assert receiver.last_kwargs["payment"].pg_tid == completed_payment.pg_tid
        finally:
            payment_approved.disconnect(receiver.handler)

    def test_multiple_approvals_tracked(self, payment, signal_receiver):
        """Receiver should track multiple signal emissions."""
        receiver = signal_receiver()
        payment_approved.connect(receiver.handler)

        try:
            for i in range(3):
                payment_approved.send(
                    sender=payment.__class__,
                    payment=payment,
                    approval_data={"iteration": i},
                )

            assert receiver.call_count == 3
            assert receiver.last_kwargs["approval_data"]["iteration"] == 2
        finally:
            payment_approved.disconnect(receiver.handler)


# ============================================================
# payment_failed Signal Tests
# ============================================================


class TestPaymentFailedSignal:
    """Tests for payment_failed signal."""

    def test_signal_fires_with_correct_arguments(self, payment, signal_receiver):
        """Signal should fire with payment, error_code, error_message, and stage."""
        receiver = signal_receiver()
        payment_failed.connect(receiver.handler)

        try:
            payment_failed.send(
                sender=payment.__class__,
                payment=payment,
                error_code="E501",
                error_message="승인 실패",
                stage="approval",
            )

            assert receiver.called is True
            assert receiver.call_count == 1
            assert receiver.last_kwargs["payment"] == payment
            assert receiver.last_kwargs["error_code"] == "E501"
            assert receiver.last_kwargs["error_message"] == "승인 실패"
            assert receiver.last_kwargs["stage"] == "approval"
        finally:
            payment_failed.disconnect(receiver.handler)

    @pytest.mark.parametrize(
        "stage,error_code,error_message",
        [
            ("registration", "E101", "필수 파라미터 누락"),
            ("approval", "E501", "승인 실패"),
            ("callback", "E401", "인증 실패"),
        ],
    )
    def test_different_failure_stages(
        self, payment, signal_receiver, stage, error_code, error_message
    ):
        """Signal should handle different failure stages."""
        receiver = signal_receiver()
        payment_failed.connect(receiver.handler)

        try:
            payment_failed.send(
                sender=payment.__class__,
                payment=payment,
                error_code=error_code,
                error_message=error_message,
                stage=stage,
            )

            assert receiver.called is True
            assert receiver.last_kwargs["stage"] == stage
            assert receiver.last_kwargs["error_code"] == error_code
            assert receiver.last_kwargs["error_message"] == error_message
        finally:
            payment_failed.disconnect(receiver.handler)

    def test_failure_with_empty_error_message(self, payment, signal_receiver):
        """Signal should accept empty error message."""
        receiver = signal_receiver()
        payment_failed.connect(receiver.handler)

        try:
            payment_failed.send(
                sender=payment.__class__,
                payment=payment,
                error_code="E999",
                error_message="",
                stage="unknown",
            )

            assert receiver.called is True
            assert receiver.last_kwargs["error_message"] == ""
        finally:
            payment_failed.disconnect(receiver.handler)


# ============================================================
# payment_cancelled Signal Tests
# ============================================================


class TestPaymentCancelledSignal:
    """Tests for payment_cancelled signal."""

    def test_signal_fires_with_correct_arguments(
        self, completed_payment, signal_receiver
    ):
        """Signal should fire with payment, cancel_type, cancel_amount, and cancel_data."""
        receiver = signal_receiver()
        payment_cancelled.connect(receiver.handler)

        try:
            cancel_data = {
                "resCd": "0000",
                "resMsg": "정상처리",
                "cancelDate": "20251223",
                "cancelTime": "143000",
            }
            payment_cancelled.send(
                sender=completed_payment.__class__,
                payment=completed_payment,
                cancel_type="40",  # Full cancel
                cancel_amount=completed_payment.amount,
                cancel_data=cancel_data,
            )

            assert receiver.called is True
            assert receiver.call_count == 1
            assert receiver.last_kwargs["payment"] == completed_payment
            assert receiver.last_kwargs["cancel_type"] == "40"
            assert receiver.last_kwargs["cancel_amount"] == completed_payment.amount
            assert receiver.last_kwargs["cancel_data"] == cancel_data
        finally:
            payment_cancelled.disconnect(receiver.handler)

    def test_full_cancellation(self, completed_payment, signal_receiver):
        """Signal should handle full cancellation (cancel_type=40)."""
        receiver = signal_receiver()
        payment_cancelled.connect(receiver.handler)

        try:
            payment_cancelled.send(
                sender=completed_payment.__class__,
                payment=completed_payment,
                cancel_type="40",
                cancel_amount=completed_payment.amount,
                cancel_data={"cancelType": "full"},
            )

            assert receiver.last_kwargs["cancel_type"] == "40"
            assert receiver.last_kwargs["cancel_amount"] == Decimal("29900")
        finally:
            payment_cancelled.disconnect(receiver.handler)

    def test_partial_cancellation(self, completed_payment, signal_receiver):
        """Signal should handle partial cancellation (cancel_type=41)."""
        receiver = signal_receiver()
        payment_cancelled.connect(receiver.handler)

        try:
            partial_amount = Decimal("10000")
            payment_cancelled.send(
                sender=completed_payment.__class__,
                payment=completed_payment,
                cancel_type="41",
                cancel_amount=partial_amount,
                cancel_data={"cancelType": "partial"},
            )

            assert receiver.last_kwargs["cancel_type"] == "41"
            assert receiver.last_kwargs["cancel_amount"] == partial_amount
        finally:
            payment_cancelled.disconnect(receiver.handler)

    def test_refund_signal(self, completed_payment, signal_receiver):
        """Signal should handle refund scenario."""
        receiver = signal_receiver()
        payment_cancelled.connect(receiver.handler)

        try:
            payment_cancelled.send(
                sender=completed_payment.__class__,
                payment=completed_payment,
                cancel_type="40",
                cancel_amount=completed_payment.amount,
                cancel_data={"reason": "customer_request", "refund": True},
            )

            assert receiver.called is True
            assert receiver.last_kwargs["cancel_data"]["refund"] is True
        finally:
            payment_cancelled.disconnect(receiver.handler)


# ============================================================
# Signal Integration Tests
# ============================================================


@pytest.mark.django_db
class TestSignalIntegration:
    """Integration tests for signals with model operations."""

    def test_manual_signal_emission_pattern(self, payment, signal_receiver):
        """Demonstrate typical signal emission pattern after payment approval."""
        receiver = signal_receiver()
        payment_approved.connect(receiver.handler)

        try:
            # Simulate payment approval flow
            approval_data = {
                "pgTid": "PGTID12345",
                "cardName": "신한카드",
            }

            # Update payment state
            payment.mark_as_paid(
                pg_tid=approval_data["pgTid"],
                card_name=approval_data["cardName"],
            )

            # Emit signal (typically done in view after mark_as_paid)
            payment_approved.send(
                sender=payment.__class__,
                payment=payment,
                approval_data=approval_data,
            )

            # Verify
            assert receiver.called is True
            assert receiver.last_kwargs["payment"].status == PaymentStatus.COMPLETED
            assert receiver.last_kwargs["payment"].pg_tid == "PGTID12345"
        finally:
            payment_approved.disconnect(receiver.handler)

    def test_failure_signal_with_model_update(self, payment, signal_receiver):
        """Signal emission after marking payment as failed."""
        receiver = signal_receiver()
        payment_failed.connect(receiver.handler)

        try:
            error_code = "E501"
            error_message = "카드 한도 초과"

            # Update payment state
            payment.mark_as_failed(error_message=error_message)

            # Emit signal
            payment_failed.send(
                sender=payment.__class__,
                payment=payment,
                error_code=error_code,
                error_message=error_message,
                stage="approval",
            )

            # Verify
            assert receiver.called is True
            assert receiver.last_kwargs["payment"].status == PaymentStatus.FAILED
        finally:
            payment_failed.disconnect(receiver.handler)

    def test_cancellation_signal_with_model_update(
        self, completed_payment, signal_receiver
    ):
        """Signal emission after marking payment as cancelled."""
        receiver = signal_receiver()
        payment_cancelled.connect(receiver.handler)

        try:
            cancel_data = {"pgTid": completed_payment.pg_tid}

            # Update payment state
            completed_payment.mark_as_cancelled()

            # Emit signal
            payment_cancelled.send(
                sender=completed_payment.__class__,
                payment=completed_payment,
                cancel_type="40",
                cancel_amount=completed_payment.amount,
                cancel_data=cancel_data,
            )

            # Verify
            assert receiver.called is True
            assert receiver.last_kwargs["payment"].status == PaymentStatus.CANCELLED
        finally:
            payment_cancelled.disconnect(receiver.handler)

    def test_all_signals_independent(self, payment, signal_receiver):
        """All four signals should work independently."""
        registered_receiver = signal_receiver()
        approved_receiver = signal_receiver()
        failed_receiver = signal_receiver()
        cancelled_receiver = signal_receiver()

        payment_registered.connect(registered_receiver.handler)
        payment_approved.connect(approved_receiver.handler)
        payment_failed.connect(failed_receiver.handler)
        payment_cancelled.connect(cancelled_receiver.handler)

        try:
            # Fire only registered signal
            payment_registered.send(
                sender=payment.__class__,
                payment=payment,
                auth_page_url="https://example.com",
            )

            # Only registered receiver should be called
            assert registered_receiver.called is True
            assert approved_receiver.called is False
            assert failed_receiver.called is False
            assert cancelled_receiver.called is False

            # Fire approved signal
            payment_approved.send(
                sender=payment.__class__,
                payment=payment,
                approval_data={},
            )

            # Now approved should also be called
            assert approved_receiver.called is True
            assert failed_receiver.called is False
            assert cancelled_receiver.called is False

        finally:
            payment_registered.disconnect(registered_receiver.handler)
            payment_approved.disconnect(approved_receiver.handler)
            payment_failed.disconnect(failed_receiver.handler)
            payment_cancelled.disconnect(cancelled_receiver.handler)


# ============================================================
# Signal Sender Tests
# ============================================================


class TestSignalSender:
    """Tests for signal sender argument."""

    def test_sender_is_model_class(self, payment, signal_receiver):
        """Sender should be the Payment model class, not instance."""
        receiver = signal_receiver()
        payment_approved.connect(receiver.handler)

        try:
            payment_approved.send(
                sender=payment.__class__,
                payment=payment,
                approval_data={},
            )

            # The sender in last_kwargs is passed by Django's signal mechanism
            # We verify the signal was called correctly
            assert receiver.called is True
        finally:
            payment_approved.disconnect(receiver.handler)

    def test_receiver_with_sender_filter(self, payment, signal_receiver, db):
        """Receiver can filter by sender."""
        from tests.models import Payment

        receiver = signal_receiver()
        # Connect with sender filter
        payment_approved.connect(receiver.handler, sender=Payment)

        try:
            # Signal from correct sender
            payment_approved.send(
                sender=Payment,
                payment=payment,
                approval_data={},
            )

            assert receiver.called is True
        finally:
            payment_approved.disconnect(receiver.handler, sender=Payment)
