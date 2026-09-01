"""History, canonical workout metrics, and goal-aware progress summaries."""

from collections import Counter
from datetime import timedelta

from django.core.paginator import Paginator
from django.db.models import Prefetch, Q
from django.utils import timezone

from .models import Exercise, ExercisePerformance, UserProfile, WorkoutLog

HISTORY_PAGE_SIZE = 12
CATEGORY_LABELS = dict(Exercise.CATEGORY_CHOICES)
DIFFICULTY_LABELS = dict(Exercise.DIFFICULTY_CHOICES)
PERIOD_OPTIONS = (
    ('30', 'Últimos 30 días'),
    ('90', 'Últimos 90 días'),
    ('all', 'Todo el historial'),
)
SOURCE_OPTIONS = (
    ('all', 'Todas las sesiones'),
    ('plan', 'Sesiones de mi plan'),
    ('standalone', 'Sesiones independientes'),
)


def parse_history_filters(params):
    """Normalize public GET filters so invalid values never widen a query."""
    period = params.get('period', '30')
    if period not in {value for value, _ in PERIOD_OPTIONS}:
        period = '30'

    source = params.get('source', 'all')
    if source not in {value for value, _ in SOURCE_OPTIONS}:
        source = 'all'

    exercise_id = params.get('exercise', '')
    if not exercise_id.isdigit():
        exercise_id = ''

    query = (params.get('q') or '').strip()[:80]
    return {
        'period': period,
        'source': source,
        'exercise': exercise_id,
        'q': query,
    }


def history_filter_options(user):
    """Return only exercises that belong to the user's own logged history."""
    return Exercise.objects.filter(
        performance_logs__user=user,
    ).distinct().order_by('name')


def user_log_queryset(user):
    """Return a user's logs with the data needed by history pages."""
    details = ExercisePerformance.objects.filter(user=user).select_related(
        'exercise',
        'workout_exercise',
    )
    return WorkoutLog.objects.filter(user=user).select_related(
        'workout',
        'planned_session__plan',
    ).prefetch_related(
        # The filtered prefetch also protects against accidental cross-user
        # details if legacy data was imported incorrectly.
        Prefetch(
            'exercise_performances',
            queryset=details,
        ),
    )


def history_queryset(user, filters):
    """Build the private, filterable session queryset."""
    logs = user_log_queryset(user)

    period = filters['period']
    if period != 'all':
        days = int(period)
        cutoff = timezone.localdate() - timedelta(days=days - 1)
        logs = logs.filter(completed_at__date__gte=cutoff)

    if filters['source'] == 'plan':
        logs = logs.filter(planned_session__isnull=False)
    elif filters['source'] == 'standalone':
        logs = logs.filter(planned_session__isnull=True)

    if filters['exercise']:
        logs = logs.filter(
            exercise_performances__user=user,
            exercise_performances__exercise_id=int(filters['exercise']),
        ).distinct()

    if filters['q']:
        logs = logs.filter(
            Q(workout_title_snapshot__icontains=filters['q'])
            | Q(workout__title__icontains=filters['q'])
        )

    return logs.order_by('-completed_at', '-id')


def paginate_history(queryset, page_number):
    paginator = Paginator(queryset, HISTORY_PAGE_SIZE)
    return paginator.get_page(page_number or 1)


def local_log_date(log):
    if log.completed_at is None:
        return None
    if timezone.is_aware(log.completed_at):
        return timezone.localtime(log.completed_at).date()
    return log.completed_at.date()


def _ordered_performances(log):
    performances = list(log.exercise_performances.all())
    return sorted(
        performances,
        key=lambda performance: (
            performance.workout_exercise.order
            if performance.workout_exercise is not None else 10**9,
            performance.id,
        ),
    )


def log_metrics(log):
    """Return canonical metrics for a log, with legacy aggregate fallback."""
    performances = _ordered_performances(log)
    weights = [
        float(performance.weight)
        for performance in performances
        if performance.weight is not None and performance.weight > 0
    ]
    rpes = [
        performance.rpe
        for performance in performances
        if performance.rpe is not None
    ]
    volumes = [
        performance.volume
        for performance in performances
        if performance.volume is not None
    ]
    categories = Counter(
        (
            performance.exercise.category
            if performance.exercise is not None
            else performance.exercise_category_snapshot
        )
        for performance in performances
        if performance.exercise is not None or performance.exercise_category_snapshot
    )
    return {
        'performances': performances,
        'has_details': bool(performances),
        'sets': sum(performance.sets_completed or 0 for performance in performances),
        'completed_exercises': sum(1 for performance in performances if performance.completed),
        'exercise_count': len(performances),
        'volume': round(sum(volumes), 1) if volumes else None,
        'max_weight': max(weights) if weights else (
            float(log.kettlebell_weight)
            if log.kettlebell_weight is not None else None
        ),
        'rpe': log.rpe or (
            round(sum(rpes) / len(rpes), 1) if rpes else None
        ),
        'category_counts': categories,
    }


def summarize_logs(logs):
    """Aggregate logs without mixing one exercise's weight into another."""
    logs = list(logs)
    metrics = [log_metrics(log) for log in logs]
    rpes = [item['rpe'] for item in metrics if item['rpe'] is not None]
    weights = [item['max_weight'] for item in metrics if item['max_weight'] is not None]
    volumes = [item['volume'] for item in metrics if item['volume'] is not None]
    category_counts = Counter()
    mobility_sessions = 0
    for item in metrics:
        category_counts.update(item['category_counts'])
        if item['category_counts'].get('flexibility'):
            mobility_sessions += 1

    return {
        'sessions': len(logs),
        'minutes': sum(log.duration_minutes or 0 for log in logs),
        'avg_rpe': round(sum(rpes) / len(rpes), 1) if rpes else None,
        'total_volume': round(sum(volumes), 1) if volumes else None,
        'max_weight': max(weights) if weights else None,
        'sets': sum(item['sets'] for item in metrics),
        'completed_exercises': sum(item['completed_exercises'] for item in metrics),
        'mobility_sessions': mobility_sessions,
        'category_counts': category_counts,
    }


def _logs_between(logs, start, end):
    return [
        log for log in logs
        if (log_date := local_log_date(log)) is not None and start <= log_date <= end
    ]


def build_weekly_review(user, plan=None, today=None):
    """Compare the current week-to-date against the same days last week."""
    today = today or timezone.localdate()
    week_start = today - timedelta(days=today.weekday())
    elapsed_days = today.weekday() + 1
    previous_start = week_start - timedelta(days=7)
    previous_end = previous_start + timedelta(days=elapsed_days - 1)
    logs = list(
        WorkoutLog.objects.filter(user=user)
        .select_related('workout')
        .prefetch_related(
            'exercise_performances__exercise',
            'exercise_performances__workout_exercise',
        )
    )
    current = summarize_logs(_logs_between(logs, week_start, today))
    previous = summarize_logs(_logs_between(logs, previous_start, previous_end))

    adherence = None
    if plan is not None and plan.status == 'active':
        due_sessions = list(plan.sessions.filter(
            scheduled_date__gte=week_start,
            scheduled_date__lte=today,
        ))
        if due_sessions:
            completed = sum(session.status == 'completed' for session in due_sessions)
            adherence = {
                'completed': completed,
                'due': len(due_sessions),
                'percent': round(completed * 100 / len(due_sessions)),
            }

    return {
        'current': current,
        'previous': previous,
        'current_start': week_start,
        'current_end': today,
        'previous_start': previous_start,
        'previous_end': previous_end,
        'adherence': adherence,
        'goal_highlight': build_goal_highlight(
            user,
            current,
            previous,
            adherence=adherence,
        ),
    }


def build_weekly_trends(user, weeks=8, today=None):
    """Return compact weekly trend data for the progress page."""
    today = today or timezone.localdate()
    this_monday = today - timedelta(days=today.weekday())
    logs = list(
        WorkoutLog.objects.filter(user=user)
        .select_related('workout')
        .prefetch_related(
            'exercise_performances__exercise',
            'exercise_performances__workout_exercise',
        )
    )
    trends = []
    for offset in range(weeks - 1, -1, -1):
        start = this_monday - timedelta(weeks=offset)
        end = start + timedelta(days=6)
        summary = summarize_logs(_logs_between(logs, start, end))
        trends.append({
            'label': start.strftime('%d/%m'),
            'start': start,
            'sessions': summary['sessions'],
            'minutes': summary['minutes'],
            'avg_rpe': summary['avg_rpe'],
            'volume': summary['total_volume'],
        })
    max_sessions = max((item['sessions'] for item in trends), default=0)
    for item in trends:
        item['pct'] = round(item['sessions'] * 100 / max_sessions) if max_sessions else 0
    return trends


def _number(value):
    if value is None:
        return None
    return f'{value:.1f}'.rstrip('0').rstrip('.')


def build_goal_highlight(user, current, previous, adherence=None):
    profile = UserProfile.objects.filter(user=user).first()
    goal = profile.goal if profile is not None else 'general'
    if goal == 'strength':
        label = 'Volumen total'
        current_value = current['total_volume']
        previous_value = previous['total_volume']
        unit = 'kg'
        empty_label = 'Registra pesos y repeticiones para medir volumen.'
    elif goal == 'fat_loss':
        label = 'Minutos activos'
        current_value = current['minutes']
        previous_value = previous['minutes']
        unit = 'min'
        empty_label = 'Completa sesiones para medir tu constancia.'
    elif goal == 'mobility':
        label = 'Sesiones de movilidad'
        current_value = current['mobility_sessions']
        previous_value = previous['mobility_sessions']
        unit = 'sesiones'
        empty_label = 'Registra ejercicios de movilidad para ver esta tendencia.'
    else:
        label = 'Sesiones completadas'
        current_value = current['sessions']
        previous_value = previous['sessions']
        unit = 'sesiones'
        empty_label = 'Completa tu primera sesión para iniciar el seguimiento.'

    delta = None
    if current_value is not None and previous_value is not None:
        delta = current_value - previous_value

    if current_value in (None, 0):
        insight = empty_label
    elif current['avg_rpe'] is not None and current['avg_rpe'] >= 9:
        insight = 'El esfuerzo medio fue alto; prioriza técnica y recuperación antes de subir carga.'
    elif adherence and adherence['completed'] < adherence['due']:
        insight = f"Llevas {adherence['completed']} de {adherence['due']} sesiones previstas esta semana."
    elif delta is None or previous_value == 0:
        insight = 'Ya tienes una primera referencia para comparar tus próximas semanas.'
    elif delta > 0:
        insight = f'Vas por encima del periodo comparable en {abs(delta):g} {unit}.'
    elif delta < 0:
        insight = f'Vas {abs(delta):g} {unit} por debajo del periodo comparable; retoma gradualmente.'
    else:
        insight = 'Mantienes el mismo nivel que en el periodo comparable.'

    return {
        'goal': goal,
        'label': label,
        'value': current_value,
        'value_display': _number(current_value),
        'unit': unit,
        'previous_value': previous_value,
        'previous_display': _number(previous_value),
        'delta': delta,
        'delta_display': _number(delta),
        'insight': insight,
    }


def history_row(log):
    metrics = log_metrics(log)
    workout_title = log.workout_title_snapshot or (
        log.workout.title if log.workout is not None else 'Rutina eliminada'
    )
    return {
        'log': log,
        'title': workout_title,
        'date': timezone.localtime(log.completed_at) if timezone.is_aware(log.completed_at) else log.completed_at,
        'duration': log.duration_minutes,
        'rpe': metrics['rpe'],
        'weight': metrics['max_weight'],
        'volume': metrics['volume'],
        'sets': metrics['sets'],
        'exercise_count': metrics['exercise_count'],
        'has_details': metrics['has_details'],
        'edited': log.edited_at,
        'planned': log.planned_session is not None,
    }


def performance_display(performance):
    exercise = performance.exercise
    workout_exercise = performance.workout_exercise
    category_code = performance.exercise_category_snapshot or (
        exercise.category if exercise is not None else ''
    )
    return {
        'performance': performance,
        'exercise_name': performance.exercise_name_snapshot or (
            exercise.name if exercise is not None else 'Ejercicio eliminado'
        ),
        'category': CATEGORY_LABELS.get(category_code, category_code),
        'target_sets': performance.target_sets or (
            workout_exercise.sets if workout_exercise is not None else None
        ),
        'target_reps': performance.target_reps or (
            workout_exercise.reps if workout_exercise is not None else ''
        ),
        'volume': performance.volume,
    }


def detail_context(log):
    metrics = log_metrics(log)
    difficulty_code = log.workout_difficulty_snapshot or (
        log.workout.difficulty if log.workout is not None else ''
    )
    return {
        'log': log,
        'title': log.workout_title_snapshot or (
            log.workout.title if log.workout is not None else 'Rutina eliminada'
        ),
        'difficulty': DIFFICULTY_LABELS.get(difficulty_code, difficulty_code),
        'metrics': metrics,
        'performances': [performance_display(item) for item in metrics['performances']],
        'planned_session': log.planned_session,
    }


def progress_context(user, filtered_page, filters, plan=None):
    logs = list(filtered_page.object_list)
    review = build_weekly_review(user, plan=plan)
    return {
        'history_rows': [history_row(log) for log in logs],
        'history_page': filtered_page,
        'review': review,
        'weekly_trends': build_weekly_trends(user),
        'period_options': PERIOD_OPTIONS,
        'source_options': SOURCE_OPTIONS,
        'filters': filters,
        'exercise_options': history_filter_options(user),
    }
