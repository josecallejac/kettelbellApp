from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone

from .forms import TrainingPlanForm, UserProfileForm
from .models import Exercise, ExercisePerformance, UserProfile, Workout, WorkoutExercise, WorkoutLog
from .plans import create_training_plan, prepare_planned_session
from .progression import recommend_exercise_progression
from .utils import RoutineGenerator


class WeightInventoryTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='weightsafety', password='password123')
        self.profile = UserProfile.objects.create(user=self.user)

    def test_legacy_profile_parser_keeps_only_safe_finite_weights(self):
        self.profile.available_weights = '-1, 0, 0.1, 200, 200.1, nan, inf, 12, 12.0, abc'
        self.profile.save()
        self.assertEqual(self.profile.weights_list(), [0.1, 12.0, 200.0])

    def test_profile_form_rejects_invalid_tokens_and_normalizes_valid_input(self):
        invalid = UserProfileForm(
            data={'level': 'beginner', 'goal': 'general', 'available_weights': '8, nan'},
            instance=self.profile,
        )
        self.assertFalse(invalid.is_valid())
        self.assertIn('Cada peso debe ser un numero finito', invalid.errors['available_weights'][0])

        valid = UserProfileForm(
            data={
                'level': 'beginner',
                'goal': 'general',
                'available_weights': '16.00, 8, 8, 0.1, 200',
            },
            instance=self.profile,
        )
        self.assertTrue(valid.is_valid(), valid.errors)
        self.assertEqual(valid.cleaned_data['available_weights'], '0.1, 8, 16, 200')

    def test_training_plan_form_shares_inventory_validation(self):
        form = TrainingPlanForm(data={
            'level': 'beginner',
            'goal': 'general',
            'available_weights': '8, -4',
            'sessions_per_week': '2',
            'preferred_weekdays': ['0', '2'],
            'session_duration': '10',
            'start_date': timezone.localdate().isoformat(),
        })
        self.assertFalse(form.is_valid())
        self.assertIn('available_weights', form.errors)


class ProgressionSafetyTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='progressionsafety', password='password123')
        UserProfile.objects.create(user=self.user, available_weights='8, 12')
        self.exercise = Exercise.objects.create(
            name='Press seguro',
            description='x',
            category='strength',
            difficulty='beginner',
        )
        self.workout = Workout.objects.create(
            title='Rutina segura',
            description='x',
            difficulty='beginner',
            estimated_duration=20,
            created_by=self.user,
        )
        self.workout_exercise = WorkoutExercise.objects.create(
            workout=self.workout,
            exercise=self.exercise,
            order=1,
            sets=3,
            reps='10 reps',
        )

    def _record(self, weight, rpe, completed=True):
        log = WorkoutLog.objects.create(user=self.user, workout=self.workout, rpe=rpe)
        return ExercisePerformance.objects.create(
            user=self.user,
            workout_log=log,
            workout_exercise=self.workout_exercise,
            exercise=self.exercise,
            completed=completed,
            sets_completed=3,
            reps_completed=10,
            weight=weight,
            rpe=rpe,
        )

    def test_hard_session_without_lower_inventory_returns_no_weight(self):
        self._record(4, 9)
        recommendation = recommend_exercise_progression(self.user, self.exercise)
        self.assertIsNone(recommendation['suggested_weight'])
        self.assertEqual(recommendation['status'], 'deload')
        self.assertIn('sin carga', recommendation['reason'])

    def test_incomplete_session_without_lower_inventory_returns_no_weight(self):
        self._record(4, 7, completed=False)
        recommendation = recommend_exercise_progression(self.user, self.exercise)
        self.assertIsNone(recommendation['suggested_weight'])
        self.assertEqual(recommendation['status'], 'recover')
        self.assertIn('sin carga', recommendation['reason'])

    def test_hard_session_uses_strictly_lower_inventory_weight(self):
        self._record(12, 9)
        recommendation = recommend_exercise_progression(self.user, self.exercise)
        self.assertEqual(recommendation['suggested_weight'], 8.0)


class RoutineGenerationSafetyTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='generatorsafety', password='password123')
        UserProfile.objects.create(user=self.user, available_weights='8, 12, 16')
        Exercise.objects.create(
            name='Calentamiento', description='x', category='cardio', difficulty='beginner'
        )
        Exercise.objects.create(
            name='Principal', description='x', category='strength', difficulty='beginner'
        )
        Exercise.objects.create(
            name='Cierre', description='x', category='flexibility', difficulty='beginner'
        )

    def test_ten_minute_session_has_compact_three_phase_structure(self):
        workout = RoutineGenerator(
            user=self.user,
            duration_minutes=10,
            difficulty='beginner',
            focus='strength',
        ).generate()
        self.assertEqual(workout.exercises.count(), 3)
        self.assertEqual(workout.exercises.filter(reps='30-45 segs').count(), 1)
        self.assertEqual(workout.exercises.filter(reps='8-12 reps').count(), 1)
        self.assertEqual(workout.exercises.filter(reps='60 segs').count(), 1)

    def test_plan_disables_generator_history_adjustment(self):
        plan, _ = create_training_plan(self.user, {
            'level': 'beginner',
            'goal': 'general',
            'available_weights': '8, 12, 16',
            'sessions_per_week': 2,
            'preferred_weekdays': [0, 2],
            'session_duration': 30,
            'start_date': timezone.localdate(),
            'reminders_enabled': False,
            'reminder_time': None,
        })
        session = plan.sessions.first()
        generated = Workout.objects.create(
            title='Mock plan routine',
            description='x',
            difficulty='beginner',
            estimated_duration=30,
            created_by=self.user,
        )
        with patch('exercises.plans.RoutineGenerator') as generator:
            generator.return_value.generate.return_value = generated
            prepare_planned_session(
                self.user,
                session,
                readiness={'energy_level': 3, 'pain_level': 'none', 'available_minutes': 30},
            )
        self.assertFalse(generator.call_args.kwargs['apply_history_volume_adjustment'])

    def test_deload_without_lower_inventory_does_not_fallback_upward(self):
        source = Workout.objects.create(
            title='Registro dificil',
            description='x',
            difficulty='beginner',
            estimated_duration=20,
            created_by=self.user,
        )
        exercise = Exercise.objects.get(name='Principal')
        item = WorkoutExercise.objects.create(
            workout=source,
            exercise=exercise,
            order=1,
            sets=3,
            reps='10 reps',
        )
        log = WorkoutLog.objects.create(user=self.user, workout=source, rpe=9)
        ExercisePerformance.objects.create(
            user=self.user,
            workout_log=log,
            workout_exercise=item,
            exercise=exercise,
            weight=4,
            rpe=9,
        )

        generated = RoutineGenerator(
            user=self.user,
            duration_minutes=30,
            difficulty='beginner',
            focus='strength',
            allow_weight_progression=False,
        ).generate()
        main = generated.exercises.get(exercise=exercise)
        self.assertIn('Sin carga', main.notes)
        self.assertNotIn('Peso sugerido', main.notes)
