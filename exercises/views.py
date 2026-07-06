import json
import logging

from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from .forms import (
    CustomAuthenticationForm,
    CustomUserCreationForm,
    WorkoutExerciseFormSet,
    WorkoutForm,
)
from .models import Exercise, Favorite, Workout, WorkoutLog
from .utils import RoutineGenerator

logger = logging.getLogger(__name__)

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

def logout_view(request):
    logout(request)
    return redirect('exercises:landing')

@login_required
@require_POST
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
    exercises = Exercise.objects.all()

    if search_query:
        exercises = exercises.filter(
            Q(name__icontains=search_query)
            | Q(description__icontains=search_query)
            | Q(muscles_targeted__icontains=search_query)
            | Q(equipment__icontains=search_query)
        )

    page_obj = paginate_exercises(request, exercises)

    if search_query:
        subtitle = f'Resultados para "{search_query}".'
        empty_message = f'No hay ejercicios que coincidan con "{search_query}".'
    else:
        subtitle = 'Biblioteca completa de ejercicios con kettlebell.'
        empty_message = 'No hay ejercicios disponibles todavia.'

    context = {
        'exercises': page_obj.object_list,
        'page_obj': page_obj,
        'search_query': search_query,
        'show_search': True,
        'favorites_ids': get_favorites_ids(request),
        'page_title': 'Todos los ejercicios',
        'page_subtitle': subtitle,
        'page_kicker': 'Ejercicios',
        'empty_message': empty_message,
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
    workouts = get_visible_workouts(request.user).order_by('-created_at')
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
    
    context = {
        'workout': workout,
        'workout_exercises': workout_exercises,
    }
    return render(request, 'exercises/session_player.html', context)

@login_required
def dashboard(request):
    recent_logs = WorkoutLog.objects.filter(user=request.user).select_related('workout')[:5]
    favorites = Favorite.objects.filter(user=request.user).select_related('exercise')
    favorite_exercises = [f.exercise for f in favorites]

    total_workouts = WorkoutLog.objects.filter(user=request.user).count()
    my_workouts = Workout.objects.filter(created_by=request.user).order_by('-created_at')

    context = {
        'recent_logs': recent_logs,
        'favorite_exercises': favorite_exercises,
        'total_workouts': total_workouts,
        'my_workouts': my_workouts,
    }
    return render(request, 'exercises/dashboard.html', context)

@login_required
@require_POST
def log_workout(request):
    data = parse_json_body(request)
    try:
        workout_id = int((data or {}).get('workout_id'))
    except (TypeError, ValueError):
        return JsonResponse({'status': 'error', 'message': 'Petición inválida'}, status=400)

    workout = get_object_or_404(get_visible_workouts(request.user), id=workout_id)
    WorkoutLog.objects.create(user=request.user, workout=workout)

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
            
            # Save deletions if any
            for obj in formset.deleted_objects:
                obj.delete()

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
            return render(request, 'exercises/generate_routine.html')

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

    return render(request, 'exercises/generate_routine.html')
