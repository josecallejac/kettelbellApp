"""Dispatch due reminders for active adaptive-plan sessions."""

import time
from datetime import datetime

from django.core.management.base import BaseCommand
from django.utils import timezone

from exercises.models import PlannedSession
from exercises.push_utils import send_push_to_user


class Command(BaseCommand):
    help = 'Envía recordatorios push de sesiones planificadas pendientes.'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', help='Muestra los avisos sin enviarlos.')
        parser.add_argument('--loop', action='store_true', help='Repite el chequeo periódicamente.')
        parser.add_argument('--interval', type=int, default=60, help='Segundos entre chequeos en modo loop.')

    def _dispatch_once(self, dry_run=False):
        now = timezone.localtime()
        today = now.date()
        sessions = PlannedSession.objects.select_related('plan__user').filter(
            plan__status='active',
            plan__reminders_enabled=True,
            scheduled_date=today,
            status='pending',
            reminder_sent_at__isnull=True,
        )
        sent = 0
        skipped = 0
        for session in sessions.iterator():
            reminder_time = session.plan.reminder_time
            if reminder_time is None:
                skipped += 1
                continue
            scheduled_at = timezone.make_aware(
                datetime.combine(today, reminder_time),
                timezone.get_current_timezone(),
            )
            if scheduled_at > now:
                skipped += 1
                continue
            payload = {
                'title': 'Tu sesión de hoy está lista 💪',
                'body': f'{session.focus.title()} · {session.estimated_duration} min. Tu plan se adapta a tu progreso.',
                'url': '/plan/',
                'type': 'plan_session_reminder',
                'planned_session_id': session.id,
            }
            if dry_run:
                self.stdout.write(f'  [DRY] plan session {session.id} → {session.plan.user.username}')
                sent += 1
                continue
            delivered = send_push_to_user(session.plan.user, payload)
            if delivered:
                PlannedSession.objects.filter(
                    pk=session.pk,
                    reminder_sent_at__isnull=True,
                ).update(reminder_sent_at=timezone.now(), updated_at=timezone.now())
                sent += 1
            else:
                skipped += 1
        return sent, skipped

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        interval = max(15, options['interval'])
        while True:
            sent, skipped = self._dispatch_once(dry_run=dry_run)
            self.stdout.write(self.style.SUCCESS(f'Plan reminders: {sent} sent, {skipped} skipped'))
            if not options['loop']:
                break
            time.sleep(interval)
