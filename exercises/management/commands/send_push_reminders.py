"""
Management command to send push notification reminders.

Usage:
    python manage.py send_push_reminders                         # All types
    python manage.py send_push_reminders --type streak            # Only streak reminders
    python manage.py send_push_reminders --type inactivity        # Only inactivity alerts
    python manage.py send_push_reminders --dry-run                # Preview without sending
    python manage.py send_push_reminders --type streak --dry-run  # Preview streak only
"""

import logging
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from exercises.models import PushSubscription, WorkoutLog
from exercises.push_utils import (
    send_inactivity_push,
    send_streak_reminder_push,
)

logger = logging.getLogger(__name__)

NOTIFICATION_TYPES = ('streak', 'inactivity')


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


def _days_since_last_workout(user_id, today):
    """Days since the user's last workout, or None if never."""
    last = (
        WorkoutLog.objects.filter(user_id=user_id)
        .order_by('-completed_at')
        .values_list('completed_at', flat=True)
        .first()
    )
    if last is None:
        return None
    return (today - timezone.localtime(last).date()).days


class Command(BaseCommand):
    help = 'Send push notification reminders (streak, inactivity)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--type',
            choices=NOTIFICATION_TYPES,
            default=None,
            help='Send only one type of notification (default: all)',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Preview notifications without sending',
        )
        parser.add_argument(
            '--inactivity-days',
            type=int,
            default=3,
            help='Days of inactivity before sending alert (default: 3)',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        notif_type = options['type']
        inactivity_threshold = options['inactivity_days']
        today = timezone.localdate()

        subscriptions = PushSubscription.objects.select_related('user').all()
        user_ids = set(subscriptions.values_list('user_id', flat=True))

        sent = 0
        skipped = 0

        for user_id in user_ids:
            user = subscriptions.filter(user_id=user_id).first().user

            # ── Streak reminder ──
            if notif_type in (None, 'streak'):
                if not _worked_out_today(user_id, today) and _has_streak(user_id, today):
                    if dry_run:
                        self.stdout.write(f'  [DRY] streak → {user.username}')
                    else:
                        send_streak_reminder_push(user)
                    sent += 1
                else:
                    skipped += 1

            # ── Inactivity alert ──
            if notif_type in (None, 'inactivity'):
                days = _days_since_last_workout(user_id, today)
                if days is not None and days >= inactivity_threshold:
                    if dry_run:
                        self.stdout.write(f'  [DRY] inactivity ({days}d) → {user.username}')
                    else:
                        send_inactivity_push(user, days)
                    sent += 1
                else:
                    skipped += 1

        self.stdout.write(self.style.SUCCESS(
            f'\nDone: {sent} sent, {skipped} skipped'
            + (' (dry run)' if dry_run else '')
        ))
