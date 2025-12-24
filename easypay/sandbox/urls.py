"""
URL patterns for EasyPay sandbox.

Include this in your project's urls.py (only for development):

    if settings.DEBUG:
        urlpatterns += [
            path('easypay/sandbox/', include('easypay.sandbox.urls')),
        ]
"""

from django.urls import path

from .views import SandboxCallbackView, SandboxIndexView, SandboxPaymentView

app_name = "easypay_sandbox"

urlpatterns = [
    path("", SandboxIndexView.as_view(), name="index"),
    path("pay/", SandboxPaymentView.as_view(), name="pay"),
    path("callback/", SandboxCallbackView.as_view(), name="callback"),
]
