import random
from .models import Exercise, Workout, WorkoutExercise

class RoutineGenerator:
    """
    Generates balanced kettlebell routines based on time, difficulty, and focus.
    """
    
    def __init__(self, user, duration_minutes=30, difficulty='intermediate', focus='full_body'):
        self.user = user
        self.duration_minutes = int(duration_minutes)
        self.difficulty = difficulty
        self.focus = focus
        
    def generate(self):
        """
        Main method to generate and save the workout.
        """
        # 1. Select exercises
        exercises = self._select_exercises()
        
        # 2. Create Workout container
        title = f"Rutina {self._get_focus_display()} ({self.duration_minutes} min)"
        description = f"Rutina generada automáticamente enfocada en {self._get_focus_display()} para nivel {self.difficulty}."
        
        workout = Workout.objects.create(
            title=title,
            description=description,
            difficulty=self.difficulty,
            estimated_duration=self.duration_minutes,
            is_public=False  # Private by default
        )
        
        # 3. Create WorkoutExercise items (the actual routine)
        self._create_workout_exercises(workout, exercises)
        
        return workout

    def _select_exercises(self):
        """
        Selects a balanced mix of exercises.
        Structure:
        - Warmup (1-2 exercises)
        - Main Block (Focus-based)
        - Cooldown (1 exercise)
        """
        selected_exercises = []
        
        # --- Warmup ---
        # Usually mobility or light cardio
        warmup_candidates = Exercise.objects.filter(
            category__in=['flexibility', 'cardio'],
            difficulty__in=['beginner'] # Warmup should vary easily
        ).order_by('?')[:2]
        
        selected_exercises.extend([('warmup', ex) for ex in warmup_candidates])
        
        # --- Main Block ---
        # Calculate time remaining for main block
        # Assuming warmup takes ~5 mins and cooldown ~5 mins
        main_time = max(10, self.duration_minutes - 10)
        
        # Approx 3-4 mins per exercise (including rest)
        num_main_exercises = max(2, main_time // 4)
        
        if self.focus == 'mix':
            categories = ['strength', 'cardio', 'full_body']
        else:
            categories = [self.focus]
            
            # If not enough specific exercises, add full_body
            if Exercise.objects.filter(category__in=categories, difficulty=self.difficulty).count() < num_main_exercises:
                 categories.append('full_body')

        main_candidates = Exercise.objects.filter(
            category__in=categories,
            difficulty=self.difficulty
        ).order_by('?')[:num_main_exercises]
        
        selected_exercises.extend([('main', ex) for ex in main_candidates])
        
        # --- Cooldown ---
        cooldown_candidates = Exercise.objects.filter(
            category='flexibility'
        ).order_by('?')[:1]
        
        selected_exercises.extend([('cooldown', ex) for ex in cooldown_candidates])
        
        return selected_exercises

    def _create_workout_exercises(self, workout, exercise_list):
        """
        Assigns sets/reps based on type and difficulty.
        """
        order = 1
        for phase, exercise in exercise_list:
            sets = 3
            reps = "10-12 reps"
            notes = ""
            
            if phase == 'warmup':
                sets = 2
                reps = "30-45 segs"
                notes = "Realizar movimientos suaves y controlados para calentar."
            
            elif phase == 'cooldown':
                sets = 1
                reps = "60 segs"
                notes = "Mantener la posición para relajar los músculos."
                
            else: # Main block logic
                if exercise.category == 'strength':
                    sets = 3 if self.difficulty == 'beginner' else 4
                    reps = "8-12 reps"
                    notes = "Descanso de 60-90s entre series."
                elif exercise.category == 'cardio':
                    sets = 3
                    reps = "40s trabajo / 20s descanso"
                    notes = "Mantener intensidad alta."
                elif exercise.category == 'full_body':
                    sets = 3
                    reps = "10 reps"
                    notes = "Controlar la técnica en todo momento."
            
            WorkoutExercise.objects.create(
                workout=workout,
                exercise=exercise,
                order=order,
                sets=sets,
                reps=reps,
                notes=notes
            )
            order += 1

    def _get_focus_display(self):
        focus_map = {
            'strength': 'Fuerza',
            'cardio': 'Cardio',
            'flexibility': 'Flexibilidad',
            'full_body': 'Cuerpo Completo',
            'mix': 'Mixta'
        }
        return focus_map.get(self.focus, 'Personalizada')
