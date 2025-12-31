# django-easypay

Django payment integration for EasyPay (KICC) PG.

## 개발 명령어

```bash
make install    # uv sync --group dev
make lint       # ruff check
make format     # ruff format
make typecheck  # mypy easypay/
make test       # pytest tests/
make ci         # 전체 CI (lint, format, typecheck, test)
make hooks      # Git hooks 설치
```

## 프로젝트 구조

```
django-easypay/
├── easypay/
│   ├── __init__.py
│   ├── admin.py           # PaymentAdminMixin
│   ├── apps.py
│   ├── client.py          # EasyPayClient (API 클라이언트)
│   ├── exceptions.py      # EasyPayError
│   ├── models.py          # AbstractPayment, PaymentStatus
│   ├── signals.py         # payment_registered, payment_approved, ...
│   ├── utils.py           # get_client_ip, get_device_type_code, mask_card_number
│   └── sandbox/           # 테스트용 샌드박스 모듈
│       ├── admin.py
│       ├── models.py
│       ├── urls.py
│       └── views.py
├── tests/
│   ├── conftest.py        # pytest fixtures
│   ├── test_admin.py
│   ├── test_client.py
│   ├── test_models.py
│   ├── test_signals.py
│   └── ...
└── docs/
    ├── installation.md
    ├── models.md
    ├── signals.md
    ├── admin.md
    └── security.md
```

## 주요 모듈

### EasyPayClient (client.py)
```python
from easypay.client import EasyPayClient

client = EasyPayClient()
result = client.register_payment(payment, return_url, device_type_code="PC")
result = client.approve_payment(payment, authorization_id)
result = client.cancel_payment(payment, cancel_type_code="40")
result = client.get_transaction_status(payment)
```

### AbstractPayment (models.py)
```python
from easypay.models import AbstractPayment, PaymentStatus

class Payment(AbstractPayment):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    
    class Meta:
        db_table = "payments_payment"
```

### Signals (signals.py)
- `payment_registered` - 결제 등록 완료
- `payment_approved` - 결제 승인 완료
- `payment_failed` - 결제 실패
- `payment_cancelled` - 결제 취소

## Django Settings

```python
INSTALLED_APPS = ["easypay"]

# EasyPay 설정 (기본값: 테스트 MID)
EASYPAY_MALL_ID = "T0021792"
EASYPAY_API_URL = "https://testpgapi.easypay.co.kr"
```

## 테스트

```bash
# 전체 테스트
make test

# 특정 테스트
uv run pytest tests/test_models.py -v

# E2E 테스트 (실제 API 호출)
uv run pytest tests/test_e2e_sandbox.py -v -m e2e
```
