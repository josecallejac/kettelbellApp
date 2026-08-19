"""
Management command to send push notification reminders to users
who haven't worked out today but have an active streak.

Usage:
    python manage.py send_push_reminders          # Send reminders
    python manage.py send_push_reminders --dry-run # Preview without sending
"""

import logging
from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone
from pywebpush import WebPushException, webpush

from exercises.models import PushSubscription, WorkoutLog

logger = logging.getLogger(__name__)


def _has_streak(user_id, today):
    """Check if user has a streak (worked out yesterday or today)."""
    yesterday = today - timedelta(days=1)
    return WorkoutLog.objects.filter(
        user_id=user_id,
        completed_at__date__gte=yesterday,
    ).exists()


def _worked_out_today(user_id, today):
    """Check if user already worked out today."""
    return WorkoutLog.objects.filter(
        user_id=user_id,
        completed_at__date=today,
    ).exists()


class Command(BaseCommand):
    help = 'Send push notification reminders to users with active streaks'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Preview notifications without sending',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        today = timezone.localdate()

        if not settings.VAPID_PRIVATE_KEY:
            self.stderr.write(self.style.ERROR(
                'VAPID_PRIVATE_KEY not configured. Set it in environment.'
            ))
            return

        vapid_claims = {'sub': f'mailto:{settings.VAPID_ADMIN_EMAIL}'}

        # Get all push subscriptions for users with active streaks
        subscriptions = PushSubscription.objects.select_related('user').all()

        sent = 0
        skipped = 0
        errors = 0

        for sub in subscriptions:
            user_id = sub.user_id

            # Skip if user already worked out today
            if _worked_out_today(user_id, today):
                skipped += 1
                continue

            # Skip if user doesn't have a streak to lose
            if not _has_streak(user_id, today):
                skipped += 1
                continue

            payload = {
                'title': '¡No pierdas tu racha! 🔥',
                'body': 'Entrena hoy para mantener tu racha activa.',
                'url': '/dashboard/',
            }

            if dry_run:
                self.stdout.write(f'  [DRY] Would send to {sub.user.username}: {payload}')
                sent += 1
                continue

            try:
                webpush(
                    subscription_info={
                        'endpoint': sub.endpoint,
                        'keys': {'p256dh': sub.p256dh, 'auth': sub.auth},
                    },
                    data=self._build_payload(payload),
                    vapid_private_key=settings.VAPID_PRIVATE_KEY,
                    vapid_claims=vapid_claims,
                )
                sent += 1
                self.stdout.write(f'  [OK] Sent to {sub.user.username}')
            except WebPushException as exc:
                errors += 1
                logger.warning('Push failed for %s: %s', sub.user.username, exc)
                # Remove expired/invalid subscriptions
                if hasattr(exc, 'response') and exc.response is not None:
                    if exc.response.status_code in (400, 404, 410):
                        sub.delete()
                        self.stdout.write(f'  [DEL] Removed expired subscription for {sub.user.username}')

        self.stdout.write(self.style.SUCCESS(
            f'\nDone: {sent} sent, {skipped} skipped, {errors} errors'
        ))

    @staticmethod
    def _build_payload(data):
        """Build a JSON payload for the push notification."""
        import json
        return json.dumps(data)
