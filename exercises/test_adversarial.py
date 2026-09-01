import json
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse

from exercises.models import (
    Exercise,
    Favorite,
    UserProfile,
    Workout,
    WorkoutExercise,
    WorkoutLog,
    build_unique_slug,
)
from exercises.utils import RoutineGenerator


class ModelRepresentationAndUrlTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='test_model_user', password='password123')
        self.exercise = Exercise.objects.create(
            name='Test Exercise',
            description='x',
            category='strength',
            difficulty='beginner'
        )

    def test_model_str_methods(self):
        # Favorite __str__
        favorite = Favorite.objects.create(user=self.user, exercise=self.exercise)
        self.assertEqual(str(favorite), f"{self.user.username} - {self.exercise.name}")

        # Workout __str__
        workout = Workout.objects.create(
            title='Test Workout',
            description='x',
            difficulty='beginner',
            estimated_duration=30,
            created_by=self.user
        )
        self.assertEqual(str(workout), 'Test Workout')

        # WorkoutExercise __str__
        we = WorkoutExercise.objects.create(
            workout=workout,
            exercise=self.exercise,
            order=1,
            sets=3,
            reps='10'
        )
        self.assertEqual(str(we), f"{workout.title} - {self.exercise.name}")

        # UserProfile __str__
        profile = UserProfile.objects.create(user=self.user, level='beginner', goal='general')
        self.assertEqual(str(profile), f"Perfil de {self.user.username}")

        # WorkoutLog __str__
        log = WorkoutLog.objects.create(user=self.user, workout=workout, rpe=7)
        expected_log_str = f"{self.user.username} - {workout.title} ({log.completed_at.strftime('%Y-%m-%d')})"
        self.assertEqual(str(log), expected_log_str)

    def test_exercise_absolute_url(self):
        self.assertEqual(self.exercise.get_absolute_url(), f"/exercise/{self.exercise.slug}/")

    @patch('exercises.models.static')
    def test_image_url_value_error(self, mock_static):
        # ValueError raised by static() (e.g. strict ManifestStaticFilesStorage missing file)
        mock_static.side_effect = ValueError("Static asset not found")
        exercise_with_img = Exercise.objects.create(
            name='Exercise With Image',
            description='x',
            category='strength',
            difficulty='beginner',
            image='missing_image.jpg'
        )
        self.assertEqual(exercise_with_img.image_url, '')

    def test_profile_weights_edge_cases(self):
        # Weights parsing handles spaces, empty values, negative values, and duplicate weights
        profile = UserProfile.objects.create(
            user=self.user,
            available_weights='-8, , 12, -16.5, 12,  '
        )
        self.assertEqual(profile.weights_list(), [-16.5, -8.0, 12.0])

        # Test empty available weights
        profile.available_weights = '   '
        self.assertEqual(profile.weights_list(), [])

    def test_slug_generation_special_chars(self):
        # Purely special character text resolves to 'item' base slug
        exercise = Exercise(name='!!!', description='x', category='strength', difficulty='beginner')
        slug = build_unique_slug(exercise, exercise.name)
        self.assertEqual(slug, 'item')


class ViewsUncoveredPathsTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username='view_test_user', password='password123')

    def test_register_get_unauthenticated(self):
        response = self.client.get(reverse('exercises:register'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'form')

    def test_login_get_unauthenticated(self):
        response = self.client.get(reverse('exercises:login'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'form')

    def test_create_workout_get(self):
        self.client.login(username='view_test_user', password='password123')
        response = self.client.get(reverse('exercises:workout_create'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'form')

    def test_log_workout_invalid_id_format(self):
        self.client.login(username='view_test_user', password='password123')
        url = reverse('exercises:log_workout')
        
        # Test missing workout_id
        response = self.client.post(url, json.dumps({}), content_type='application/json')
        self.assertEqual(response.status_code, 400)
        self.assertIn('Petición inválida', response.json().get('message', ''))
        
        # Test non-integer workout_id format
        response = self.client.post(url, json.dumps({'workout_id': 'abc'}), content_type='application/json')
        self.assertEqual(response.status_code, 400)

        # Test dict workout_id format
        response = self.client.post(url, json.dumps({'workout_id': {'id': 1}}), content_type='application/json')
        self.assertEqual(response.status_code, 400)

    def test_log_workout_weight_invalid_operation(self):
        self.client.login(username='view_test_user', password='password123')
        workout = Workout.objects.create(
            title='Temp Workout',
            description='x',
            difficulty='beginner',
            estimated_duration=30
        )
        url = reverse('exercises:log_workout')
        
        # Passing invalid weight string to check InvalidOperation exception handling
        response = self.client.post(url, json.dumps({
            'workout_id': workout.id,
            'kettlebell_weight': 'not-a-decimal'
        }), content_type='application/json')
        self.assertEqual(response.status_code, 400)
        self.assertIn('Métricas inválidas', response.json().get('message', ''))

    @patch('exercises.views.RoutineGenerator.generate')
    def test_generate_routine_exception_handling(self, mock_generate):
        mock_generate.side_effect = Exception("Database failure")
        self.client.login(username='view_test_user', password='password123')
        
        response = self.client.post(reverse('exercises:generate_routine'), {
            'duration': 30,
            'difficulty': 'beginner',
            'focus': 'mix'
        })
        self.assertEqual(response.status_code, 200) # Renders form back
        self.assertContains(response, 'No se pudo generar la rutina')


class RoutineGeneratorAdversarialTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='routine_test_user', password='password123')

    def test_routine_generator_category_fallback(self):
        # Clear database to isolate
        Exercise.objects.all().delete()
        
        # Create 1 intermediate cardio exercise and 2 intermediate full body exercises
        Exercise.objects.create(name='Cardio Ex', description='x', category='cardio', difficulty='intermediate')
        Exercise.objects.create(name='FB Ex 1', description='x', category='full_body', difficulty='intermediate')
        Exercise.objects.create(name='FB Ex 2', description='x', category='full_body', difficulty='intermediate')
        
        # Cooldown & Warmup candidates
        Exercise.objects.create(name='Flexibility Ex', description='x', category='flexibility', difficulty='intermediate')
        Exercise.objects.create(name='Warmup Ex', description='x', category='cardio', difficulty='beginner')

        # Requiring 30 mins means it will look for more exercises than the 1 cardio exercise available
        generator = RoutineGenerator(
            user=self.user,
            duration_minutes=30,
            difficulty='intermediate',
            focus='cardio'
        )
        workout = generator.generate()
        
        # Assert full_body exercises were included because cardio catalog was insufficient
        categories_included = {we.exercise.category for we in workout.exercises.all()}
        self.assertIn('full_body', categories_included)

    def test_rpe_baseline_volume_fall_through(self):
        workout = Workout.objects.create(
            title='Temp Workout',
            description='x',
            difficulty='intermediate',
            estimated_duration=30
        )
        # Create 3 logs with RPE 6, 7, 6. Average RPE is 6.33, between 5.0 and 8.5
        WorkoutLog.objects.create(user=self.user, workout=workout, rpe=6)
        WorkoutLog.objects.create(user=self.user, workout=workout, rpe=7)
        WorkoutLog.objects.create(user=self.user, workout=workout, rpe=6)
        
        generator = RoutineGenerator(user=self.user, difficulty='intermediate', focus='strength')
        adjustment = generator._rpe_volume_adjustment()
        self.assertEqual(adjustment, 0)
        self.assertEqual(generator.adaptation_note, '')

    def test_routine_generator_empty_db(self):
        # Empty the catalog completely
        Exercise.objects.all().delete()
        
        generator = RoutineGenerator(user=self.user, duration_minutes=30, difficulty='intermediate', focus='mix')
        workout = generator.generate()
        
        # Generator shouldn't crash, it should just return workout with 0 exercises
        self.assertEqual(workout.exercises.count(), 0)

    def test_routine_generator_extreme_duration(self):
        # Seed a small set of exercises
        for i in range(3):
            Exercise.objects.create(name=f'Strength Ex {i}', description='x', category='strength', difficulty='intermediate')
        Exercise.objects.create(name='Flexibility Ex', description='x', category='flexibility', difficulty='intermediate')
        Exercise.objects.create(name='Warmup Ex', description='x', category='cardio', difficulty='beginner')

        # Requests a 1000-minute routine (which calculates huge exercise count target)
        generator = RoutineGenerator(user=self.user, duration_minutes=1000, difficulty='intermediate', focus='strength')
        workout = generator.generate()
        
        # Generator should handle this gracefully and limit itself to available exercises without crashing
        self.assertTrue(workout.exercises.count() > 0)
