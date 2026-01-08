# Django EasyPay 보안 가이드

이 문서는 django-easypay 패키지를 사용할 때 지켜야 할 보안 지침을 설명합니다.

---

## 1. 로깅 가이드라인

### 1.1 로깅 가능한 데이터 (안전)

| 필드 | 설명 | 예시 |
|------|------|------|
| `order_id` | 주문 식별자 | `"ORD-20251224-001"` |
| `payment_id` | 결제 DB ID | `123` |
| `pg_tid` | PG 거래번호 | `"EP12345678901234"` |
| `amount` | 결제 금액 | `50000` |
| `card_name` | 카드사명 | `"삼성카드"` |
| `status` | 결제 상태 | `"completed"` |
| `pay_method` | 결제수단 코드 | `"11"` (신용카드) |
| `client_ip` | 클라이언트 IP | `"203.0.113.1"` |
| `error_code` | PG 에러 코드 | `"E501"` |
| `error_message` | PG 에러 메시지 | `"승인 실패"` |
| `device_type` | 디바이스 유형 | `"PC"` / `"MOBILE"` |

### 1.2 로깅 금지 데이터 (민감)

| 필드 | 이유 | 대안 |
|------|------|------|
| `auth_id` | 세션별 인증 토큰, 재사용 공격 가능 | 로깅하지 않음 |
| `card_no` (전체) | PCI-DSS 위반 | `mask_card_number()` 사용 |
| 전체 API 응답 | 민감 정보 포함 가능 | 필요한 필드만 추출하여 로깅 |
| `shopSecretKey` | API 인증 키 | 절대 로깅 금지 |
| CVV, 유효기간 | 카드 보안 정보 | 저장/로깅 금지 |

### 1.3 로깅 레벨 가이드

```python
import logging
logger = logging.getLogger(__name__)

# DEBUG: 개발/디버깅용 상세 정보 (프로덕션에서 비활성화)
logger.debug("Querying transaction status", extra={"pg_tid": pg_tid})

# INFO: 정상 비즈니스 이벤트
logger.info("Payment approved", extra={"payment_id": pk, "amount": amount})

# WARNING: 주의가 필요한 상황, 결제 취소 등 중요 작업
logger.warning("Payment cancellation initiated", extra={"payment_id": pk})

# ERROR: 처리가 필요한 오류
logger.error("Payment approval failed", extra={"error_code": code})

# CRITICAL: 시스템 장애
logger.critical("EasyPay API unreachable")
```

---

## 2. 카드번호 마스킹

### 2.1 기본 사용법

```python
from easypay.utils import mask_card_number

# 기본 마스킹 (앞 4자리, 뒤 4자리 표시)
mask_card_number("1234567890123456")  # "1234-****-****-3456"
mask_card_number("1234-5678-9012-3456")  # "1234-****-****-3456"

# 이미 마스킹된 데이터는 그대로 반환
mask_card_number("1234-****-****-3456")  # "1234-****-****-3456"
```

### 2.2 마스킹 적용 위치

| 위치 | 마스킹 필수 | 비고 |
|------|------------|------|
| DB 저장 | ✅ | EasyPay가 이미 마스킹하여 전달 |
| Admin 표시 | ✅ | `PaymentAdminMixin` 자동 처리 |
| CSV 내보내기 | ✅ | `export_to_csv` 자동 처리 |
| 로그 출력 | ✅ | 로깅 전 `mask_card_number()` 호출 |
| API 응답 | ✅ | 직접 마스킹 처리 필요 |

---

## 3. Admin 보안

### 3.1 감사 로깅

모든 Admin 액션은 자동으로 감사 로그가 기록됩니다:

```python
# 기록되는 정보
{
    "admin_user": "admin@example.com",
    "admin_user_id": 1,
    "action": "cancel_selected_payments",
    "selected_count": 5,
    "payment_ids": [1, 2, 3, 4, 5],
}
```

### 3.2 CSV 내보내기 보안

CSV 내보내기 시 자동으로 적용되는 보안 조치:
- 카드번호 마스킹 적용
- `auth_id` 필드 제외 (민감 정보)
- 내보내기 작업 감사 로그 기록

### 3.3 권한 설정 권장사항

```python
# 프로젝트 admin.py에서 권한 제한 예시
@admin.register(Payment)
class PaymentAdmin(PaymentAdminMixin, admin.ModelAdmin):

    def has_delete_permission(self, request, obj=None):
        # 결제 데이터 삭제 금지
        return False

    def has_change_permission(self, request, obj=None):
        # 결제 완료 건은 수정 금지
        if obj and obj.is_paid:
            return False
        return super().has_change_permission(request, obj)
```

---

## 4. Signal Receiver 작성 가이드

### 4.1 안전한 Signal Receiver 예시

```python
from django.dispatch import receiver
from easypay.signals import payment_approved, payment_failed

@receiver(payment_approved)
def send_notification(sender, payment, **kwargs):
    """결제 성공 알림 전송"""
    # ✅ 안전: 민감하지 않은 정보만 사용
    send_telegram(
        f"결제 완료: {payment.amount:,}원 (주문 #{payment.order_id})"
    )

@receiver(payment_failed)
def log_failure(sender, payment, error_code, error_message, **kwargs):
    """결제 실패 로깅"""
    # ✅ 안전: 에러 코드/메시지만 로깅
    logger.error(
        "Payment failed",
        extra={
            "payment_id": payment.pk,
            "error_code": error_code,
            "error_message": error_message,
        }
    )
```

### 4.2 피해야 할 패턴

```python
@receiver(payment_approved)
def unsafe_handler(sender, payment, approval_data, **kwargs):
    # ❌ 위험: 전체 응답 데이터 로깅
    logger.info(f"Approval data: {approval_data}")

    # ❌ 위험: auth_id 로깅
    logger.info(f"Auth ID: {payment.auth_id}")

    # ❌ 위험: 카드번호 마스킹 없이 로깅
    logger.info(f"Card: {payment.card_no}")
```

---

## 5. 결제 콜백 보안

### 5.1 Idempotency (멱등성) 처리

동일한 결제에 대해 중복 콜백이 발생할 수 있습니다.
`SandboxCallbackView`는 다음과 같이 처리합니다:

```python
from django.db import transaction

with transaction.atomic():
    # select_for_update로 동시 접근 방지
    payment = Payment.objects.select_for_update().get(pk=payment_id)

    # 이미 처리된 결제는 스킵
    if payment.is_paid:
        return render(request, "already_paid.html")

    # 승인 처리
    result = client.approve_payment(payment, auth_id)
    payment.mark_as_paid(...)
```

### 5.2 금액 검증

결제 승인 시 요청 금액과 승인 금액이 일치하는지 검증합니다:

```python
# EasyPayClient.approve_payment() 내부
approved_amount = int(payment_info.get("approvalAmount", 0))
expected_amount = int(payment.amount)

if approved_amount != expected_amount:
    logger.error(
        "Payment amount mismatch detected",
        extra={
            "expected_amount": expected_amount,
            "approved_amount": approved_amount,
        }
    )
    # 경고만 로깅 (승인 자체는 진행)
    # 프로젝트에서 필요시 예외 발생 처리 가능
```

### 5.3 CSRF 면제

EasyPay 콜백은 외부에서 오는 요청이므로 CSRF 검증을 면제해야 합니다:

```python
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator

@method_decorator(csrf_exempt, name="dispatch")
class PaymentCallbackView(View):
    """EasyPay 콜백 처리"""
    pass
```

---

## 6. 환경 설정 보안

### 6.1 필수 환경변수

```python
# settings.py 또는 settings.toml
EASYPAY_MALL_ID = "실제_MID"  # 테스트: T0021792
EASYPAY_API_URL = "https://pgapi.easypay.co.kr"  # 운영 URL
EASYPAY_SECRET_KEY = "..."  # 절대 코드에 하드코딩 금지
```

### 6.2 1Password 연동 (권장)

```bash
# .env.template (프로젝트별 설정)
# EasyPay 자격 증명은 각 프로젝트의 project-{name} 아이템에 저장
EASYPAY_MALL_ID="op://dev/project-sajudoctor/easypay_mall_id"
EASYPAY_SECRET_KEY="op://dev/project-sajudoctor/easypay_secret_key"
```

### 6.3 테스트 환경 분리

```python
# 테스트 환경에서는 테스트 MID 사용
if settings.DEBUG:
    EASYPAY_MALL_ID = "T0021792"
    EASYPAY_API_URL = "https://testpgapi.easypay.co.kr"
```

---

## 7. 체크리스트

### 7.1 개발 시 확인사항

- [ ] 로그에 `auth_id` 포함 여부 확인
- [ ] 로그에 전체 API 응답 포함 여부 확인
- [ ] 카드번호 마스킹 적용 확인
- [ ] Signal receiver에서 민감 데이터 처리 확인

### 7.2 배포 전 확인사항

- [ ] `DEBUG = False` 설정
- [ ] 운영 MID 및 API URL 설정
- [ ] `EASYPAY_SECRET_KEY` 환경변수 설정
- [ ] Admin 권한 설정 확인
- [ ] 로그 레벨 설정 (DEBUG 비활성화)

### 7.3 운영 중 확인사항

- [ ] 정기적인 Admin 감사 로그 검토
- [ ] 결제 실패 로그 모니터링
- [ ] 금액 불일치 경고 모니터링
- [ ] 비정상 취소 패턴 감지

---

## 8. PCI-DSS 준수 참고사항

django-easypay는 PG사(EasyPay)를 통한 결제 처리를 위한 패키지입니다.
실제 카드 정보는 EasyPay 서버에서 처리되며, 이 패키지에서는:

1. **카드번호**: 마스킹된 형태로만 저장 (예: `1234-****-****-5678`)
2. **CVV**: 저장하지 않음
3. **유효기간**: 저장하지 않음
4. **인증 토큰**: 로깅하지 않음

PCI-DSS 완전 준수를 위해서는 서버 인프라, 네트워크, 접근 제어 등
추가적인 보안 조치가 필요합니다.

---

## 참고 자료

- [EasyPay Developer Center](https://developer.easypay.co.kr)
- [PCI DSS 요구사항](https://www.pcisecuritystandards.org/)
- [Django 보안 가이드](https://docs.djangoproject.com/en/5.0/topics/security/)
