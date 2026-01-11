"""
Sandbox views for testing EasyPay integration.

These views provide a simple interface for testing payment flows.
Only accessible when DEBUG=True.
"""

import logging

from django.conf import settings
from django.db import transaction
from django.http import HttpRequest, HttpResponse, HttpResponseForbidden
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt

from easypay.client import EasyPayClient
from easypay.exceptions import EasyPayError
from easypay.utils import get_device_type_code

from .models import SandboxPayment

logger = logging.getLogger(__name__)


def debug_required(view_func):
    """Decorator to restrict access to DEBUG mode only."""

    def wrapper(request: HttpRequest, *args, **kwargs):
        if not settings.DEBUG:
            return HttpResponseForbidden(
                "Sandbox is only available in DEBUG mode. "
                "Set DEBUG=True in your settings to access this page."
            )
        return view_func(request, *args, **kwargs)

    return wrapper


class SandboxIndexView(View):
    """
    Display the payment test form.

    GET: Render the sandbox.html template with a form for testing payments.
    """

    @method_decorator(debug_required)
    def get(self, request: HttpRequest) -> HttpResponse:
        """Display payment test form."""
        context = {
            "title": "EasyPay Sandbox",
            "mall_id": getattr(settings, "EASYPAY_MALL_ID", "T0021792"),
            "api_url": getattr(settings, "EASYPAY_API_URL", "https://testpgapi.easypay.co.kr"),
        }
        return render(request, "easypay/sandbox.html", context)


class SandboxPaymentView(View):
    """
    Create a payment and redirect to EasyPay.

    POST: Create SandboxPayment, register with EasyPay, redirect to authPageUrl.
    """

    @method_decorator(debug_required)
    def post(self, request: HttpRequest) -> HttpResponse:
        """Process payment form and redirect to EasyPay."""
        # Parse form data
        try:
            amount = int(request.POST.get("amount", 1000))
        except (ValueError, TypeError):
            amount = 1000

        goods_name = request.POST.get("goods_name", "테스트 상품") or "테스트 상품"

        # Create sandbox payment with client info auto-populated
        # Using set_client_info() - the recommended pattern for existing instances
        payment = SandboxPayment.create_test_payment(
            amount=amount,
            goods_name=goods_name,
        )
        payment.set_client_info(request)  # New pattern: auto-sets client_ip & client_user_agent
        payment.save()

        logger.info(
            "Sandbox payment created",
            extra={
                "order_id": payment.order_id,
                "amount": amount,
                "goods_name": goods_name,
            },
        )

        # Build callback URL
        callback_url = request.build_absolute_uri(reverse("easypay_sandbox:callback"))
        # Include payment ID in callback
        callback_url = f"{callback_url}?payment_id={payment.pk}"

        # Force HTTPS if behind proxy (CloudFlare, etc.)
        # Skip for localhost development
        if (
            callback_url.startswith("http://")
            and "localhost" not in callback_url
            and "127.0.0.1" not in callback_url
        ):
            callback_url = callback_url.replace("http://", "https://", 1)

        try:
            # Register with EasyPay
            client = EasyPayClient()
            result = client.register_payment(
                payment=payment,
                return_url=callback_url,
                goods_name=goods_name,
                customer_name="테스트 고객",
                device_type_code=get_device_type_code(request),
            )

            auth_page_url = result.get("authPageUrl")
            if auth_page_url:
                logger.info(
                    "Redirecting to EasyPay",
                    extra={"order_id": payment.order_id},
                )
                return redirect(auth_page_url)
            else:
                # SECURITY: Do not log full API response (may contain sensitive data)
                logger.error(
                    "No authPageUrl in response",
                    extra={
                        "order_id": payment.order_id,
                        "response_code": result.get("resCd"),
                        "response_message": result.get("resMsg"),
                    },
                )
                return render(
                    request,
                    "easypay/callback.html",
                    {
                        "success": False,
                        "error_message": "결제 페이지 URL을 받지 못했습니다.",
                        "payment": payment,
                    },
                )

        except EasyPayError as e:
            logger.error(
                "EasyPay registration failed",
                extra={
                    "order_id": payment.order_id,
                    "error_code": e.code,
                    "error_message": e.message,
                },
            )
            payment.mark_as_failed()
            return render(
                request,
                "easypay/callback.html",
                {
                    "success": False,
                    "error_code": e.code,
                    "error_message": e.message,
                    "payment": payment,
                },
            )


@method_decorator(csrf_exempt, name="dispatch")
class SandboxCallbackView(View):
    """
    Handle EasyPay callback and display result.

    GET/POST: Parse authorizationId, resCd, resMsg, approve payment, display result.

    Note: @csrf_exempt is required because EasyPay redirects with GET/POST
    without CSRF token. EasyPay may send callback as either GET or POST
    depending on the payment method and configuration.
    """

    @method_decorator(debug_required)
    def dispatch(self, request, *args, **kwargs):
        return super().dispatch(request, *args, **kwargs)

    def get(self, request: HttpRequest) -> HttpResponse:
        """Handle GET callback from EasyPay."""
        return self._handle_callback(request)

    def post(self, request: HttpRequest) -> HttpResponse:
        """Handle POST callback from EasyPay."""
        return self._handle_callback(request)

    def _handle_callback(self, request: HttpRequest) -> HttpResponse:
        """Common callback handler for GET and POST."""
        # Get parameters from either GET or POST
        payment_id = request.GET.get("payment_id") or request.POST.get("payment_id")
        auth_id = request.GET.get("authorizationId") or request.POST.get("authorizationId")
        res_cd = request.GET.get("resCd") or request.POST.get("resCd")
        res_msg = request.GET.get("resMsg") or request.POST.get("resMsg")

        logger.info(
            "EasyPay callback received",
            extra={
                "payment_id": payment_id,
                "auth_id": auth_id,
                "res_cd": res_cd,
                "res_msg": res_msg,
                "method": request.method,
            },
        )

        if not payment_id:
            return render(
                request,
                "easypay/callback.html",
                {
                    "success": False,
                    "error_message": "payment_id 파라미터가 없습니다.",
                },
            )

        # Get payment
        try:
            payment = SandboxPayment.objects.get(pk=payment_id)
        except SandboxPayment.DoesNotExist:
            return render(
                request,
                "easypay/callback.html",
                {
                    "success": False,
                    "error_message": f"결제 정보를 찾을 수 없습니다. (ID: {payment_id})",
                },
            )

        # Check if already processed
        if payment.is_paid:
            return render(
                request,
                "easypay/callback.html",
                {
                    "success": True,
                    "payment": payment,
                    "message": "이미 결제가 완료된 건입니다.",
                },
            )

        # Check response code from EasyPay authentication
        # res_cd == "0000" means authentication succeeded
        if res_cd and res_cd != "0000":
            logger.error(
                "EasyPay authentication failed",
                extra={
                    "order_id": payment.order_id,
                    "res_cd": res_cd,
                    "res_msg": res_msg,
                },
            )
            payment.mark_as_failed()
            return render(
                request,
                "easypay/callback.html",
                {
                    "success": False,
                    "error_code": res_cd,
                    "error_message": res_msg or "결제 인증에 실패했습니다.",
                    "payment": payment,
                },
            )

        # Check for user cancellation (no authorizationId)
        if not auth_id:
            payment.mark_as_failed()
            return render(
                request,
                "easypay/callback.html",
                {
                    "success": False,
                    "error_message": "결제가 취소되었거나 인증 정보가 없습니다.",
                    "payment": payment,
                },
            )

        # Approve payment with idempotency lock
        # Use select_for_update to prevent race conditions on concurrent callbacks
        try:
            with transaction.atomic():
                # Re-fetch with lock to prevent double approval
                payment = SandboxPayment.objects.select_for_update().get(pk=payment_id)

                # Double-check after acquiring lock (another request may have processed it)
                if payment.is_paid:
                    logger.info(
                        "Payment already processed (concurrent request)",
                        extra={"payment_id": payment_id},
                    )
                    return render(
                        request,
                        "easypay/callback.html",
                        {
                            "success": True,
                            "payment": payment,
                            "message": "이미 결제가 완료된 건입니다.",
                        },
                    )

                client = EasyPayClient()
                result = client.approve_payment(payment=payment, authorization_id=auth_id)

                # Extract payment info
                pg_tid = result.get("pgTid", "")
                payment_info = result.get("paymentInfo", {})
                card_info = payment_info.get("cardInfo", {})

                # Update payment (inside transaction for atomicity)
                payment.mark_as_paid(
                    pg_tid=pg_tid,
                    authorization_id=auth_id,
                    pay_method_type_code=payment_info.get("payMethodTypeCode", ""),
                    card_name=card_info.get("cardName", ""),
                    card_no=card_info.get("cardNo", ""),
                )

            # Transaction committed, now log and render
            logger.info(
                "Sandbox payment approved",
                extra={
                    "order_id": payment.order_id,
                    "pg_tid": pg_tid,
                },
            )

            return render(
                request,
                "easypay/callback.html",
                {
                    "success": True,
                    "payment": payment,
                    "pg_tid": pg_tid,
                },
            )

        except EasyPayError as e:
            logger.error(
                "EasyPay approval failed",
                extra={
                    "order_id": payment.order_id,
                    "error_code": e.code,
                    "error_message": e.message,
                },
            )
            payment.mark_as_failed()
            return render(
                request,
                "easypay/callback.html",
                {
                    "success": False,
                    "error_code": e.code,
                    "error_message": e.message,
                    "payment": payment,
                },
            )
