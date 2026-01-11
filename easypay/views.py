"""
View mixins for EasyPay payment integration.

Usage:
    from easypay.views import PaymentViewMixin

    class OrderCreateView(PaymentViewMixin, View):
        payment_model = Order

        def post(self, request):
            order = self.create_payment(
                amount=29900,
                product=product,
                user=request.user,
            )
            # client_ip and client_user_agent are automatically set
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .utils import get_client_ip, get_user_agent

if TYPE_CHECKING:
    from django.http import HttpRequest

    from .models import AbstractPayment


class PaymentViewMixin:
    """
    Mixin for views that create or update payment objects.

    This mixin provides helper methods to automatically populate
    client tracking information (IP address, user agent) when
    creating or updating payment objects.

    Attributes:
        payment_model: The payment model class to use for create_payment().
                       Must be set in the subclass.
        request: The Django request object (provided by View).

    Example:
        class OrderCreateView(PaymentViewMixin, View):
            payment_model = Order

            def post(self, request, slug):
                product = get_object_or_404(Product, slug=slug)
                order = self.create_payment(
                    name=request.POST['name'],
                    amount=product.price,
                    product=product,
                )
                return redirect('payment:confirm', hash_id=order.hash_id)
    """

    payment_model: type[AbstractPayment] | None = None
    request: HttpRequest

    def get_client_info(self) -> dict[str, Any]:
        """
        Extract client information from the current request.

        Returns:
            Dictionary with client_ip and client_user_agent
        """
        return {
            "client_ip": get_client_ip(self.request),
            "client_user_agent": get_user_agent(self.request),
        }

    def create_payment(self, **kwargs: Any) -> AbstractPayment:
        """
        Create a payment object with client info automatically populated.

        This method creates a new payment object using the payment_model
        and automatically sets client_ip and client_user_agent from
        the current request.

        Args:
            **kwargs: Fields to pass to the model constructor

        Returns:
            Created and saved payment instance

        Raises:
            ValueError: If payment_model is not set
        """
        if self.payment_model is None:
            raise ValueError(
                "payment_model must be set on the view class. Example: payment_model = Order"
            )

        kwargs.update(self.get_client_info())
        # Note: payment_model is a concrete subclass with objects manager
        return self.payment_model.objects.create(**kwargs)  # type: ignore[attr-defined, no-any-return]

    def update_payment_client_info(self, payment: AbstractPayment) -> bool:
        """
        Update client info on an existing payment if not already set.

        This is useful as a fallback when a payment was created without
        client info (e.g., in a different view or process).

        Args:
            payment: The payment object to update

        Returns:
            True if updated, False if client_ip was already set
        """
        if payment.client_ip:
            return False

        payment.set_client_info(self.request)
        payment.save(update_fields=["client_ip", "client_user_agent"])
        return True
