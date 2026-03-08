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

### AbstractPayment 모델 상속

```python
from easypay.models import AbstractPayment, PaymentStatus

class Order(AbstractPayment):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    product = models.ForeignKey(Product, on_delete=models.CASCADE)

    class Meta:
        db_table = "orders_order"
```

AbstractPayment 제공 필드: `hash_id`, `pg_tid`, `authorization_id`, `amount`, `status`, `supply_amount`, `vat_amount`, `tax_free_amount`, `is_taxable`, `pay_method_type_code`, `card_name`, `card_no`, `client_ip`, `client_user_agent`, `created_at`, `paid_at`

### 결제 흐름

```python
from easypay.client import EasyPayClient

client = EasyPayClient()

# 1. 결제 등록 (PG 결제창 URL 반환)
result = client.register_payment(order, return_url="/payment/callback/", device_type_code="PC")

# 2. 콜백에서 결제 승인
client.approve_payment(order, authorization_id=request.GET["authorizationId"])

# 3. 상태 변경 헬퍼
order.mark_as_paid(pg_tid="T123", authorization_id="A456", card_name="삼성카드")
order.mark_as_failed(error_message="카드 한도 초과")
order.mark_as_cancelled()
order.mark_as_refunded()

# 4. 취소/환불
client.cancel_payment(order, cancel_type_code="40")  # 40=전체취소

# 5. 편의 메서드
order.set_client_info(request)       # IP, User-Agent 자동 세팅
order = Order.create_with_request(request, amount=29900, product=product)  # 팩토리
url = order.get_receipt_url()        # 영수증 URL
```

### PaymentStatus

`PENDING` → `COMPLETED` / `FAILED` / `CANCELLED` / `REFUNDED`

Properties: `is_paid`, `is_pending`, `is_cancelled`, `can_cancel`

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

## 결제수단 코드

| 코드 | 결제수단 |
|------|---------|
| `11` | 신용카드 |
| `21` | 계좌이체 |
| `22` | 가상계좌 |
| `31` | 휴대폰 |
| `50` | 간편결제 |

`order.get_pay_method_type_display()` → 한글 표시명 반환

## 주의사항

| 주의 | 설명 |
|------|------|
| 테스트/운영 URL 분리 | 테스트: `testpgapi.easypay.co.kr`, 운영: `pgapi.easypay.co.kr` |
| 취소 API 차이 | 테스트 `/api/ep9/trades/cancel` vs 운영 `/api/trades/revise` (필드명도 다름) |
| HMAC 인증 | **운영 환경만** 필수. `EASYPAY_SECRET_KEY` 누락 시 취소 API 실패 |
| VAT 자동 계산 | `save()` 시 `supply_amount`/`vat_amount` 미설정이면 자동 계산 (10% VAT) |
| hash_id 12자리 | UUID hex[:12] 자동 생성. URL용 외부 식별자 (PK 노출 방지) |
| Retry 보수적 | **transport-layer만** 재시도 (timeout, 502/503/504). 비즈니스 로직 에러는 절대 재시도 안함 (중복 결제 방지) |
| Signal 안전 | signal receiver 에러가 결제 플로우를 중단시키지 않음 (`_send_signal_safe()`) |
