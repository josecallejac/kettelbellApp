from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, Http404
from django.views.decorators.http import require_POST
from django.db.models import Count
from .models import Exercise, Favorite, Workout, WorkoutLog
from .utils import RoutineGenerator
from .forms import CustomUserCreationForm, CustomAuthenticationForm
import logging

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

def register_view(request):
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
    if request.method == 'POST':
        form = CustomAuthenticationForm(data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            if 'next' in request.POST:
                return redirect(request.POST.get('next'))
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
    import json
    data = json.loads(request.body)
    exercise_id = data.get('exercise_id')
    exercise = get_object_or_404(Exercise, id=exercise_id)
    
    favorite, created = Favorite.objects.get_or_create(user=request.user, exercise=exercise)
    
    if not created:
        favorite.delete()
        is_paved = False
    else:
        is_paved = True
        
    return JsonResponse({'status': 'success', 'is_favorite': is_paved})

@login_required
def favorites_list(request):
    favorites = Favorite.objects.filter(user=request.user).select_related('exercise')
    exercises = [f.exercise for f in favorites]
    return render(request, 'exercises/favorites.html', {'exercises': exercises})

def landing_page(request):
    exercises = Exercise.objects.all()
    video_exercises = exercises.exclude(video_url__isnull=True).exclude(video_url__exact="")[:6]
    
    favorites_ids = get_favorites_ids(request)

    # Organize exercises by category
    exercises_by_category = {
        'strength': exercises.filter(category='strength'),
        'cardio': exercises.filter(category='cardio'),
        'flexibility': exercises.filter(category='flexibility'),
        'full_body': exercises.filter(category='full_body'),
    }
    
    context = {
        'exercises_by_category': exercises_by_category,
        'all_exercises': exercises,
        'favorites_ids': favorites_ids,
        'video_exercises': video_exercises,
    }
    
    return render(request, 'exercises/landing.html', context)

def exercise_list(request):
    exercises = Exercise.objects.all()
    context = {
        'exercises': exercises,
        'favorites_ids': get_favorites_ids(request),
        'page_title': 'Todos los ejercicios',
        'page_subtitle': 'Biblioteca completa de ejercicios con kettlebell.',
        'page_kicker': 'Ejercicios',
        'empty_message': 'No hay ejercicios disponibles todavia.',
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

    exercises = Exercise.objects.filter(category=category)
    context = {
        'exercises': exercises,
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

    exercises = Exercise.objects.filter(difficulty=difficulty)
    context = {
        'exercises': exercises,
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

def workout_list(request):
    workouts = Workout.objects.filter(is_public=True)
    if request.user.is_authenticated:
        # We can add private workouts here later
        pass
    
    context = {
        'workouts': workouts
    }
    return render(request, 'exercises/workout_list.html', context)

def workout_detail(request, slug):
    workout = get_object_or_404(Workout, slug=slug)
    workout_exercises = workout.exercises.select_related('exercise').all()
    
    context = {
        'workout': workout,
        'workout_exercises': workout_exercises
    }
    return render(request, 'exercises/workout_detail.html', context)

@login_required
def workout_session(request, slug):
    workout = get_object_or_404(Workout, slug=slug)
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
    
    context = {
        'recent_logs': recent_logs,
        'favorite_exercises': favorite_exercises,
        'total_workouts': total_workouts,
    }
    return render(request, 'exercises/dashboard.html', context)

@login_required
@require_POST
def log_workout(request):
    import json
    data = json.loads(request.body)
    workout_id = data.get('workout_id')
    workout = get_object_or_404(Workout, id=workout_id)
    
    WorkoutLog.objects.create(user=request.user, workout=workout)
    
    return JsonResponse({'status': 'success'})

@login_required
def create_workout(request):
    from .forms import WorkoutForm, WorkoutExerciseFormSet
    
    if request.method == 'POST':
        form = WorkoutForm(request.POST)
        formset = WorkoutExerciseFormSet(request.POST)
        
        if form.is_valid() and formset.is_valid():
            workout = form.save(commit=False)
            # If standard user, maybe force is_public=False or similar? 
            # For now let them choose.
            workout.save()
            
            instances = formset.save(commit=False)
            for instance in instances:
                instance.workout = workout
                instance.save()
            
            # Save deletions if any
            for obj in formset.deleted_objects:
                obj.delete()
                
            return redirect('exercises:workout_detail', slug=workout.slug)
    else:
        form = WorkoutForm()
        formset = WorkoutExerciseFormSet()
        
    return render(request, 'exercises/workout_form.html', {
        'form': form,
        'formset': formset
    })

@login_required
def generate_routine_view(request):
    if request.method == 'POST':
        duration = request.POST.get('duration', 30)
        difficulty = request.POST.get('difficulty', 'intermediate')
        focus = request.POST.get('focus', 'mix')
        
        try:
            generator = RoutineGenerator(
                user=request.user,
                duration_minutes=duration,
                difficulty=difficulty,
                focus=focus
            )
            workout = generator.generate()
            return redirect('exercises:workout_detail', slug=workout.slug)
            
        except Exception as e:
            # Add error handling appropriately
            logger.error(f"Error generating routine: {e}")
            # fall through to render page again with error?
            
    return render(request, 'exercises/generate_routine.html')
