from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from .models import Exercise, Favorite, Workout, WorkoutLog
from .utils import RoutineGenerator
from .forms import CustomUserCreationForm, CustomAuthenticationForm
import logging

logger = logging.getLogger(__name__)

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
    
    favorites_ids = []
    if request.user.is_authenticated:
        favorites_ids = list(request.user.favorites.values_list('exercise_id', flat=True))

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
    }
    
    return render(request, 'exercises/landing.html', context)

def exercise_detail(request, slug):
    exercise = get_object_or_404(Exercise, slug=slug)
    is_favorite = False
    if request.user.is_authenticated:
        is_favorite = Favorite.objects.filter(user=request.user, exercise=exercise).exists()
        
    context = {
        'exercise': exercise,
        'is_favorite': is_favorite,
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
