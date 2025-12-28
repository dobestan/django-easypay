# Signals

django-easypay provides Django signals to hook into payment lifecycle events.

## Available Signals

| Signal | Sent When |
|--------|-----------|
| `payment_registered` | Payment registered with EasyPay (authPageUrl received) |
| `payment_approved` | Payment successfully approved |
| `payment_failed` | Payment failed |
| `payment_cancelled` | Payment cancelled or refunded |

## Signal Arguments

All signals send:
- `sender`: The Payment model class
- `payment`: The payment instance

Additional arguments:

### payment_approved
- `pg_tid`: EasyPay transaction ID
- `auth_id`: Authorization ID

### payment_failed
- `error_code`: Error code from EasyPay
- `error_message`: Error message

### payment_cancelled
- `cancel_type`: '40' (full) or '41' (partial)
- `cancel_amount`: Amount cancelled

## Usage Examples

### Connect Signals in AppConfig

```python
# apps/payments/apps.py
from django.apps import AppConfig

class PaymentsConfig(AppConfig):
    name = 'apps.payments'

    def ready(self):
        from . import signals  # noqa
```

### Send Notifications

```python
# apps/payments/signals.py
from django.dispatch import receiver
from easypay.signals import payment_approved, payment_failed

@receiver(payment_approved)
def send_success_notification(sender, payment, **kwargs):
    """Send Telegram notification on payment success."""
    from myapp.telegram import send_message

    send_message(
        chat_id=ADMIN_CHAT_ID,
        text=f"💰 결제 완료!\n"
             f"금액: {payment.amount:,}원\n"
             f"상품: {payment.product.name}"
    )

@receiver(payment_approved)
def send_sms_to_user(sender, payment, **kwargs):
    """Send SMS confirmation to user."""
    from myapp.sms import send_sms

    send_sms(
        to=payment.user.phone,
        text=f"[MyApp] 결제가 완료되었습니다. 금액: {payment.amount:,}원"
    )
```

### Log Failures

```python
@receiver(payment_failed)
def log_payment_failure(sender, payment, error_code, error_message, **kwargs):
    """Log payment failures to Sentry."""
    import sentry_sdk

    sentry_sdk.capture_message(
        f"Payment failed: {error_code}",
        level="warning",
        extra={
            'payment_id': payment.pk,
            'error_code': error_code,
            'error_message': error_message,
            'amount': str(payment.amount),
        }
    )
```

### Trigger Post-Payment Tasks

```python
@receiver(payment_approved)
def generate_report(sender, payment, **kwargs):
    """Start report generation after payment."""
    from myapp.tasks import generate_report_task

    generate_report_task.delay(payment.pk)
```

### Slack Integration

```python
@receiver(payment_approved)
def notify_slack(sender, payment, **kwargs):
    """Post to Slack channel on payment."""
    import requests

    requests.post(
        SLACK_WEBHOOK_URL,
        json={
            "text": f"💰 New payment: {payment.amount:,}원",
            "attachments": [
                {
                    "color": "good",
                    "fields": [
                        {"title": "User", "value": payment.user.email, "short": True},
                        {"title": "Product", "value": payment.product.name, "short": True},
                    ]
                }
            ]
        }
    )
```

## Django 6.0+ Background Tasks Integration

Django 6.0 introduces a built-in Tasks framework for running code outside the HTTP request-response cycle.
This is ideal for payment-related background processing.

> **Note**: Django's Background Tasks provides task definition, validation, and queuing.
> Production execution requires an external worker (Celery, RQ, etc.).

### Define Payment Tasks

```python
# apps/payments/tasks.py
from django.tasks import task

@task(priority=10, queue_name="payments")
def send_payment_notification(payment_id: int, notification_type: str) -> dict:
    """Send async payment notification (email, SMS, webhook)."""
    from apps.payments.models import Payment
    
    payment = Payment.objects.get(id=payment_id)
    
    if notification_type == "telegram":
        send_telegram_notification(payment)
    elif notification_type == "sms":
        send_sms_notification(payment)
    elif notification_type == "webhook":
        send_webhook_notification(payment)
    
    return {"status": "sent", "payment_id": payment_id}


@task(priority=5, queue_name="reports")
def generate_payment_report(payment_id: int) -> dict:
    """Generate report after payment (lower priority)."""
    from apps.payments.models import Payment
    
    payment = Payment.objects.get(id=payment_id)
    report = generate_report_for_payment(payment)
    
    return {"report_id": report.id, "payment_id": payment_id}
```

### Enqueue Tasks from Signal Handlers

```python
# apps/payments/signals.py
from functools import partial

from django.db import transaction
from django.dispatch import receiver

from easypay.signals import payment_approved


@receiver(payment_approved)
def queue_notifications(sender, payment, **kwargs):
    """Queue async notifications after payment approval."""
    from apps.payments.tasks import send_payment_notification
    
    # Use transaction.on_commit to ensure task is queued
    # only after the payment transaction is committed
    transaction.on_commit(
        partial(
            send_payment_notification.enqueue,
            payment_id=payment.id,
            notification_type="telegram",
        )
    )


@receiver(payment_approved)  
def queue_report_generation(sender, payment, **kwargs):
    """Queue report generation (lower priority)."""
    from apps.payments.tasks import generate_payment_report
    
    transaction.on_commit(
        partial(
            generate_payment_report.enqueue,
            payment_id=payment.id,
        )
    )
```

### Configure Tasks Backend

```python
# settings.py

# Development: Tasks execute immediately (for testing)
TASKS = {
    "default": {
        "BACKEND": "django.tasks.backends.immediate.ImmediateBackend"
    }
}

# Production: Use a proper task backend
# TASKS = {
#     "default": {
#         "BACKEND": "path.to.your.backend.CeleryBackend"
#     }
# }
```

### Deferred Tasks (Scheduled Execution)

```python
from datetime import timedelta
from django.utils import timezone

@receiver(payment_approved)
def schedule_followup(sender, payment, **kwargs):
    """Schedule a follow-up task for 24 hours later."""
    from apps.payments.tasks import send_followup_survey
    
    transaction.on_commit(
        partial(
            send_followup_survey.enqueue,
            payment_id=payment.id,
            run_after=timezone.now() + timedelta(hours=24),
        )
    )
```

## Best Practices

1. **Keep handlers fast**: Offload heavy work to background tasks (Celery or Django 6.0+ Tasks)
2. **Handle exceptions**: Don't let notification failures break the payment flow
3. **Use multiple receivers**: Separate concerns (notifications, logging, tasks)
4. **Test your handlers**: Mock signals in unit tests
5. **Use transaction.on_commit**: Ensure tasks are queued after DB commit

```python
# Example: Safe handler with error handling
@receiver(payment_approved)
def safe_notification(sender, payment, **kwargs):
    try:
        send_notification(payment)
    except Exception as e:
        logger.error(f"Notification failed: {e}", exc_info=True)
        # Don't re-raise - payment already succeeded
```
