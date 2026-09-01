import json
import logging
import uuid
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from functools import wraps

from django.conf import settings as django_settings
from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.core.paginator import Paginator
from django.db import connection, transaction
from django.db.models import Avg, Count, Max, Q, Sum
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_GET, require_POST

from .forms import (
    CustomAuthenticationForm,
    CustomUserCreationForm,
    ExercisePerformanceEditFormSet,
    SessionReadinessForm,
    TrainingPlanForm,
    UserProfileForm,
    WorkoutExerciseFormSet,
    WorkoutForm,
    WorkoutLogEditForm,
)
from .history import (
    detail_context,
    history_queryset,
    paginate_history,
    parse_history_filters,
    progress_context,
    user_log_queryset,
)
from .models import (
    Exercise,
    ExercisePerformance,
    Favorite,
    PlannedSession,
    PushSubscription,
    TrainingPlan,
    UserProfile,
    Workout,
    WorkoutLog,
)
from .plans import (
    create_training_plan,
    get_open_plan,
    next_planned_session,
    plan_progress,
    plan_summary,
    prepare_planned_session,
)
from .progression import (
    build_dashboard_exercise_progress,
    build_exercise_progress,
    recommend_exercise_progression,
)
from .utils import RoutineGenerator

logger = logging.getLogger(__name__)


def service_worker(request):
    """Serve the worker at the root so its scope can cover the whole app."""
    path = django_settings.BASE_DIR / 'exercises' / 'static' / 'exercises' / 'sw.js'
    response = HttpResponse(path.read_bytes(), content_type='application/javascript')
    response['Service-Worker-Allowed'] = '/'
    response['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    return response


def _render_public_page(request, template, context):
    """Render a page and make its cacheability explicit for the service worker."""
    response = render(request, template, context)
    if request.user.is_authenticated:
        response['Cache-Control'] = 'private, no-store'
        response['X-KB-Public-Cache'] = '0'
    else:
        response['Cache-Control'] = 'public, max-age=300'
        response['X-KB-Public-Cache'] = '1'
    return response


# ---------------------------------------------------------------------------
# Rate limiting
# ---------------------------------------------------------------------------
def rate_limit(key_prefix, max_requests=30, window_seconds=60):
    """Decorator that limits requests per user (authenticated) or per IP.

    Uses Django's cache backend.  Returns 429 when the limit is exceeded.
    """
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped(request, *args, **kwargs):
            if request.user.is_authenticated:
                identity = f"user:{request.user.pk}"
            else:
                identity = f"ip:{request.META.get('REMOTE_ADDR', 'unknown')}"
            cache_key = f"rl:{key_prefix}:{identity}"
            current = cache.get(cache_key)
            if current is None:
                cache.set(cache_key, 1, timeout=window_seconds)
            elif current >= max_requests:
                logger.warning("Rate limit exceeded: %s (%s)", key_prefix, identity)
                return JsonResponse(
                    {'status': 'error', 'message': 'Demasiadas solicitudes. Intenta más tarde.'},
                    status=429,
                )
            else:
                cache.incr(cache_key)
            return view_func(request, *args, **kwargs)
        return _wrapped
    return decorator


CATEGORY_ICONS = {
    'strength': '&#128170;',
    'cardio': '&#128293;',
    'flexibility': '&#129496;',
    'full_body': '&#127919;',
}

DIFFICULTY_ICONS = {
    'beginner': '&#127793;',
    'intermediate': '&#9889;',
    'advanced': '&#128640;',
}


def get_favorites_ids(request):
    if request.user.is_authenticated:
        return list(request.user.favorites.values_list('exercise_id', flat=True))
    return []


def parse_json_body(request):
    """Devuelve el body como dict, o None si no es JSON válido."""
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None
    return data if isinstance(data, dict) else None


def register_view(request):
    if not django_settings.ALLOW_REGISTRATION:
        raise Http404
    if request.user.is_authenticated:
        return redirect('exercises:landing')
    if request.method == 'POST':
        form = CustomUserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            return redirect('exercises:landing')
    else:
        form = CustomUserCreationForm()
    return render(request, 'registration/register.html', {'form': form})


@require_GET
def healthz(request):
    """Minimal unauthenticated health endpoint for the reverse proxy/container."""
    try:
        with connection.cursor() as cursor:
            cursor.execute('SELECT 1')
            cursor.fetchone()
    except Exception as exc:  # pragma: no cover - backend-specific failures
        logger.exception('Health check failed')
        payload = {
            'status': 'error',
            'app': 'kettlebell',
            'database': 'error',
            'release_sha': django_settings.RELEASE_SHA,
            'sha': django_settings.RELEASE_SHA,
        }
        if django_settings.DEBUG:
            payload['detail'] = str(exc)[:200]
        response = JsonResponse(payload, status=503)
        response['Cache-Control'] = 'no-store'
        return response
    response = JsonResponse({
        'status': 'ok',
        'app': 'kettlebell',
        'database': 'ok',
        'release_sha': django_settings.RELEASE_SHA,
        'sha': django_settings.RELEASE_SHA,
    })
    response['Cache-Control'] = 'no-store'
    return response

def login_view(request):
    if request.user.is_authenticated:
        return redirect('exercises:landing')
    if request.method == 'POST':
        form = CustomAuthenticationForm(data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            next_url = request.POST.get('next')
            if next_url and url_has_allowed_host_and_scheme(
                next_url, allowed_hosts={request.get_host()}, require_https=request.is_secure()
            ):
                return redirect(next_url)
            return redirect('exercises:landing')
    else:
        form = CustomAuthenticationForm()
    return render(request, 'registration/login.html', {'form': form})

@require_POST
def logout_view(request):
    logout(request)
    return redirect('exercises:landing')

@login_required
@require_POST
@rate_limit('toggle-favorite', max_requests=30, window_seconds=60)
def toggle_favorite(request):
    data = parse_json_body(request)
    try:
        exercise_id = int((data or {}).get('exercise_id'))
    except (TypeError, ValueError):
        return JsonResponse({'status': 'error', 'message': 'Petición inválida'}, status=400)

    exercise = get_object_or_404(Exercise, id=exercise_id)
    favorite, created = Favorite.objects.get_or_create(user=request.user, exercise=exercise)

    if not created:
        favorite.delete()

    return JsonResponse({'status': 'success', 'is_favorite': created})

@login_required
def favorites_list(request):
    favorites = Favorite.objects.filter(user=request.user).select_related('exercise')
    exercises = [f.exercise for f in favorites]
    return render(request, 'exercises/favorites.html', {'exercises': exercises})

FEATURED_EXERCISES_LIMIT = 8
LANDING_VIDEOS_LIMIT = 3


def landing_page(request):
    total_exercises = Exercise.objects.count()

    # Preview ligero: solo unos pocos destacados en lugar de toda la biblioteca.
    # Priorizamos los que tienen vídeo (más visuales) y rellenamos con el resto.
    featured_exercises = list(
        Exercise.objects.exclude(video_url='').order_by('-updated_at')[:FEATURED_EXERCISES_LIMIT]
    )
    if len(featured_exercises) < FEATURED_EXERCISES_LIMIT:
        already = [ex.id for ex in featured_exercises]
        featured_exercises += list(
            Exercise.objects.exclude(id__in=already)
            .order_by('-updated_at')[:FEATURED_EXERCISES_LIMIT - len(featured_exercises)]
        )

    video_exercises = [ex for ex in featured_exercises if ex.video_url][:LANDING_VIDEOS_LIMIT]

    context = {
        'featured_exercises': featured_exercises,
        'total_exercises': total_exercises,
        'favorites_ids': get_favorites_ids(request),
        'video_exercises': video_exercises,
        'show_plan_invite': request.user.is_authenticated and not get_open_plan(request.user) and not UserProfile.objects.filter(
            user=request.user,
            plan_prompt_dismissed_at__isnull=False,
        ).exists(),
    }

    return _render_public_page(request, 'exercises/landing.html', context)

EXERCISES_PER_PAGE = 12


def paginate_exercises(request, queryset):
    paginator = Paginator(queryset, EXERCISES_PER_PAGE)
    return paginator.get_page(request.GET.get('page'))


def exercise_list(request):
    search_query = request.GET.get('q', '').strip()
    category = request.GET.get('category', '').strip()
    difficulty = request.GET.get('difficulty', '').strip()
    muscle = request.GET.get('muscle', '').strip()

    exercises = Exercise.objects.all()

    if search_query:
        exercises = exercises.filter(
            Q(name__icontains=search_query)
            | Q(description__icontains=search_query)
            | Q(muscles_targeted__icontains=search_query)
            | Q(equipment__icontains=search_query)
        )

    if category and category in dict(Exercise.CATEGORY_CHOICES):
        exercises = exercises.filter(category=category)

    if difficulty and difficulty in dict(Exercise.DIFFICULTY_CHOICES):
        exercises = exercises.filter(difficulty=difficulty)

    if muscle:
        exercises = exercises.filter(muscles_targeted__icontains=muscle)

    page_obj = paginate_exercises(request, exercises)

    active_filters = []
    if search_query:
        active_filters.append(f'"{search_query}"')
    if category:
        active_filters.append(dict(Exercise.CATEGORY_CHOICES).get(category, category))
    if difficulty:
        active_filters.append(dict(Exercise.DIFFICULTY_CHOICES).get(difficulty, difficulty))
    if muscle:
        active_filters.append(f'músculo: {muscle}')

    if active_filters:
        subtitle = 'Filtrado por ' + ', '.join(active_filters) + '.'
        empty_message = 'No hay ejercicios que coincidan con los filtros seleccionados.'
    elif search_query:
        subtitle = f'Resultados para "{search_query}".'
        empty_message = f'No hay ejercicios que coincidan con "{search_query}".'
    else:
        subtitle = 'Biblioteca completa de ejercicios con kettlebell.'
        empty_message = 'No hay ejercicios disponibles todavia.'

    context = {
        'exercises': page_obj.object_list,
        'page_obj': page_obj,
        'search_query': search_query,
        'active_category': category,
        'active_difficulty': difficulty,
        'active_muscle': muscle,
        'show_search': True,
        'favorites_ids': get_favorites_ids(request),
        'page_title': 'Todos los ejercicios',
        'page_subtitle': subtitle,
        'page_kicker': 'Ejercicios',
        'empty_message': empty_message,
        'category_choices': Exercise.CATEGORY_CHOICES,
        'difficulty_choices': Exercise.DIFFICULTY_CHOICES,
    }
    return _render_public_page(request, 'exercises/exercise_collection.html', context)

def category_list(request):
    counts = dict(
        Exercise.objects.values('category').annotate(total=Count('id')).values_list('category', 'total')
    )
    cards = [
        {
            'value': value,
            'label': label,
            'count': counts.get(value, 0),
            'icon': CATEGORY_ICONS.get(value, '&#127919;'),
        }
        for value, label in Exercise.CATEGORY_CHOICES
    ]
    return _render_public_page(request, 'exercises/taxonomy_overview.html', {
        'page_title': 'Categorias',
        'page_subtitle': 'Elige una categoria para ver sus ejercicios.',
        'page_kicker': '4 grupos',
        'cards': cards,
        'url_name': 'exercises:category_detail',
        'count_label': 'ejercicios',
    })

def category_detail(request, category):
    category_labels = dict(Exercise.CATEGORY_CHOICES)
    if category not in category_labels:
        raise Http404("Categoria no encontrada")

    page_obj = paginate_exercises(request, Exercise.objects.filter(category=category))
    context = {
        'exercises': page_obj.object_list,
        'page_obj': page_obj,
        'favorites_ids': get_favorites_ids(request),
        'page_title': category_labels[category],
        'page_subtitle': 'Ejercicios filtrados por categoria.',
        'page_kicker': 'Categoria',
        'empty_message': 'No hay ejercicios en esta categoria todavia.',
    }
    return _render_public_page(request, 'exercises/exercise_collection.html', context)

def difficulty_list(request):
    counts = dict(
        Exercise.objects.values('difficulty').annotate(total=Count('id')).values_list('difficulty', 'total')
    )
    cards = [
        {
            'value': value,
            'label': label,
            'count': counts.get(value, 0),
            'icon': DIFFICULTY_ICONS.get(value, '&#127919;'),
        }
        for value, label in Exercise.DIFFICULTY_CHOICES
    ]
    return _render_public_page(request, 'exercises/taxonomy_overview.html', {
        'page_title': 'Niveles',
        'page_subtitle': 'Elige un nivel para ver los ejercicios recomendados.',
        'page_kicker': '3 niveles',
        'cards': cards,
        'url_name': 'exercises:difficulty_detail',
        'count_label': 'ejercicios',
    })

def difficulty_detail(request, difficulty):
    difficulty_labels = dict(Exercise.DIFFICULTY_CHOICES)
    if difficulty not in difficulty_labels:
        raise Http404("Nivel no encontrado")

    page_obj = paginate_exercises(request, Exercise.objects.filter(difficulty=difficulty))
    context = {
        'exercises': page_obj.object_list,
        'page_obj': page_obj,
        'favorites_ids': get_favorites_ids(request),
        'page_title': difficulty_labels[difficulty],
        'page_subtitle': 'Ejercicios filtrados por nivel.',
        'page_kicker': 'Nivel',
        'empty_message': 'No hay ejercicios en este nivel todavia.',
    }
    return _render_public_page(request, 'exercises/exercise_collection.html', context)

def exercise_detail(request, slug):
    exercise = get_object_or_404(Exercise, slug=slug)
    is_favorite = False
    if request.user.is_authenticated:
        is_favorite = Favorite.objects.filter(user=request.user, exercise=exercise).exists()

    def split_lines(value):
        return [line.strip() for line in (value or '').splitlines() if line.strip()]

    instruction_steps = split_lines(exercise.instructions)
    setup_tips = split_lines(exercise.setup_tips)
    common_mistakes = split_lines(exercise.common_mistakes)
    progressions = split_lines(exercise.progressions)
    precautions = split_lines(exercise.precautions)
    muscles_targeted = split_lines(exercise.muscles_targeted)
    variations = split_lines(exercise.variations)

    coaching_cards = [
        {
            'title': 'Antes de partir',
            'kicker': 'Setup',
            'items': setup_tips or [
                'Ubica la kettlebell cerca del cuerpo y crea tension en el core.',
                'Mantiene pies firmes, hombros abajo y columna neutra.',
            ],
        },
        {
            'title': 'Durante el movimiento',
            'kicker': 'Ejecucion',
            'items': instruction_steps[:4] or [
                'Mueve la pesa con control, sin perder la postura.',
                'Respira de forma estable y evita acelerar si la tecnica se rompe.',
            ],
        },
        {
            'title': 'Para saber si va bien',
            'kicker': 'Control',
            'items': [
                'La kettlebell viaja cerca del cuerpo cuando corresponde.',
                'No aparece dolor punzante en espalda, hombros, munecas o rodillas.',
                'Puedes terminar cada repeticion con la misma postura con que empezaste.',
            ],
        },
    ]

    related_exercises = Exercise.objects.filter(
        category=exercise.category
    ).exclude(id=exercise.id).order_by('?')[:3]
    exercise_progress = (
        build_exercise_progress(request.user, exercise)
        if request.user.is_authenticated
        else None
    )

    context = {
        'exercise': exercise,
        'is_favorite': is_favorite,
        'instruction_steps': instruction_steps,
        'setup_tips_list': setup_tips,
        'common_mistakes_list': common_mistakes,
        'progressions_list': progressions,
        'precautions_list': precautions,
        'muscles_targeted_list': muscles_targeted,
        'variations_list': variations,
        'coaching_cards': coaching_cards,
        'related_exercises': related_exercises,
        'exercise_progress': exercise_progress,
    }
    return render(request, 'exercises/detail.html', context)

def get_visible_workouts(user):
    """Workouts públicos más los privados del usuario autenticado."""
    if user.is_authenticated:
        return Workout.objects.filter(Q(is_public=True) | Q(created_by=user))
    return Workout.objects.filter(is_public=True)


def get_visible_workout_or_404(user, slug):
    return get_object_or_404(get_visible_workouts(user), slug=slug)


def workout_list(request):
    workouts = (
        get_visible_workouts(request.user)
        .filter(is_plan_managed=False)
        .annotate(num_exercises=Count('exercises'))
        .order_by('-created_at')
    )
    context = {
        'workouts': workouts
    }
    return render(request, 'exercises/workout_list.html', context)

def workout_detail(request, slug):
    workout = get_visible_workout_or_404(request.user, slug)
    workout_exercises = workout.exercises.select_related('exercise').all()

    context = {
        'workout': workout,
        'workout_exercises': workout_exercises
    }
    return render(request, 'exercises/workout_detail.html', context)

@login_required
def workout_session(request, slug):
    workout = get_visible_workout_or_404(request.user, slug)
    planned_session = None
    raw_planned_session_id = request.GET.get('planned_session')
    if raw_planned_session_id:
        try:
            planned_session = PlannedSession.objects.select_related('plan').get(
                pk=int(raw_planned_session_id),
                plan__user=request.user,
                workout=workout,
                status='pending',
                readiness_checked_at__isnull=False,
            )
            if planned_session.pain_level == 'stop':
                raise PlannedSession.DoesNotExist
        except (TypeError, ValueError, PlannedSession.DoesNotExist):
            raise Http404
    # Get all exercises ordered
    workout_exercises = workout.exercises.select_related('exercise').all().order_by('order')

    session_steps = []
    for item in workout_exercises:
        progression = recommend_exercise_progression(request.user, item.exercise)
        suggested_weight = progression['suggested_weight']
        session_steps.append({
            'item': item,
            'progression': progression,
            'prefill_weight': f'{suggested_weight:g}' if suggested_weight is not None else '',
            'prefill_reps': (
                str(progression['last_reps'])
                if progression['last_reps'] is not None else ''
            ),
        })

    # Prefill del peso en el formulario de guardado: el de la última sesión.
    last_weight = (
        WorkoutLog.objects.filter(user=request.user, kettlebell_weight__isnull=False)
        .values_list('kettlebell_weight', flat=True)
        .first()
    )

    context = {
        'workout': workout,
        'workout_exercises': workout_exercises,
        'session_steps': session_steps,
        'last_weight': f'{float(last_weight):g}' if last_weight is not None else '',
        'planned_session': planned_session,
    }
    return render(request, 'exercises/session_player.html', context)

WEEKLY_CHART_WEEKS = 8


def compute_streak_days(log_dates, today):
    """Días consecutivos con al menos una sesión, terminando hoy o ayer."""
    dates = set(log_dates)
    current = today if today in dates else today - timedelta(days=1)
    streak = 0
    while current in dates:
        streak += 1
        current -= timedelta(days=1)
    return streak


def build_weekly_chart(log_dates, today):
    """Sesiones por semana (lunes a domingo) de las últimas WEEKLY_CHART_WEEKS."""
    this_monday = today - timedelta(days=today.weekday())
    weeks = []
    for offset in range(WEEKLY_CHART_WEEKS - 1, -1, -1):
        start = this_monday - timedelta(weeks=offset)
        end = start + timedelta(days=7)
        count = sum(1 for d in log_dates if start <= d < end)
        weeks.append({'label': start.strftime('%d/%m'), 'count': count})
    max_count = max((week['count'] for week in weeks), default=0)
    for week in weeks:
        week['pct'] = round(week['count'] * 100 / max_count) if max_count else 0
    return weeks


def build_rpe_chart(logs, today):
    """RPE promedio por semana de las últimas 8 semanas."""
    this_monday = today - timedelta(days=today.weekday())
    weeks = []
    for offset in range(WEEKLY_CHART_WEEKS - 1, -1, -1):
        start = this_monday - timedelta(weeks=offset)
        end = start + timedelta(days=7)
        week_rpes = list(
            logs.filter(
                completed_at__date__gte=start,
                completed_at__date__lt=end,
                rpe__isnull=False,
            ).values_list('rpe', flat=True)
        )
        avg = round(sum(week_rpes) / len(week_rpes), 1) if week_rpes else None
        weeks.append({'label': start.strftime('%d/%m'), 'avg': avg})
    # Calcular pct relativo a escala 1-10 para la barra
    for week in weeks:
        week['pct'] = round(week['avg'] * 10) if week['avg'] else 0
    return weeks


def compute_personal_records(logs, log_dates, today):
    """Récords personales del usuario."""
    prs = {}

    # Peso más alto usado
    max_weight = logs.filter(kettlebell_weight__isnull=False).aggregate(
        max_w=Max('kettlebell_weight')
    )['max_w']
    if max_weight is not None:
        prs['max_weight'] = float(max_weight)

    # Racha más larga (no solo la actual)
    prs['best_streak'] = _compute_best_streak(log_dates)

    # Mejor semana (más sesiones)
    prs['best_week'] = _compute_best_week(log_dates)

    # Sesión más larga
    max_duration = logs.filter(duration_minutes__isnull=False).aggregate(
        max_d=Max('duration_minutes')
    )['max_d']
    if max_duration is not None:
        prs['longest_session'] = max_duration

    return prs


def _compute_best_streak(log_dates):
    """La racha más larga de días consecutivos con al menos una sesión."""
    if not log_dates:
        return 0
    sorted_dates = sorted(set(log_dates))
    best = 1
    current = 1
    for i in range(1, len(sorted_dates)):
        if (sorted_dates[i] - sorted_dates[i - 1]).days == 1:
            current += 1
            best = max(best, current)
        else:
            current = 1
    return best


def _compute_best_week(log_dates):
    """La semana (lun-dom) con más sesiones."""
    if not log_dates:
        return 0
    week_counts = {}
    for d in log_dates:
        monday = d - timedelta(days=d.weekday())
        week_counts[monday] = week_counts.get(monday, 0) + 1
    return max(week_counts.values())


def compute_suggested_weight(user, exercise_progress=None):
    """Return the dashboard weight without mixing aggregate and exercise data."""
    if exercise_progress is None:
        exercise_progress = build_dashboard_exercise_progress(user)
    if exercise_progress:
        # The most recent exercise owns the recommendation. In particular, do
        # not replace a safe ``None`` (for example after a hard session with no
        # lighter inventory) with an unrelated aggregate workout weight.
        return exercise_progress[0]['suggested_weight']

    # Without detailed history, use only the profile as a neutral starting point.
    profile = UserProfile.objects.filter(user=user).first()
    if profile:
        weights = profile.weights_list()
        if weights:
            level_index = {'beginner': 0, 'intermediate': len(weights) // 2, 'advanced': len(weights) - 1}
            idx = level_index.get(profile.level, len(weights) // 2)
            return weights[idx]
    return None


@login_required
def dashboard(request):
    logs = WorkoutLog.objects.filter(user=request.user)
    recent_logs = logs.select_related('workout')[:5]
    favorites = Favorite.objects.filter(user=request.user).select_related('exercise')
    favorite_exercises = [f.exercise for f in favorites]
    my_workouts = Workout.objects.filter(
        created_by=request.user,
        is_plan_managed=False,
    ).order_by('-created_at')

    open_plan = get_open_plan(request.user)
    next_session = next_planned_session(open_plan) if open_plan else None

    today = timezone.localdate()
    log_dates = [timezone.localtime(dt).date() for dt in logs.values_list('completed_at', flat=True)]
    week_ago = today - timedelta(days=6)

    stats = logs.aggregate(total_minutes=Sum('duration_minutes'), avg_rpe=Avg('rpe'))

    exercise_progress = build_dashboard_exercise_progress(request.user)
    suggested_weight = compute_suggested_weight(request.user, exercise_progress)
    suggested_weight_exercise = (
        exercise_progress[0]['exercise']
        if exercise_progress and suggested_weight is not None
        else None
    )

    context = {
        'recent_logs': recent_logs,
        'favorite_exercises': favorite_exercises,
        'total_workouts': len(log_dates),
        'my_workouts': my_workouts,
        'sessions_this_week': sum(1 for d in log_dates if d >= week_ago),
        'streak_days': compute_streak_days(log_dates, today),
        'total_minutes': stats['total_minutes'] or 0,
        'avg_rpe': round(stats['avg_rpe'], 1) if stats['avg_rpe'] is not None else None,
        'weekly_chart': build_weekly_chart(log_dates, today),
        'rpe_chart': build_rpe_chart(logs, today),
        'personal_records': compute_personal_records(logs, log_dates, today),
        'suggested_weight': suggested_weight,
        'suggested_weight_exercise': suggested_weight_exercise,
        'exercise_progress': exercise_progress,
        'open_plan': open_plan,
        'plan_progress': plan_progress(open_plan) if open_plan else None,
        'next_planned_session': next_session,
        'show_plan_invite': not open_plan and not UserProfile.objects.filter(
            user=request.user,
            plan_prompt_dismissed_at__isnull=False,
        ).exists(),
        'vapid_public_key': django_settings.VAPID_PUBLIC_KEY,
    }
    return render(request, 'exercises/dashboard.html', context)


@login_required
def progress_overview(request):
    """Private history list and goal-aware progress review."""
    filters = parse_history_filters(request.GET)
    page = paginate_history(
        history_queryset(request.user, filters),
        request.GET.get('page'),
    )
    context = progress_context(
        request.user,
        page,
        filters,
        plan=get_open_plan(request.user),
    )
    return render(request, 'exercises/progress_overview.html', context)


def _get_user_history_log(user, log_id, for_update=False):
    queryset = user_log_queryset(user)
    if for_update:
        queryset = queryset.select_for_update(of=('self',))
    return get_object_or_404(queryset, pk=log_id)


@login_required
def progress_session_detail(request, log_id):
    """Show one completed session and its exercise-level results."""
    log = _get_user_history_log(request.user, log_id)
    return render(request, 'exercises/progress_session_detail.html', detail_context(log))


@login_required
def progress_session_edit(request, log_id):
    """Correct a completed session without changing its identity or date."""
    if request.method == 'POST':
        with transaction.atomic():
            log = _get_user_history_log(request.user, log_id, for_update=True)
            performances = ExercisePerformance.objects.filter(
                workout_log=log,
                user=request.user,
            ).select_related(
                'exercise',
                'workout_exercise',
            )
            has_details = performances.exists()
            log_form = WorkoutLogEditForm(
                request.POST,
                instance=log,
                has_details=has_details,
            )
            performance_formset = ExercisePerformanceEditFormSet(
                request.POST,
                queryset=performances,
                prefix='performances',
            )
            if log_form.is_valid() and performance_formset.is_valid():
                edited_log = log_form.save(commit=False)
                if has_details:
                    # Detailed weights are canonical; retain an aggregate for
                    # old dashboard/export consumers without mixing exercises.
                    for form in performance_formset:
                        form.save()
                    detail_weights = list(
                        ExercisePerformance.objects.filter(workout_log=log)
                        .exclude(weight__isnull=True)
                        .values_list('weight', flat=True)
                    )
                    edited_log.kettlebell_weight = max(detail_weights) if detail_weights else None
                edited_log.edited_at = timezone.now()
                edited_log.save()
                messages.success(request, 'Sesión actualizada. Tu progreso ya usa estos datos.')
                return redirect('exercises:progress_session_detail', log_id=log.id)
    else:
        log = _get_user_history_log(request.user, log_id)
        performances = ExercisePerformance.objects.filter(
            workout_log=log,
            user=request.user,
        ).select_related(
            'exercise',
            'workout_exercise',
        )
        has_details = performances.exists()
        log_form = WorkoutLogEditForm(instance=log, has_details=has_details)
        performance_formset = ExercisePerformanceEditFormSet(
            queryset=performances,
            prefix='performances',
        )

    return render(request, 'exercises/progress_session_edit.html', {
        **detail_context(log),
        'log_form': log_form,
        'performance_formset': performance_formset,
        'has_details': has_details,
    })


def _complete_plan_if_ready(plan):
    if plan.status == 'active' and not plan.sessions.filter(status='pending').exists():
        plan.status = 'completed'
        plan.completed_at = timezone.now()
        plan.save(update_fields=['status', 'completed_at', 'updated_at'])
        return True
    return False


@login_required
def plan_overview(request):
    plan = get_open_plan(request.user)
    if plan is None:
        latest_plan = TrainingPlan.objects.filter(user=request.user).order_by('-created_at').first()
        if latest_plan:
            return redirect('exercises:plan_detail', plan_id=latest_plan.id)
        return redirect('exercises:plan_create')
    return _render_plan_detail(request, plan)


@login_required
def plan_detail(request, plan_id):
    plan = get_object_or_404(TrainingPlan, pk=plan_id, user=request.user)
    return _render_plan_detail(request, plan)


def _render_plan_detail(
    request,
    plan,
    readiness_session=None,
    readiness_form=None,
    readiness_regenerate=False,
):
    sessions = list(plan.sessions.select_related('workout').order_by('scheduled_date', 'sequence'))
    today = timezone.localdate()
    for session in sessions:
        session.is_today = session.scheduled_date == today and session.status == 'pending'
        session.is_overdue_display = session.scheduled_date < today and session.status == 'pending'
    return render(request, 'exercises/plan_overview.html', {
        'plan': plan,
        'sessions': sessions,
        'plan_progress': plan_progress(plan),
        'next_planned_session': next_planned_session(plan, today),
        'plan_summary': plan_summary(request.user, plan),
        'today': today,
        'readiness_session': readiness_session,
        'readiness_form': readiness_form,
        'readiness_regenerate': readiness_regenerate,
    })


@login_required
def plan_create(request):
    if get_open_plan(request.user):
        return redirect('exercises:plan_overview')
    profile, _ = UserProfile.objects.get_or_create(user=request.user)
    if request.method == 'POST':
        form = TrainingPlanForm(request.POST, profile=profile)
        if form.is_valid():
            plan, created = create_training_plan(request.user, form.cleaned_data)
            if created:
                messages.success(request, 'Tu plan de cuatro semanas está listo.')
            return redirect('exercises:plan_detail', plan_id=plan.id)
    else:
        form = TrainingPlanForm(profile=profile)
    return render(request, 'exercises/plan_form.html', {
        'form': form,
        'welcome': request.GET.get('welcome') == '1',
    })


@login_required
@require_POST
def dismiss_plan_invite(request):
    profile, _ = UserProfile.objects.get_or_create(user=request.user)
    profile.plan_prompt_dismissed_at = timezone.now()
    profile.save(update_fields=['plan_prompt_dismissed_at', 'updated_at'])
    return redirect('exercises:dashboard')


@login_required
@require_POST
@rate_limit('plan-prepare', max_requests=20, window_seconds=60)
def prepare_plan_session_view(request, session_id):
    session = get_object_or_404(
        PlannedSession.objects.select_related('plan'),
        pk=session_id,
        plan__user=request.user,
    )
    form = SessionReadinessForm(
        request.POST or None,
        initial={
            'energy_level': session.energy_level or 3,
            'pain_level': session.pain_level or 'none',
            'available_minutes': session.available_minutes or session.estimated_duration,
        },
    )
    if not form.is_valid():
        return _render_plan_detail(
            request,
            session.plan,
            readiness_session=session,
            readiness_form=form,
            readiness_regenerate=request.POST.get('regenerate') == '1',
        )
    try:
        session = prepare_planned_session(
            request.user,
            session,
            regenerate=request.POST.get('regenerate') == '1',
            readiness=form.cleaned_data,
        )
    except ValueError as exc:
        messages.error(request, str(exc))
        return redirect('exercises:plan_detail', plan_id=session.plan_id)
    if session.pain_level == 'stop' or not session.workout_id:
        messages.warning(
            request,
            'No se generó la sesión porque indicaste dolor. Puedes reprogramarla u omitirla; '
            'si persiste, busca orientación profesional.',
        )
        return redirect('exercises:plan_detail', plan_id=session.plan_id)
    url = reverse('exercises:workout_session', kwargs={'slug': session.workout.slug})
    return redirect(f'{url}?planned_session={session.id}')


@login_required
@require_POST
def reschedule_plan_session(request, session_id):
    session = get_object_or_404(
        PlannedSession.objects.select_related('plan'),
        pk=session_id,
        plan__user=request.user,
    )
    if session.status != 'pending' or session.plan.status != 'active':
        messages.error(request, 'Solo puedes reprogramar sesiones pendientes de un plan activo.')
        return redirect('exercises:plan_detail', plan_id=session.plan_id)
    try:
        target_date = date.fromisoformat(request.POST.get('scheduled_date', ''))
    except (TypeError, ValueError):
        messages.error(request, 'La fecha elegida no es válida.')
        return redirect('exercises:plan_detail', plan_id=session.plan_id)
    if not session.plan.start_date <= target_date <= session.plan.end_date:
        messages.error(request, 'La fecha debe estar dentro de las cuatro semanas del plan.')
        return redirect('exercises:plan_detail', plan_id=session.plan_id)
    collision = session.plan.sessions.filter(scheduled_date=target_date).exclude(pk=session.pk).exists()
    if collision:
        messages.error(request, 'Ya existe otra sesión en esa fecha.')
        return redirect('exercises:plan_detail', plan_id=session.plan_id)
    session.scheduled_date = target_date
    session.reminder_sent_at = None
    session.save(update_fields=['scheduled_date', 'reminder_sent_at', 'updated_at'])
    messages.success(request, 'Sesión reprogramada; tu racha no se verá afectada.')
    return redirect('exercises:plan_detail', plan_id=session.plan_id)


@login_required
@require_POST
def skip_plan_session(request, session_id):
    session = get_object_or_404(PlannedSession, pk=session_id, plan__user=request.user)
    if session.status == 'pending' and session.plan.status == 'active':
        session.status = 'skipped'
        session.save(update_fields=['status', 'updated_at'])
        _complete_plan_if_ready(session.plan)
        messages.info(request, 'Sesión marcada como omitida.')
    return redirect('exercises:plan_detail', plan_id=session.plan_id)


@login_required
@require_POST
def toggle_plan_pause(request, plan_id):
    plan = get_object_or_404(TrainingPlan, pk=plan_id, user=request.user)
    if plan.status == 'active':
        plan.status = 'paused'
        message = 'Plan pausado. No se enviarán recordatorios mientras esté detenido.'
    elif plan.status == 'paused':
        plan.status = 'active'
        message = 'Plan reanudado.'
    else:
        messages.error(request, 'Este plan ya no se puede pausar o reanudar.')
        return redirect('exercises:plan_detail', plan_id=plan.id)
    plan.save(update_fields=['status', 'updated_at'])
    messages.success(request, message)
    return redirect('exercises:plan_detail', plan_id=plan.id)


@login_required
@require_POST
def cancel_plan(request, plan_id):
    plan = get_object_or_404(TrainingPlan, pk=plan_id, user=request.user)
    if plan.status in ('active', 'paused'):
        plan.status = 'cancelled'
        plan.save(update_fields=['status', 'updated_at'])
        plan.sessions.filter(status='pending').update(status='skipped', updated_at=timezone.now())
        messages.info(request, 'Plan cancelado. Tu historial de sesiones se conserva.')
    return redirect('exercises:plan_detail', plan_id=plan.id)

def _optional_int(data, key, minimum, maximum):
    """Entero opcional del payload: (ok, valor). None/ausente es válido."""
    raw = (data or {}).get(key)
    if raw is None:
        return True, None
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return False, None
    if not minimum <= value <= maximum:
        return False, None
    return True, value


def _parse_exercise_performance_payload(data, workout):
    """Validate and normalize detailed metrics for the selected workout."""
    raw_logs = data.get('exercise_logs')
    if raw_logs is None:
        return True, []
    if not isinstance(raw_logs, list) or len(raw_logs) > 100:
        return False, 'El registro por ejercicio no es válido.'

    workout_exercises = {
        item.id: item
        for item in workout.exercises.select_related('exercise').all()
    }
    seen_ids = set()
    parsed = []
    for row in raw_logs:
        if not isinstance(row, dict):
            return False, 'Cada registro de ejercicio debe ser un objeto.'

        raw_workout_exercise_id = row.get('workout_exercise_id')
        if isinstance(raw_workout_exercise_id, bool):
            return False, 'El ejercicio indicado no es válido.'
        try:
            workout_exercise_id = int(raw_workout_exercise_id)
        except (TypeError, ValueError):
            return False, 'El ejercicio indicado no es válido.'
        if workout_exercise_id not in workout_exercises:
            return False, 'El ejercicio no pertenece a esta rutina.'
        if workout_exercise_id in seen_ids:
            return False, 'No se puede registrar dos veces el mismo ejercicio.'
        seen_ids.add(workout_exercise_id)

        completed = row.get('completed', True)
        if type(completed) is not bool:
            return False, 'El estado de completado no es válido.'

        sets_ok, sets_completed = _optional_int(row, 'sets_completed', 0, 100)
        reps_ok, reps_completed = _optional_int(row, 'reps_completed', 0, 1000)
        rpe_ok, exercise_rpe = _optional_int(row, 'rpe', 1, 10)

        raw_weight = row.get('weight', row.get('kettlebell_weight'))
        weight = None
        weight_ok = True
        if raw_weight is not None and raw_weight != '':
            try:
                weight = Decimal(str(raw_weight))
                weight_ok = Decimal('0.1') <= weight <= Decimal('200')
            except (InvalidOperation, ValueError):
                weight_ok = False

        notes = row.get('notes') or ''
        notes_ok = isinstance(notes, str) and len(notes) <= 300
        if not (sets_ok and reps_ok and rpe_ok and weight_ok and notes_ok):
            return False, 'Las métricas de un ejercicio no son válidas.'

        parsed.append({
            'workout_exercise': workout_exercises[workout_exercise_id],
            'completed': completed,
            'sets_completed': sets_completed or 0,
            'reps_completed': reps_completed,
            'weight': weight,
            'rpe': exercise_rpe,
            'notes': notes.strip(),
        })
    return True, parsed


def _validate_planned_session_weights(user, planned_session, aggregate_weight, exercise_logs):
    """Keep plan-session weights inside the inventory declared by the profile."""
    if planned_session is None:
        return None
    profile = UserProfile.objects.filter(user=user).first()
    allowed = {
        Decimal(str(value))
        for value in (profile.weights_list() if profile else [])
    }
    if not allowed:
        return None
    candidates = [aggregate_weight]
    candidates.extend(item['weight'] for item in exercise_logs)
    outside = next((value for value in candidates if value is not None and value not in allowed), None)
    if outside is not None:
        return 'El peso indicado no está en tu inventario del plan.'
    return None


@login_required
def profile_view(request):
    profile, _ = UserProfile.objects.get_or_create(user=request.user)
    if request.method == 'POST':
        form = UserProfileForm(request.POST, instance=profile)
        if form.is_valid():
            form.save()
            messages.success(request, 'Perfil actualizado.')
            return redirect('exercises:profile')
    else:
        form = UserProfileForm(instance=profile)
    return render(request, 'exercises/profile.html', {'form': form})


@login_required
@require_POST
@rate_limit('log-workout', max_requests=10, window_seconds=60)
def log_workout(request):
    data = parse_json_body(request)
    if data is None:
        return JsonResponse({'status': 'error', 'message': 'Petición inválida'}, status=400)
    try:
        workout_id = int(data.get('workout_id'))
    except (TypeError, ValueError):
        return JsonResponse({'status': 'error', 'message': 'Petición inválida'}, status=400)

    duration_ok, duration = _optional_int(data, 'duration_minutes', 1, 600)
    rpe_ok, rpe = _optional_int(data, 'rpe', 1, 10)

    weight = data.get('kettlebell_weight')
    weight_ok = True
    if weight is not None:
        try:
            weight = Decimal(str(weight))
            weight_ok = Decimal('1') <= weight <= Decimal('200')
        except InvalidOperation:
            weight_ok = False

    notes = data.get('notes') or ''
    notes_ok = isinstance(notes, str) and len(notes) <= 300

    if not (duration_ok and rpe_ok and weight_ok and notes_ok):
        return JsonResponse({'status': 'error', 'message': 'Métricas inválidas'}, status=400)

    workout = get_object_or_404(get_visible_workouts(request.user), id=workout_id)
    planned_session = None
    raw_planned_session_id = data.get('planned_session_id')
    if raw_planned_session_id not in (None, ''):
        try:
            planned_session = PlannedSession.objects.select_related('plan').get(
                pk=int(raw_planned_session_id),
                plan__user=request.user,
            )
        except (TypeError, ValueError, PlannedSession.DoesNotExist):
            return JsonResponse({'status': 'error', 'message': 'La sesión planificada no es válida.'}, status=400)
        if planned_session.workout_id != workout.id:
            return JsonResponse({'status': 'error', 'message': 'La rutina no corresponde al plan.'}, status=409)
        if planned_session.plan.status != 'active':
            return JsonResponse({'status': 'error', 'message': 'El plan no está activo.'}, status=409)
        if not planned_session.readiness_checked_at:
            return JsonResponse({'status': 'error', 'message': 'Completa el chequeo de preparación antes de guardar.'}, status=409)
        if planned_session.pain_level == 'stop':
            return JsonResponse({'status': 'error', 'message': 'La sesión está detenida por dolor.'}, status=409)
        if planned_session.status != 'pending':
            existing_for_plan = WorkoutLog.objects.filter(planned_session=planned_session).first()
            if existing_for_plan:
                return JsonResponse({
                    'status': 'success',
                    'created': False,
                    'log_id': existing_for_plan.id,
                    'performance_count': existing_for_plan.exercise_performances.count(),
                })
            return JsonResponse({'status': 'error', 'message': 'La sesión ya no está pendiente.'}, status=409)
    raw_client_session_id = data.get('client_session_id')
    client_session_id = None
    if raw_client_session_id not in (None, ''):
        try:
            client_session_id = uuid.UUID(str(raw_client_session_id))
        except (ValueError, AttributeError):
            return JsonResponse(
                {'status': 'error', 'message': 'El identificador de sesión no es válido.'},
                status=400,
            )

    if client_session_id:
        existing_log = WorkoutLog.objects.filter(
            user=request.user,
            client_session_id=client_session_id,
        ).first()
        if existing_log:
            if existing_log.workout_id not in (None, workout.id):
                return JsonResponse(
                    {'status': 'error', 'message': 'El identificador de sesión ya pertenece a otra rutina.'},
                    status=409,
                )
            if planned_session and existing_log.planned_session_id not in (None, planned_session.id):
                return JsonResponse(
                    {'status': 'error', 'message': 'El identificador de sesión ya pertenece a otro plan.'},
                    status=409,
                )
            return JsonResponse({
                'status': 'success',
                'created': False,
                'log_id': existing_log.id,
                'performance_count': existing_log.exercise_performances.count(),
            })

    valid_details, exercise_logs = _parse_exercise_performance_payload(data, workout)
    if not valid_details:
        return JsonResponse({'status': 'error', 'message': exercise_logs}, status=400)

    inventory_error = _validate_planned_session_weights(
        request.user,
        planned_session,
        weight,
        exercise_logs,
    )
    if inventory_error:
        return JsonResponse({'status': 'error', 'message': inventory_error}, status=400)

    if weight is None:
        detail_weights = [item['weight'] for item in exercise_logs if item['weight'] is not None]
        if detail_weights and len(set(detail_weights)) == 1:
            weight = detail_weights[0]
    if rpe is None:
        detail_rpes = [item['rpe'] for item in exercise_logs if item['rpe'] is not None]
        if detail_rpes:
            rpe = round(sum(detail_rpes) / len(detail_rpes))

    with transaction.atomic():
        defaults = {
            'workout': workout,
            'planned_session': planned_session,
            'workout_title_snapshot': workout.title,
            'workout_difficulty_snapshot': workout.difficulty,
            'workout_duration_snapshot': workout.estimated_duration,
            'duration_minutes': duration,
            'kettlebell_weight': weight,
            'rpe': rpe,
            'notes': notes.strip(),
        }
        if client_session_id:
            workout_log, created = WorkoutLog.objects.get_or_create(
                user=request.user,
                client_session_id=client_session_id,
                defaults=defaults,
            )
            if not created:
                if workout_log.workout_id not in (None, workout.id):
                    return JsonResponse(
                        {'status': 'error', 'message': 'El identificador de sesión ya pertenece a otra rutina.'},
                        status=409,
                    )
                if planned_session and workout_log.planned_session_id not in (None, planned_session.id):
                    return JsonResponse(
                        {'status': 'error', 'message': 'El identificador de sesión ya pertenece a otro plan.'},
                        status=409,
                    )
                return JsonResponse({
                    'status': 'success',
                    'created': False,
                    'log_id': workout_log.id,
                    'performance_count': workout_log.exercise_performances.count(),
                })
        else:
            workout_log = WorkoutLog.objects.create(user=request.user, **defaults)
            created = True

        ExercisePerformance.objects.bulk_create([
            ExercisePerformance(
                user=request.user,
                workout_log=workout_log,
                workout_exercise=item['workout_exercise'],
                exercise=item['workout_exercise'].exercise,
                completed=item['completed'],
                sets_completed=item['sets_completed'],
                reps_completed=item['reps_completed'],
                weight=item['weight'],
                rpe=item['rpe'],
                notes=item['notes'],
                exercise_name_snapshot=item['workout_exercise'].exercise.name,
                exercise_category_snapshot=item['workout_exercise'].exercise.category,
                target_sets=item['workout_exercise'].sets,
                target_reps=item['workout_exercise'].reps,
            )
            for item in exercise_logs
        ])
        if planned_session:
            planned_session.status = 'completed'
            planned_session.completed_at = timezone.now()
            planned_session.save(update_fields=['status', 'completed_at', 'updated_at'])
            _complete_plan_if_ready(planned_session.plan)

    # Push notification: felicitación + check de PRs
    if created:
        _send_post_workout_push(request.user, workout.title, weight, log_id=workout_log.id)

    return JsonResponse({
        'status': 'success',
        'created': created,
        'log_id': workout_log.id,
        'performance_count': len(exercise_logs),
    })


def _send_post_workout_push(user, workout_title, weight_used, log_id=None):
    """Send push after workout: congratulate + check for new PRs."""
    from .push_utils import send_new_pr_push, send_workout_completed_push

    today = timezone.localdate()
    all_logs = WorkoutLog.objects.filter(user=user)
    log_dates = list(
        all_logs
        .values_list('completed_at', flat=True)
    )
    log_dates = [timezone.localtime(dt).date() for dt in log_dates]
    streak = compute_streak_days(log_dates, today)

    send_workout_completed_push(
        user,
        workout_title=workout_title,
        streak=streak,
        weight=float(weight_used) if weight_used else None,
    )

    # Check for new weight PR
    if weight_used:
        previous_max = (
            all_logs.filter(kettlebell_weight__isnull=False)
            .exclude(pk=log_id)
            .aggregate(m=Max('kettlebell_weight'))['m']
        )
        if previous_max is None or weight_used > previous_max:
            send_new_pr_push(user, 'weight', float(weight_used))

    # Check for new streak PR
    historical_dates = list(
        all_logs.exclude(pk=log_id).values_list('completed_at', flat=True)
    )
    historical_dates = [timezone.localtime(dt).date() for dt in historical_dates]
    best_streak = _compute_best_streak(historical_dates)
    if streak > 1 and streak > best_streak:
        send_new_pr_push(user, 'streak', streak)

@login_required
def create_workout(request):
    if request.method == 'POST':
        form = WorkoutForm(request.POST)
        formset = WorkoutExerciseFormSet(request.POST)

        if form.is_valid() and formset.is_valid():
            workout = form.save(commit=False)
            workout.created_by = request.user
            workout.save()
            
            instances = formset.save(commit=False)
            for instance in instances:
                instance.workout = workout
                instance.save()

            messages.success(request, 'Rutina creada correctamente.')
            return redirect('exercises:workout_detail', slug=workout.slug)
    else:
        form = WorkoutForm()
        formset = WorkoutExerciseFormSet()

    return render(request, 'exercises/workout_form.html', {
        'form': form,
        'formset': formset,
        'page_heading': 'Crear Nueva Rutina',
        'page_subtitle': 'Diseña tu entrenamiento personalizado.',
    })


@login_required
def edit_workout(request, slug):
    workout = get_object_or_404(Workout, slug=slug, created_by=request.user)
    if workout.is_plan_managed:
        messages.error(request, 'Las rutinas de un plan solo se pueden regenerar desde el calendario.')
        return redirect('exercises:workout_detail', slug=workout.slug)

    if request.method == 'POST':
        form = WorkoutForm(request.POST, instance=workout)
        formset = WorkoutExerciseFormSet(request.POST, instance=workout)

        if form.is_valid() and formset.is_valid():
            form.save()
            formset.save()
            messages.success(request, 'Rutina actualizada correctamente.')
            return redirect('exercises:workout_detail', slug=workout.slug)
    else:
        form = WorkoutForm(instance=workout)
        formset = WorkoutExerciseFormSet(instance=workout)

    return render(request, 'exercises/workout_form.html', {
        'form': form,
        'formset': formset,
        'workout': workout,
        'page_heading': 'Editar Rutina',
        'page_subtitle': f'Modifica los datos de "{workout.title}".',
    })


@login_required
@require_POST
def delete_workout(request, slug):
    workout = get_object_or_404(Workout, slug=slug, created_by=request.user)
    if workout.is_plan_managed:
        messages.error(request, 'Las rutinas de un plan se gestionan desde el calendario.')
        return redirect('exercises:workout_list')
    title = workout.title
    workout.delete()
    messages.success(request, f'Rutina "{title}" eliminada.')
    return redirect('exercises:workout_list')

VALID_FOCUS_OPTIONS = {'strength', 'cardio', 'flexibility', 'full_body', 'mix'}
VALID_DIFFICULTY_OPTIONS = {value for value, _ in Exercise.DIFFICULTY_CHOICES}


def _generate_routine_defaults(user):
    """Preselección del formulario según el perfil del usuario (si existe)."""
    profile = UserProfile.objects.filter(user=user).first()
    return {
        'default_difficulty': profile.level if profile else 'intermediate',
        'default_focus': profile.focus if profile else 'mix',
    }


@login_required
def generate_routine_view(request):
    if request.method == 'POST':
        difficulty = request.POST.get('difficulty', 'intermediate')
        focus = request.POST.get('focus', 'mix')

        try:
            duration = int(request.POST.get('duration', 30))
        except (TypeError, ValueError):
            duration = 0

        if (
            not 10 <= duration <= 120
            or difficulty not in VALID_DIFFICULTY_OPTIONS
            or focus not in VALID_FOCUS_OPTIONS
        ):
            messages.error(request, 'Los datos del formulario no son válidos. Revisa la duración, el nivel y el enfoque.')
            return render(request, 'exercises/generate_routine.html', _generate_routine_defaults(request.user))

        try:
            generator = RoutineGenerator(
                user=request.user,
                duration_minutes=duration,
                difficulty=difficulty,
                focus=focus
            )
            workout = generator.generate()
            return redirect('exercises:workout_detail', slug=workout.slug)
        except Exception:
            logger.exception("Error generando la rutina")
            messages.error(request, 'No se pudo generar la rutina. Inténtalo de nuevo.')

    return render(request, 'exercises/generate_routine.html', _generate_routine_defaults(request.user))


@login_required
@require_POST
@rate_limit('push-sub', max_requests=5, window_seconds=60)
def save_push_subscription(request):
    """Guardar o actualizar una suscripcion push del navegador."""
    try:
        data = json.loads(request.body)
        endpoint = data.get('endpoint', '')
        keys = data.get('keys', {})
        p256dh = keys.get('p256dh', '')
        auth = keys.get('auth', '')

        if not endpoint or not p256dh or not auth:
            return JsonResponse({'status': 'error', 'message': 'Datos incompletos'}, status=400)

        subscription, created = PushSubscription.objects.update_or_create(
            user=request.user,
            endpoint=endpoint,
            defaults={'p256dh': p256dh, 'auth': auth},
        )
        return JsonResponse({'status': 'success', 'created': created})
    except (json.JSONDecodeError, KeyError) as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=400)


@login_required
@require_POST
@rate_limit('push-remove', max_requests=5, window_seconds=60)
def remove_push_subscription(request):
    """Eliminar una suscripcion push."""
    try:
        data = json.loads(request.body)
        endpoint = data.get('endpoint', '')
        PushSubscription.objects.filter(user=request.user, endpoint=endpoint).delete()
        return JsonResponse({'status': 'success'})
    except json.JSONDecodeError:
        return JsonResponse({'status': 'error', 'message': 'JSON invalido'}, status=400)


@login_required
@require_POST
@rate_limit('push-test', max_requests=3, window_seconds=60)
def send_test_notification(request):
    """Envía una notificación de prueba al usuario actual."""
    from .push_utils import send_push_to_user

    if not django_settings.VAPID_PRIVATE_KEY:
        return JsonResponse(
            {'status': 'error', 'message': 'VAPID no configurado'}, status=500
        )

    if not PushSubscription.objects.filter(user=request.user).exists():
        return JsonResponse(
            {'status': 'error', 'message': 'No tienes suscripciones push activas'}, status=400
        )

    sent = send_push_to_user(request.user, {
        'title': '¡KettleBell Pro! 🔔',
        'body': 'Las notificaciones están funcionando correctamente.',
        'url': '/dashboard/',
    })

    return JsonResponse({'status': 'success', 'sent': sent})


@rate_limit('autocomplete', max_requests=60, window_seconds=60)
def exercise_autocomplete(request):
    """Devuelve sugerencias de autocompletado para el buscador."""
    q = request.GET.get('q', '').strip()
    if len(q) < 2:
        return JsonResponse({'suggestions': []})

    exercises = Exercise.objects.filter(
        Q(name__icontains=q) | Q(muscles_targeted__icontains=q)
    ).values('name', 'slug', 'category', 'difficulty')[:8]

    suggestions = [
        {
            'name': ex['name'],
            'slug': ex['slug'],
            'category': dict(Exercise.CATEGORY_CHOICES).get(ex['category'], ex['category']),
            'difficulty': dict(Exercise.DIFFICULTY_CHOICES).get(ex['difficulty'], ex['difficulty']),
        }
        for ex in exercises
    ]
    return JsonResponse({'suggestions': suggestions})


@rate_limit('exercise-filters', max_requests=60, window_seconds=60)
def exercise_filters(request):
    """Devuelve los valores únicos de músculos para el filtro."""
    muscles = (
        Exercise.objects.exclude(muscles_targeted='')
        .values_list('muscles_targeted', flat=True)
    )
    muscle_set = set()
    for text in muscles:
        for part in text.replace('\n', ',').split(','):
            part = part.strip()
            if part:
                muscle_set.add(part)

    return JsonResponse({
        'muscles': sorted(muscle_set),
        'categories': list(Exercise.CATEGORY_CHOICES),
        'difficulties': list(Exercise.DIFFICULTY_CHOICES),
    })


def workout_export(request, slug):
    """Devuelve JSON con los datos de la rutina para generar imagen compartible."""
    workout = get_visible_workout_or_404(request.user, slug)
    exercises = workout.exercises.select_related('exercise').order_by('order')

    return JsonResponse({
        'title': workout.title,
        'description': workout.description,
        'difficulty': workout.difficulty,
        'duration': workout.estimated_duration,
        'slug': workout.slug,
        'exercises': [
            {
                'name': item.exercise.name,
                'sets': item.sets,
                'reps': item.reps,
                'notes': item.notes or '',
            }
            for item in exercises
        ],
    })
