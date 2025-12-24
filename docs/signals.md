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

## Best Practices

1. **Keep handlers fast**: Offload heavy work to Celery tasks
2. **Handle exceptions**: Don't let notification failures break the payment flow
3. **Use multiple receivers**: Separate concerns (notifications, logging, tasks)
4. **Test your handlers**: Mock signals in unit tests

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
