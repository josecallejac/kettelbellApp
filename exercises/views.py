import json
import logging
import time
from datetime import timedelta
from decimal import Decimal, InvalidOperation
from functools import wraps

from django.conf import settings as django_settings
from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.core.paginator import Paginator
from django.db.models import Avg, Count, Max, Q, Sum
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from .forms import (
    CustomAuthenticationForm,
    CustomUserCreationForm,
    UserProfileForm,
    WorkoutExerciseFormSet,
    WorkoutForm,
)
from .models import Exercise, Favorite, PushSubscription, UserProfile, Workout, WorkoutLog
from .utils import RoutineGenerator

logger = logging.getLogger(__name__)


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
    }

    return render(request, 'exercises/landing.html', context)

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
    return render(request, 'exercises/exercise_collection.html', context)

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
    return render(request, 'exercises/taxonomy_overview.html', {
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
    return render(request, 'exercises/exercise_collection.html', context)

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
    return render(request, 'exercises/taxonomy_overview.html', {
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
    return render(request, 'exercises/exercise_collection.html', context)

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
    # Get all exercises ordered
    workout_exercises = workout.exercises.select_related('exercise').all().order_by('order')

    # Prefill del peso en el formulario de guardado: el de la última sesión.
    last_weight = (
        WorkoutLog.objects.filter(user=request.user, kettlebell_weight__isnull=False)
        .values_list('kettlebell_weight', flat=True)
        .first()
    )

    context = {
        'workout': workout,
        'workout_exercises': workout_exercises,
        'last_weight': f'{float(last_weight):g}' if last_weight is not None else '',
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


def compute_suggested_weight(user):
    """Peso sugerido basado en el historial real de entrenamientos."""
    last_weight = (
        WorkoutLog.objects.filter(user=user, kettlebell_weight__isnull=False)
        .order_by('-completed_at')
        .values_list('kettlebell_weight', flat=True)
        .first()
    )
    if last_weight is not None:
        return float(last_weight)

    # Fallback: usar el perfil
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
    my_workouts = Workout.objects.filter(created_by=request.user).order_by('-created_at')

    today = timezone.localdate()
    log_dates = [timezone.localtime(dt).date() for dt in logs.values_list('completed_at', flat=True)]
    week_ago = today - timedelta(days=6)

    stats = logs.aggregate(total_minutes=Sum('duration_minutes'), avg_rpe=Avg('rpe'))

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
        'suggested_weight': compute_suggested_weight(request.user),
        'vapid_public_key': django_settings.VAPID_PUBLIC_KEY,
    }
    return render(request, 'exercises/dashboard.html', context)

def _optional_int(data, key, minimum, maximum):
    """Entero opcional del payload: (ok, valor). None/ausente es válido."""
    raw = data.get(key)
    if raw is None:
        return True, None
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return False, None
    if not minimum <= value <= maximum:
        return False, None
    return True, value


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
    try:
        workout_id = int((data or {}).get('workout_id'))
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
    WorkoutLog.objects.create(
        user=request.user,
        workout=workout,
        duration_minutes=duration,
        kettlebell_weight=weight,
        rpe=rpe,
        notes=notes.strip(),
    )

    return JsonResponse({'status': 'success'})

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
    from pywebpush import WebPushException, webpush
    import json as _json

    if not django_settings.VAPID_PRIVATE_KEY:
        return JsonResponse(
            {'status': 'error', 'message': 'VAPID no configurado'}, status=500
        )

    subscriptions = PushSubscription.objects.filter(user=request.user)
    if not subscriptions.exists():
        return JsonResponse(
            {'status': 'error', 'message': 'No tienes suscripciones push activas'}, status=400
        )

    payload = _json.dumps({
        'title': '¡KettleBell Pro! 🔔',
        'body': 'Las notificaciones están funcionando correctamente.',
        'url': '/dashboard/',
    })

    vapid_claims = {'sub': f'mailto:{django_settings.VAPID_ADMIN_EMAIL}'}
    sent = 0
    for sub in subscriptions:
        try:
            webpush(
                subscription_info={
                    'endpoint': sub.endpoint,
                    'keys': {'p256dh': sub.p256dh, 'auth': sub.auth},
                },
                data=payload,
                vapid_private_key=django_settings.VAPID_PRIVATE_KEY,
                vapid_claims=vapid_claims,
            )
            sent += 1
        except WebPushException:
            pass

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
    workout = get_object_or_404(Workout, slug=slug)
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
