"""Domain services for four-week adaptive training plans."""

from datetime import timedelta

from django.db import transaction
from django.db.models import Avg, Count
from django.utils import timezone

from .models import PlannedSession, TrainingPlan, UserProfile, WorkoutLog
from .utils import RoutineGenerator
from .weights import normalize_available_weights

PLAN_WEEKS = 4
PLAN_DAYS = PLAN_WEEKS * 7
PHASES = ('base', 'base', 'build', 'deload')

GOAL_ROLES = {
    'strength': {'primary': 'strength', 'secondary': 'full_body', 'recovery': 'flexibility'},
    'fat_loss': {'primary': 'cardio', 'secondary': 'full_body', 'recovery': 'flexibility'},
    'mobility': {'primary': 'flexibility', 'secondary': 'full_body', 'recovery': 'flexibility'},
    'general': {'primary': 'full_body', 'secondary': 'strength', 'recovery': 'flexibility'},
}


def _focus_for_session(goal, frequency, slot, week_number):
    """Return (focus, kind) for a weekly slot, preserving recovery exposure."""
    roles = GOAL_ROLES.get(goal, GOAL_ROLES['general'])
    if frequency == 2:
        pattern = ('primary', 'secondary')
    elif frequency == 3:
        pattern = ('primary', 'secondary', 'recovery')
    elif frequency == 4:
        pattern = ('primary', 'secondary', 'primary', 'recovery')
    else:
        pattern = ('primary', 'secondary', 'primary', 'secondary', 'recovery')

    role = pattern[slot]
    focus = roles[role]
    if goal == 'general' and role == 'secondary':
        # Alternate conditioning and strength across cycles without changing the
        # user's stated goal.
        focus = 'strength' if week_number % 2 else 'cardio'
    return focus, 'recovery' if role == 'recovery' else 'main'


def _phase_reason(phase, focus, session_kind):
    if phase == 'deload':
        return 'Semana de descarga: volumen reducido para recuperar y consolidar.'
    if phase == 'build':
        return 'Semana de construcción: el volumen puede subir si tu esfuerzo reciente fue cómodo.'
    if session_kind == 'recovery':
        return 'Sesión de movilidad y recuperación para llegar mejor a la siguiente carga.'
    return f'Semana base enfocada en {focus}.'


def build_schedule(start_date, goal, frequency, weekdays, level, duration):
    """Build deterministic session rows for four contiguous seven-day blocks."""
    days = sorted({int(day) for day in weekdays})
    # The plan may start on any calendar day. Keep the selected ISO weekdays
    # meaningful by rotating them relative to that first day instead of
    # treating Monday=0 as a raw offset from ``start_date``.
    ordered_days = sorted(days, key=lambda day: (day - start_date.weekday()) % 7)
    offsets = [(day - start_date.weekday()) % 7 for day in ordered_days]
    sessions = []
    sequence = 1
    for week_number in range(1, PLAN_WEEKS + 1):
        phase = PHASES[week_number - 1]
        week_start = start_date + timedelta(weeks=week_number - 1)
        for slot, offset in enumerate(offsets):
            focus, session_kind = _focus_for_session(goal, frequency, slot, week_number)
            scheduled_date = week_start + timedelta(days=offset)
            sessions.append({
                'sequence': sequence,
                'week_number': week_number,
                'scheduled_date': scheduled_date,
                'focus': focus,
                'session_kind': session_kind,
                'phase': phase,
                'estimated_duration': duration,
                'adaptation_reason': _phase_reason(phase, focus, session_kind),
                'level': level,
            })
            sequence += 1
    return sessions


@transaction.atomic
def create_training_plan(user, cleaned_data):
    """Create one active plan and persist its four-week calendar."""
    profile, _ = UserProfile.objects.select_for_update().get_or_create(user=user)
    open_plan = TrainingPlan.objects.filter(user=user, status__in=('active', 'paused')).first()
    if open_plan:
        return open_plan, False

    profile.level = cleaned_data['level']
    profile.goal = cleaned_data['goal']
    profile.available_weights = normalize_available_weights(
        cleaned_data.get('available_weights', '')
    )
    profile.plan_prompt_dismissed_at = None
    profile.save(update_fields=['level', 'goal', 'available_weights', 'plan_prompt_dismissed_at', 'updated_at'])

    start_date = cleaned_data['start_date']
    frequency = cleaned_data['sessions_per_week']
    plan = TrainingPlan.objects.create(
        user=user,
        goal=cleaned_data['goal'],
        level=cleaned_data['level'],
        sessions_per_week=frequency,
        session_duration=cleaned_data['session_duration'],
        preferred_weekdays=cleaned_data['preferred_weekdays'],
        start_date=start_date,
        end_date=start_date + timedelta(days=PLAN_DAYS - 1),
        reminders_enabled=cleaned_data.get('reminders_enabled', False),
        reminder_time=cleaned_data.get('reminder_time'),
        status='active',
    )
    rows = build_schedule(
        start_date=start_date,
        goal=plan.goal,
        frequency=plan.sessions_per_week,
        weekdays=plan.preferred_weekdays,
        level=plan.level,
        duration=plan.session_duration,
    )
    PlannedSession.objects.bulk_create([
        PlannedSession(plan=plan, **{key: value for key, value in row.items() if key != 'level'})
        for row in rows
    ])
    return plan, True


def get_open_plan(user):
    return (
        TrainingPlan.objects.filter(user=user, status__in=('active', 'paused'))
        .prefetch_related('sessions')
        .first()
    )


def next_planned_session(plan, today=None):
    """Overdue sessions take priority, then today's and upcoming sessions."""
    today = today or timezone.localdate()
    pending = plan.sessions.filter(status='pending')
    return (
        pending.filter(scheduled_date__lte=today).order_by('scheduled_date', 'sequence').first()
        or pending.filter(scheduled_date__gt=today).order_by('scheduled_date', 'sequence').first()
    )


def plan_progress(plan):
    counts = plan.sessions.values('status').annotate(count=Count('id'))
    by_status = {row['status']: row['count'] for row in counts}
    total = sum(by_status.values())
    completed = by_status.get('completed', 0)
    return {
        'total': total,
        'completed': completed,
        'pending': by_status.get('pending', 0),
        'skipped': by_status.get('skipped', 0),
        'percent': round(completed * 100 / total) if total else 0,
    }


def _recent_plan_rpe(user, plan):
    values = list(
        WorkoutLog.objects.filter(
            user=user,
            planned_session__plan=plan,
            rpe__isnull=False,
        )
        .order_by('-completed_at')
        .values_list('rpe', flat=True)[:5]
    )
    return values, (sum(values) / len(values) if values else None)


def adaptation_for_session(user, planned_session):
    """Return the generator modifier and human-readable explanation."""
    values, average = _recent_plan_rpe(user, planned_session.plan)
    if planned_session.phase == 'deload':
        return -1, 'Descarga programada: reducimos el volumen para recuperar.'
    if average is not None and average >= 8.5:
        return -1, f'RPE reciente {average:.1f}: reducimos el volumen para recuperar.'
    if planned_session.phase == 'build' and len(values) >= 2 and average <= 7:
        return 1, f'RPE reciente {average:.1f}: añadimos un movimiento principal con control.'
    if planned_session.session_kind == 'recovery':
        return 0, 'Sesión de recuperación: priorizamos movilidad y técnica.'
    return 0, 'Volumen base; el peso se adapta por ejercicio según tus últimas sesiones.'


def _validated_readiness(readiness):
    """Normalize and validate the short pre-session readiness check."""
    if not readiness:
        return None
    try:
        energy_level = int(readiness['energy_level'])
        available_minutes = int(readiness['available_minutes'])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError('Completa los tres datos de preparación antes de entrenar.') from exc
    pain_level = readiness.get('pain_level')
    if energy_level not in {1, 2, 3, 4, 5}:
        raise ValueError('La energía debe estar entre 1 y 5.')
    if pain_level not in {'none', 'mild', 'stop'}:
        raise ValueError('Selecciona una opción válida para dolor o molestia.')
    if not 10 <= available_minutes <= 120:
        raise ValueError('Los minutos disponibles deben estar entre 10 y 120.')
    return {
        'energy_level': energy_level,
        'pain_level': pain_level,
        'available_minutes': available_minutes,
    }


def _readiness_from_session(session):
    if not session.readiness_checked_at:
        return None
    return _validated_readiness({
        'energy_level': session.energy_level,
        'pain_level': session.pain_level,
        'available_minutes': session.available_minutes,
    })


@transaction.atomic
def prepare_planned_session(user, planned_session, regenerate=False, readiness=None):
    """Materialize a private workout exactly once for a pending session."""
    session = (
        PlannedSession.objects.select_for_update()
        .select_related('plan')
        .get(pk=planned_session.pk, plan__user=user)
    )
    if session.status != 'pending':
        raise ValueError('La sesión ya no está pendiente.')
    if session.plan.status != 'active':
        raise ValueError('El plan no está activo.')
    previous_readiness = _readiness_from_session(session)
    normalized_readiness = (
        _validated_readiness(readiness)
        if readiness is not None
        else _readiness_from_session(session)
    )
    if normalized_readiness is None:
        raise ValueError('Completa el chequeo de preparación antes de generar la sesión.')
    readiness_changed = readiness is not None and normalized_readiness != previous_readiness
    if readiness is not None:
        session.energy_level = normalized_readiness['energy_level']
        session.pain_level = normalized_readiness['pain_level']
        session.available_minutes = normalized_readiness['available_minutes']
        session.readiness_checked_at = timezone.now()
        session.save(update_fields=[
            'energy_level',
            'pain_level',
            'available_minutes',
            'readiness_checked_at',
            'updated_at',
        ])
    if normalized_readiness['pain_level'] == 'stop':
        previous_workout = session.workout
        session.workout = None
        session.adaptation_reason = (
            'No se generó la rutina porque indicaste dolor. Descansa, considera '
            'reprogramar u omitir la sesión y busca orientación profesional si persiste.'
        )
        session.save(update_fields=['workout', 'adaptation_reason', 'updated_at'])
        # A pending plan routine has no completed log yet. Remove only an
        # unreferenced routine owned by this plan; a logged routine remains so
        # its historical snapshot can be preserved.
        if (
            previous_workout
            and previous_workout.is_plan_managed
            and not WorkoutLog.objects.filter(workout=previous_workout).exists()
        ):
            previous_workout.delete()
        return session
    if session.workout_id and not regenerate and not readiness_changed:
        return session

    volume_modifier, reason = adaptation_for_session(user, session)
    readiness_reasons = []
    low_readiness = (
        normalized_readiness['energy_level'] <= 2
        or normalized_readiness['pain_level'] == 'mild'
    )
    if low_readiness:
        volume_modifier = min(volume_modifier, -1)
        readiness_reasons.append(
            'Energía baja o molestia leve: reducimos volumen y no subimos peso.'
        )
    duration = min(session.estimated_duration, normalized_readiness['available_minutes'])
    if duration < session.estimated_duration:
        readiness_reasons.append(
            f'Sesión acortada a {duration} min por el tiempo disponible.'
        )
    if readiness_reasons:
        reason = f'{reason} {" ".join(readiness_reasons)}'
    generator = RoutineGenerator(
        user=user,
        duration_minutes=duration,
        difficulty=session.plan.level,
        focus=session.focus,
        volume_modifier=volume_modifier,
        plan_phase=session.phase,
        session_kind=session.session_kind,
        allow_weight_progression=not low_readiness,
        apply_history_volume_adjustment=False,
    )
    workout = generator.generate()
    workout.is_plan_managed = True
    workout.is_public = False
    workout.description = f'{workout.description} {reason}'
    workout.save(update_fields=['is_plan_managed', 'is_public', 'description'])

    previous_workout = session.workout
    session.workout = workout
    session.adaptation_reason = reason
    session.save(update_fields=['workout', 'adaptation_reason', 'updated_at'])
    if previous_workout and previous_workout.pk != workout.pk:
        # It has no log because a completed session cannot be regenerated. The
        # delete is limited to the replaced, plan-managed routine.
        previous_workout.delete()
    return session


def plan_summary(user, plan):
    progress = plan_progress(plan)
    logs = WorkoutLog.objects.filter(user=user, planned_session__plan=plan)
    stats = logs.aggregate(sessions=Count('id'), avg_rpe=Avg('rpe'))
    return {
        **progress,
        'sessions_logged': stats['sessions'] or 0,
        'avg_rpe': round(stats['avg_rpe'], 1) if stats['avg_rpe'] is not None else None,
    }
