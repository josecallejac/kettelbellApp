from .models import Exercise, Workout, WorkoutExercise, WorkoutLog

# Adaptación por historial
RECENT_WORKOUTS_TO_AVOID = 3   # rutinas propias cuyos ejercicios se evita repetir
RPE_LOGS_WINDOW = 5            # sesiones recientes para el promedio de RPE
RPE_HIGH_THRESHOLD = 8.5       # promedio >= aquí -> aligerar la rutina
RPE_LOW_THRESHOLD = 5.0        # promedio <= aquí -> subir un poco el volumen


class RoutineGenerator:
    """
    Generates balanced kettlebell routines based on time, difficulty, and focus.
    Adapts to the user's history: avoids recently used exercises and adjusts
    volume based on recent RPE.
    """

    def __init__(self, user, duration_minutes=30, difficulty='intermediate', focus='full_body'):
        self.user = user
        self.duration_minutes = int(duration_minutes)
        self.difficulty = difficulty
        self.focus = focus
        self.adaptation_note = ''

    def generate(self):
        """
        Main method to generate and save the workout.
        """
        # 1. Select exercises
        exercises = self._select_exercises()
        
        # 2. Create Workout container
        title = f"Rutina {self._get_focus_display()} ({self.duration_minutes} min)"
        description = f"Rutina generada automáticamente enfocada en {self._get_focus_display()} para nivel {self.difficulty}."
        if self.adaptation_note:
            description += f" {self.adaptation_note}"
        
        workout = Workout.objects.create(
            title=title,
            description=description,
            difficulty=self.difficulty,
            estimated_duration=self.duration_minutes,
            created_by=self.user,
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

        # Approx 3-4 mins per exercise (including rest), ajustado por RPE reciente
        num_main_exercises = max(2, main_time // 4 + self._rpe_volume_adjustment())

        if self.focus == 'mix':
            categories = ['strength', 'cardio', 'full_body']
        else:
            categories = [self.focus]

            # If not enough specific exercises, add full_body
            if Exercise.objects.filter(category__in=categories, difficulty=self.difficulty).count() < num_main_exercises:
                 categories.append('full_body')

        # Variedad: primero los que no aparecieron en las últimas rutinas del
        # usuario; si el catálogo no alcanza, se completa con repetidos.
        recent_ids = self._recent_exercise_ids()
        base_queryset = Exercise.objects.filter(
            category__in=categories,
            difficulty=self.difficulty
        )
        main_candidates = list(
            base_queryset.exclude(id__in=recent_ids).order_by('?')[:num_main_exercises]
        )
        missing = num_main_exercises - len(main_candidates)
        if missing > 0:
            already = [ex.id for ex in main_candidates]
            main_candidates += list(
                base_queryset.filter(id__in=recent_ids)
                .exclude(id__in=already)
                .order_by('?')[:missing]
            )

        selected_exercises.extend([('main', ex) for ex in main_candidates])
        
        # --- Cooldown ---
        cooldown_candidates = Exercise.objects.filter(
            category='flexibility'
        ).order_by('?')[:1]
        
        selected_exercises.extend([('cooldown', ex) for ex in cooldown_candidates])
        
        return selected_exercises

    def _recent_exercise_ids(self):
        """IDs de ejercicios usados en las últimas rutinas del usuario."""
        recent_workout_ids = list(
            Workout.objects.filter(created_by=self.user)
            .order_by('-created_at')
            .values_list('id', flat=True)[:RECENT_WORKOUTS_TO_AVOID]
        )
        return set(
            WorkoutExercise.objects.filter(workout_id__in=recent_workout_ids)
            .values_list('exercise_id', flat=True)
        )

    def _rpe_volume_adjustment(self):
        """-1, 0 o +1 ejercicios del bloque principal según el RPE reciente."""
        rpes = list(
            WorkoutLog.objects.filter(user=self.user, rpe__isnull=False)
            .order_by('-completed_at')
            .values_list('rpe', flat=True)[:RPE_LOGS_WINDOW]
        )
        if not rpes:
            return 0
        avg_rpe = sum(rpes) / len(rpes)
        if avg_rpe >= RPE_HIGH_THRESHOLD:
            self.adaptation_note = (
                'Volumen reducido: tu esfuerzo reciente (RPE) ha sido alto, toca recuperar.'
            )
            return -1
        if avg_rpe <= RPE_LOW_THRESHOLD:
            self.adaptation_note = (
                'Volumen aumentado: tus últimas sesiones se sintieron livianas.'
            )
            return 1
        return 0

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
