"""
Django signals for EasyPay payment lifecycle events.

Usage:
    from django.dispatch import receiver
    from easypay.signals import payment_approved, payment_failed

    @receiver(payment_approved)
    def send_notification(sender, payment, **kwargs):
        # Send Telegram, SMS, or Slack notification
        pass

    @receiver(payment_failed)
    def log_failure(sender, payment, error_code, error_message, **kwargs):
        # Log to Sentry or custom logging
        sentry_sdk.capture_message(f"Payment failed: {error_code}")

Signals:
    payment_registered: Fired when payment registration succeeds (authPageUrl received)
    payment_approved: Fired when payment is successfully approved by PG
    payment_failed: Fired when payment fails at any stage
    payment_cancelled: Fired when payment is cancelled or refunded
"""

from django.dispatch import Signal

# Fired when payment is registered with PG and authPageUrl is received.
# This is the first step where user is about to be redirected to payment page.
#
# Arguments:
#   sender: Payment model class
#   payment: Payment instance
#   auth_page_url: URL to redirect user to EasyPay payment page
payment_registered = Signal()

# Fired when payment is successfully approved.
# This is the final step after user completes authentication.
#
# Arguments:
#   sender: Payment model class
#   payment: Payment instance
#   approval_data: Dict containing PG response (pg_tid, card_name, etc.)
payment_approved = Signal()

# Fired when payment fails at any stage.
# Can be during registration, authentication, or approval.
#
# Arguments:
#   sender: Payment model class
#   payment: Payment instance
#   error_code: EasyPay error code (e.g., "E501")
#   error_message: Human-readable error message
#   stage: Where the failure occurred ("registration", "approval", "callback")
payment_failed = Signal()

# Fired when payment is cancelled or refunded.
#
# Arguments:
#   sender: Payment model class
#   payment: Payment instance
#   cancel_type: "40" for full cancel, "41" for partial cancel
#   cancel_amount: Amount cancelled (for partial cancellation)
#   cancel_data: Dict containing PG cancellation response
payment_cancelled = Signal()
