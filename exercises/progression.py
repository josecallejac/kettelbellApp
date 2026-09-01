"""Progression and history helpers for exercise-level performance data."""

from collections import OrderedDict
from math import isfinite

from django.utils import timezone

from .models import ExercisePerformance, UserProfile

RPE_EASY_THRESHOLD = 7
RPE_HARD_THRESHOLD = 9


def _to_float(value):
    if value is None:
        return None
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return result if isfinite(result) else None


def _profile_and_weights(user):
    profile = UserProfile.objects.filter(user=user).first()
    weights = profile.weights_list() if profile else []
    # El perfil histórico permite texto libre por compatibilidad; aquí solo
    # usamos pesos positivos y seguros para recomendaciones.
    return profile, weights


def _profile_default_weight(profile, exercise, weights):
    if not profile or not weights:
        return None

    level_index = {
        'beginner': 0,
        'intermediate': len(weights) // 2,
        'advanced': len(weights) - 1,
    }
    index = level_index.get(profile.level, len(weights) // 2)
    if exercise.category == 'cardio':
        index = max(0, index - 1)
    return weights[index]


def _next_available_weight(weights, current):
    higher = [weight for weight in weights if weight > current]
    if higher:
        return higher[0]
    return _nearest_available_weight(weights, current) if weights else current


def _previous_available_weight(weights, current):
    previous = [weight for weight in weights if weight < current]
    return previous[-1] if previous else None


def _at_or_below_available_weight(weights, current):
    """Return the heaviest inventory weight that does not exceed ``current``."""
    available = [weight for weight in weights if weight <= current]
    return available[-1] if available else None


def _nearest_available_weight(weights, current):
    return min(weights, key=lambda weight: abs(weight - current))


def latest_exercise_performance(user, exercise):
    """Return the latest performance for this user and exact exercise."""
    return (
        ExercisePerformance.objects.filter(user=user, exercise=exercise)
        .select_related('workout_log', 'workout_exercise')
        .order_by('-workout_log__completed_at', '-created_at', '-id')
        .first()
    )


def recent_exercise_performances(user, exercise, latest=None, limit=2):
    """Return the latest exercise records, newest first."""
    query = (
        ExercisePerformance.objects.filter(user=user, exercise=exercise)
        .select_related('workout_log', 'workout_exercise')
        .order_by('-workout_log__completed_at', '-created_at', '-id')
    )
    if latest is None:
        return list(query[:limit])
    return [latest, *list(query.exclude(pk=latest.pk)[:max(0, limit - 1)])]


def recommend_exercise_progression(user, exercise, latest=None):
    """Recommend a safe next weight using only this exercise's history.

    The recommendation never invents a weight outside the user's profile. A
    missing history falls back to the profile's level/category preference.
    """
    profile, weights = _profile_and_weights(user)
    latest = latest if latest is not None else latest_exercise_performance(user, exercise)
    recent = recent_exercise_performances(user, exercise, latest=latest)
    last_weight = _to_float(latest.weight) if latest and latest.weight is not None else None
    last_rpe = latest.rpe if latest else None

    if latest is None:
        suggested = _profile_default_weight(profile, exercise, weights)
        reason = (
            'Primera referencia: usamos el peso de tu perfil.'
            if suggested is not None
            else 'Registra tu primera sesión para recibir una recomendación.'
        )
        return {
            'suggested_weight': _to_float(suggested),
            'last_weight': None,
            'last_rpe': None,
            'last_sets': None,
            'last_reps': None,
            'last_completed': None,
            'history_count': 0,
            'easy_sessions': 0,
            'reason': reason,
            'status': 'new',
        }

    if last_weight is None:
        suggested = _profile_default_weight(profile, exercise, weights)
        reason = (
            'No hay peso registrado en la última sesión; usa el valor de tu perfil.'
            if suggested is not None
            else 'No hay peso registrado. Añádelo para ajustar la progresión.'
        )
        status = 'profile' if suggested is not None else 'untracked'
    elif not latest.completed:
        suggested = _previous_available_weight(weights, last_weight)
        reason = 'Sesión incompleta: mantén o baja un nivel para recuperar técnica.'
        if suggested is None:
            reason += ' No hay un peso menor disponible; practica tecnica sin carga.'
        status = 'recover'
    elif last_rpe is not None and last_rpe >= RPE_HARD_THRESHOLD:
        suggested = _previous_available_weight(weights, last_weight)
        reason = 'RPE alto: reduce un nivel y prioriza la técnica.'
        if suggested is None:
            reason += ' No hay un peso menor disponible; practica tecnica sin carga.'
        status = 'deload'
    elif last_rpe is not None and last_rpe <= RPE_EASY_THRESHOLD:
        easy_sessions = sum(
            1
            for performance in recent
            if performance.completed
            and performance.rpe is not None
            and performance.rpe <= RPE_EASY_THRESHOLD
        )
        can_progress = len(recent) >= 2 and easy_sessions >= 2
        suggested = (
            _next_available_weight(weights, last_weight)
            if can_progress and weights else last_weight
        )
        if can_progress and suggested > last_weight:
            reason = 'RPE controlado: sube al siguiente peso disponible.'
            status = 'progress'
        elif not can_progress:
            reason = 'RPE controlado: repite una sesión para consolidar el movimiento.'
            status = 'maintain'
        else:
            reason = 'RPE controlado: mantén el peso máximo disponible.'
            status = 'maintain'
    else:
        if weights:
            suggested = _at_or_below_available_weight(weights, last_weight)
            if suggested is None:
                reason = (
                    'No hay un peso igual o menor en tu inventario; registra una carga '
                    'disponible para ajustar la progresión.'
                )
            else:
                reason = 'Mantén el peso y consolida el movimiento.'
        else:
            suggested = last_weight
            reason = 'Mantén el peso y consolida el movimiento.'
        status = 'maintain'

    return {
        'suggested_weight': _to_float(suggested),
        'last_weight': last_weight,
        'last_rpe': last_rpe,
        'last_sets': latest.sets_completed,
        'last_reps': latest.reps_completed,
        'last_completed': latest.completed,
        'history_count': ExercisePerformance.objects.filter(
            user=user,
            exercise=exercise,
        ).count(),
        'easy_sessions': sum(
            1
            for performance in recent
            if performance.completed
            and performance.rpe is not None
            and performance.rpe <= RPE_EASY_THRESHOLD
        ),
        'reason': reason,
        'status': status,
    }


def build_exercise_progress(user, exercise, limit=8):
    """Build detail-page history and summary for one exercise."""
    performances = list(
        ExercisePerformance.objects.filter(user=user, exercise=exercise)
        .select_related('workout_log__workout')
        .order_by('-workout_log__completed_at', '-created_at', '-id')
    )
    latest = performances[0] if performances else None
    recommendation = recommend_exercise_progression(user, exercise, latest=latest)
    rows = []
    for performance in performances[:limit]:
        completed_at = timezone.localtime(performance.workout_log.completed_at)
        workout = performance.workout_log.workout
        rows.append({
            'date': completed_at,
            'workout_title': (
                workout.title
                if workout
                else performance.workout_log.workout_title_snapshot or 'Rutina eliminada'
            ),
            'completed': performance.completed,
            'sets': performance.sets_completed,
            'reps': performance.reps_completed,
            'weight': _to_float(performance.weight),
            'rpe': performance.rpe,
            'volume': performance.volume,
        })

    completed_performances = [item for item in performances if item.completed]
    weights = [
        _to_float(item.weight)
        for item in completed_performances
        if item.weight is not None
    ]
    volumes = [item.volume for item in completed_performances if item.volume is not None]
    return {
        'sessions': len({item.workout_log_id for item in performances}),
        'max_weight': max(weights) if weights else None,
        'best_volume': max(volumes) if volumes else None,
        'latest': latest,
        'recommendation': recommendation,
        'history': rows,
    }


def build_dashboard_exercise_progress(user, limit=6):
    """Return recent exercise-level progress without cross-user data."""
    performances = (
        ExercisePerformance.objects.filter(user=user, exercise__isnull=False)
        .select_related('exercise', 'workout_log')
        .order_by('-workout_log__completed_at', '-created_at', '-id')
    )
    grouped = OrderedDict()
    for performance in performances:
        grouped.setdefault(performance.exercise_id, []).append(performance)

    highlights = []
    for items in list(grouped.values())[:limit]:
        latest = items[0]
        completed_items = [item for item in items if item.completed]
        weights = [
            _to_float(item.weight)
            for item in completed_items
            if item.weight is not None
        ]
        completed_at = timezone.localtime(latest.workout_log.completed_at)
        recommendation = recommend_exercise_progression(
            user,
            latest.exercise,
            latest=latest,
        )
        highlights.append({
            'exercise': latest.exercise,
            'sessions': len({item.workout_log_id for item in items}),
            'last_date': completed_at,
            'last_weight': _to_float(latest.weight),
            'max_weight': max(weights) if weights else None,
            'last_rpe': latest.rpe,
            'suggested_weight': recommendation['suggested_weight'],
            'reason': recommendation['reason'],
        })
    return highlights
