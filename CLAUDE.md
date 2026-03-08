# django-easypay

Django payment integration for EasyPay (KICC) PG.

## 개발

```bash
poe ci         # lint + format + typecheck + test
poe test       # pytest
```

## 프로젝트 구조

```
easypay/
├── client.py          # EasyPayClient (API)
├── models.py          # AbstractPayment, PaymentStatus
├── signals.py         # payment_registered, payment_approved, ...
├── admin.py           # PaymentAdminMixin
├── exceptions.py      # EasyPayError
└── sandbox/           # 테스트용 샌드박스
```

## 사용법

```python
from easypay.client import EasyPayClient
from easypay.models import AbstractPayment

client = EasyPayClient()
client.register_payment(payment, return_url, device_type_code="PC")
client.approve_payment(payment, authorization_id)
client.cancel_payment(payment, cancel_type_code="40")
```

## Django Settings

```python
INSTALLED_APPS = ["easypay"]

# 테스트 (기본)
EASYPAY_MALL_ID = "T0021792"
EASYPAY_API_URL = "https://testpgapi.easypay.co.kr"

# 운영
EASYPAY_MALL_ID = env("EASYPAY_MALL_ID")
EASYPAY_API_URL = "https://pgapi.easypay.co.kr"
EASYPAY_SECRET_KEY = env("EASYPAY_SECRET_KEY")  # HMAC 키 (영업담당자 제공)
```

## ⚠️ 테스트/운영 환경 차이

| 환경 | 취소 API | HMAC 인증 |
|-----|---------|----------|
| 테스트 | `/api/ep9/trades/cancel` | 불필요 |
| 운영 | `/api/trades/revise` | 필수 |

**필드명 차이:**
- 테스트: `pgTid`, `cancelTypeCode`, `cancelAmount`
- 운영: `pgCno`, `reviseTypeCode`, `reviseAmount` + `msgAuthValue`

**HMAC SHA256:**
```python
data = f"{pg_tid}|{shop_transaction_id}"
msg_auth_value = hmac.new(secret_key.encode(), data.encode(), hashlib.sha256).hexdigest()
```

## Reliability & Performance

### Retry with Exponential Backoff

`EasyPayClient._request()` retries up to 3 times with exponential backoff (1s, 2s, 4s) for **transport-layer failures only**:

| Retried (transient) | NOT retried (business logic) |
|---------------------|------------------------------|
| `requests.exceptions.Timeout` | EasyPay `resCd != "0000"` (declined, invalid card, duplicate) |
| `requests.exceptions.ConnectionError` | HTTP 4xx (bad request, auth failure) |
| `OSError` / `ConnectionError` | `requests.exceptions.InvalidURL`, SSL cert errors |
| HTTP 502, 503, 504 (server errors) | Any response with a valid JSON body from EasyPay |

Payment APIs are sensitive — only clear network/infrastructure failures trigger retry. Business logic errors are never retried to avoid duplicate charges.

### Signal Error Isolation

All signal dispatches (`payment_registered`, `payment_approved`, `payment_failed`, `payment_cancelled`) use `_send_signal_safe()` which catches and logs exceptions from signal receivers without propagating them. A failing webhook handler or notification service will not crash the payment flow.
