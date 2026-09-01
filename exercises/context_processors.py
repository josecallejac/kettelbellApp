"""Small application settings exposed to templates."""

from django.conf import settings


def app_config(request):
    """Expose only non-secret feature flags needed by the shared layout."""
    return {
        'allow_registration': settings.ALLOW_REGISTRATION,
    }
