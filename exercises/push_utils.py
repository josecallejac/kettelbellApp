"""
Centralized push notification helpers.

Usage:
    from exercises.push_utils import send_push_to_user, send_workout_completed_push

    # Send a custom payload
    send_push_to_user(user, {'title': 'Hola', 'body': '...'})

    # Send a typed notification
    send_workout_completed_push(user, workout_title='Rutina Fuerza', streak=5)
"""

import json
import logging
import threading

from django.conf import settings

logger = logging.getLogger(__name__)


def send_push_to_user(user, payload):
    """Send a push notification to all active subscriptions of a user.

    Runs in a background thread to avoid blocking the response.
    Automatically cleans up expired/invalid subscriptions.
    """
    if not settings.VAPID_PRIVATE_KEY:
        logger.debug('VAPID_PRIVATE_KEY not set, skipping push')
        return 0

    from pywebpush import WebPushException, webpush

    from .models import PushSubscription

    subscriptions = PushSubscription.objects.filter(user=user)
    if not subscriptions.exists():
        return 0

    vapid_claims = {'sub': f'mailto:{settings.VAPID_ADMIN_EMAIL}'}
    data = json.dumps(payload) if isinstance(payload, dict) else payload
    sent = 0

    for sub in subscriptions:
        try:
            webpush(
                subscription_info={
                    'endpoint': sub.endpoint,
                    'keys': {'p256dh': sub.p256dh, 'auth': sub.auth},
                },
                data=data,
                vapid_private_key=settings.VAPID_PRIVATE_KEY,
                vapid_claims=vapid_claims,
            )
            sent += 1
        except WebPushException as exc:
            logger.warning('Push failed for %s: %s', user.username, exc)
            if hasattr(exc, 'response') and exc.response is not None:
                if exc.response.status_code in (400, 404, 410):
                    sub.delete()
                    logger.info('Removed expired subscription for %s', user.username)

    return sent


def _send_async(user, payload):
    """Fire-and-forget push send in a background thread."""
    thread = threading.Thread(
        target=send_push_to_user,
        args=(user, payload),
        daemon=True,
    )
    thread.start()


# ── Typed notification helpers ──────────────────────────────────────────────

def send_workout_completed_push(user, workout_title, streak=None, weight=None):
    """Congratulate user after completing a workout."""
    parts = [f'"{workout_title}" completada']
    if streak and streak > 1:
        parts.append(f'🔥 Racha de {streak} días')
    if weight:
        parts.append(f'🏋️ {weight:g} kg')

    _send_async(user, {
        'title': '¡Entrenamiento completado! 💪',
        'body': ' · '.join(parts),
        'url': '/dashboard/',
        'type': 'workout_completed',
    })


def send_streak_reminder_push(user):
    """Remind user to train today to keep their streak alive."""
    _send_async(user, {
        'title': '¡No pierdas tu racha! 🔥',
        'body': 'Entrena hoy para mantener tu racha activa.',
        'url': '/dashboard/',
        'type': 'streak_reminder',
    })


def send_inactivity_push(user, days):
    """Alert user who hasn't trained in several days."""
    _send_async(user, {
        'title': f'Llevas {days} días sin entrenar 😟',
        'body': 'Vuelve a la acción. Una sesión corta cuenta.',
        'url': '/workouts/generate/',
        'type': 'inactivity_alert',
    })


def send_new_pr_push(user, record_type, value):
    """Notify user about a new personal record."""
    messages = {
        'weight': f'Nuevo peso máximo: {value:g} kg 🏋️',
        'streak': f'Nueva mejor racha: {value} días 🔥',
        'sessions_week': f'Mejor semana: {value} sesiones 📅',
    }
    body = messages.get(record_type, f'Nuevo récord: {value}')

    _send_async(user, {
        'title': '¡Nuevo récord personal! 🏆',
        'body': body,
        'url': '/dashboard/',
        'type': 'new_pr',
    })
