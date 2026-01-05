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

# 테스트 환경 (기본값)
EASYPAY_MALL_ID = "T0021792"
EASYPAY_API_URL = "https://testpgapi.easypay.co.kr"

# 운영 환경
EASYPAY_MALL_ID = env("EASYPAY_MALL_ID")  # 실 가맹점 ID
EASYPAY_API_URL = "https://pgapi.easypay.co.kr"
EASYPAY_SECRET_KEY = env("EASYPAY_SECRET_KEY")  # HMAC 암복호화 키 (영업담당자 제공)
```

## 환경별 API 동작

| 환경 | 취소 API | 조회 API | HMAC 인증 |
|-----|---------|---------|----------|
| 테스트 (`testpgapi`) | `/api/ep9/trades/cancel` | `/api/ep9/trades/status` | 불필요 |
| 운영 (`pgapi`) | `/api/trades/revise` | `/api/trades/retrieveTransaction` | 필수 |

환경은 `EASYPAY_API_URL`로 자동 감지됨 (`is_test_mode` 프로퍼티).

## Lessons Learned (2026-01-05)

### 1. 테스트 환경과 운영 환경의 API 차이

EasyPay는 테스트/운영 환경에서 **다른 API 엔드포인트와 필드명**을 사용함.

**취소 API:**
- 테스트: `/api/ep9/trades/cancel`
  - `pgTid`, `cancelTypeCode`, `cancelAmount`, `cancelReason`, `cancelReqDate`
- 운영: `/api/trades/revise`
  - `pgCno`, `reviseTypeCode`, `reviseAmount`, `reviseMessage`, `reviseReqDate`, `msgAuthValue`

**중요:** 운영 API는 모든 필드가 `revise` prefix를 사용함 (`cancelReqDate` → `reviseReqDate`).

### 2. HMAC SHA256 인증 (운영 환경 필수)

```python
# msgAuthValue 생성
data = f"{pg_tid}|{shop_transaction_id}"
msg_auth_value = hmac.new(
    secret_key.encode(),
    data.encode(),
    hashlib.sha256
).hexdigest()
```

### 3. 응답 필드명 차이

| 필드 | 테스트 환경 | 운영 환경 |
|-----|------------|----------|
| PG 거래 ID | `pgTid` | `pgCno` |
| 카드명 | `cardName` | `issuerName` |
| 승인 금액 | `paymentInfo.approvalAmount` | `amount` (루트) |

### 4. 영수증 URL

영수증 URL은 `pgCno` (운영 PG 거래번호)를 사용:
- 테스트: `https://testpgweb.easypay.co.kr/receipt/card?pgTid={pgCno}`
- 운영: `https://pgweb.easypay.co.kr/receipt/card?pgTid={pgCno}`

### 5. 프로젝트별 Secret Key

각 프로젝트(가맹점)마다 별도의 `EASYPAY_SECRET_KEY`가 필요함.
영업담당자에게 요청하여 발급받아야 함.

## 테스트

```bash
# 전체 테스트
make test

# 특정 테스트
uv run pytest tests/test_models.py -v

# E2E 테스트 (실제 API 호출)
uv run pytest tests/test_e2e_sandbox.py -v -m e2e
```
