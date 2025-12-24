"""
Custom exceptions for EasyPay payment integration.

Usage:
    from easypay.exceptions import EasyPayError, PaymentRegistrationError

    try:
        result = easypay_client.register_payment(payment, return_url)
    except PaymentRegistrationError as e:
        logger.error(f"Registration failed: {e.code} - {e.message}")
"""


class EasyPayError(Exception):
    """
    Base exception for EasyPay-related errors.

    Attributes:
        message: Human-readable error description
        code: EasyPay response code (if available)
        response: Raw API response dict (if available)
    """

    def __init__(
        self,
        message: str = "EasyPay error occurred",
        code: str = "",
        response: dict | None = None,
    ):
        self.message = message
        self.code = code
        self.response = response or {}
        super().__init__(self.message)

    def __str__(self):
        if self.code:
            return f"[{self.code}] {self.message}"
        return self.message


class PaymentRegistrationError(EasyPayError):
    """
    Raised when payment registration fails.

    This occurs during the initial payment request to get authPageUrl.
    """

    pass


class PaymentApprovalError(EasyPayError):
    """
    Raised when payment approval fails.

    This occurs after the user completes authentication
    but the final approval request fails.
    """

    pass


class PaymentCancellationError(EasyPayError):
    """
    Raised when payment cancellation/refund fails.

    This can occur when:
    - The payment is already cancelled
    - Partial refund amount exceeds original amount
    - PG system error
    """

    pass


class PaymentInquiryError(EasyPayError):
    """
    Raised when payment status inquiry fails.

    This occurs when querying transaction status from PG.
    """

    pass


class InvalidPaymentStateError(EasyPayError):
    """
    Raised when an operation is attempted on a payment in an invalid state.

    Examples:
    - Trying to approve an already completed payment
    - Trying to cancel a pending payment
    - Trying to refund an already refunded payment
    """

    pass


class ConfigurationError(EasyPayError):
    """
    Raised when EasyPay is not properly configured.

    This can occur when:
    - EASYPAY_MALL_ID is not set
    - EASYPAY_API_URL is not set
    - Invalid configuration values
    """

    pass
