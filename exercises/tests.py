import json
import uuid
from datetime import timedelta
from unittest.mock import patch

from django.conf import settings as django_settings
from django.contrib.auth.models import User
from django.core.cache import cache
from django.templatetags.static import static
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from django.utils.crypto import get_random_string

from .history import build_weekly_review
from .models import (
    Exercise,
    ExercisePerformance,
    Favorite,
    PlannedSession,
    PushSubscription,
    TrainingPlan,
    UserProfile,
    Workout,
    WorkoutExercise,
    WorkoutLog,
)
from .plans import build_schedule, create_training_plan, prepare_planned_session
from .progression import build_exercise_progress, recommend_exercise_progression
from .utils import RoutineGenerator


class AuthTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.register_url = reverse('exercises:register')
        self.login_url = reverse('exercises:login')
        self.logout_url = reverse('exercises:logout')

    def test_register_user(self):
        password = get_random_string(32)
        response = self.client.post(self.register_url, {
            'username': 'newuser',
            'email': 'new@example.com',
            'password1': password,
            'password2': password,
        })
        self.assertRedirects(response, reverse('exercises:landing'))
        self.assertTrue(User.objects.filter(username='newuser').exists())
        self.assertTrue(response.wsgi_request.user.is_authenticated)

    def test_register_password_mismatch_shows_errors(self):
        password = get_random_string(32)
        response = self.client.post(self.register_url, {
            'username': 'newuser',
            'email': 'new@example.com',
            'password1': password,
            'password2': 'otra-cosa',
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(username='newuser').exists())

    def test_login_user(self):
        User.objects.create_user(username='testuser', password='password123')
        response = self.client.post(self.login_url, {
            'username': 'testuser',
            'password': 'password123'
        })
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.wsgi_request.user.is_authenticated)

    def test_login_rejects_external_next_redirect(self):
        User.objects.create_user(username='testuser', password='password123')
        response = self.client.post(self.login_url, {
            'username': 'testuser',
            'password': 'password123',
            'next': 'https://evil.example.com/phish',
        })
        self.assertRedirects(response, reverse('exercises:landing'))

    def test_login_honors_internal_next_redirect(self):
        User.objects.create_user(username='testuser', password='password123')
        response = self.client.post(self.login_url, {
            'username': 'testuser',
            'password': 'password123',
            'next': reverse('exercises:dashboard'),
        })
        self.assertRedirects(response, reverse('exercises:dashboard'))

    def test_authenticated_user_redirected_from_login_and_register(self):
        User.objects.create_user(username='testuser', password='password123')
        self.client.login(username='testuser', password='password123')
        for url in (self.login_url, self.register_url):
            response = self.client.get(url)
            self.assertRedirects(response, reverse('exercises:landing'))

    @override_settings(ALLOW_REGISTRATION=False)
    def test_closed_beta_hides_and_blocks_registration(self):
        self.assertEqual(self.client.get(self.register_url).status_code, 404)
        password = get_random_string(32)
        response = self.client.post(self.register_url, {
            'username': 'blocked',
            'password1': password,
            'password2': password,
        })
        self.assertEqual(response.status_code, 404)
        landing = self.client.get(reverse('exercises:landing'))
        login_page = self.client.get(self.login_url)
        self.assertNotContains(landing, 'Registrarse')
        self.assertNotContains(login_page, 'Regístrate aquí')

    def test_logout_user(self):
        User.objects.create_user(username='testuser', password='password123')
        self.client.login(username='testuser', password='password123')
        response = self.client.post(self.logout_url)
        self.assertEqual(response.status_code, 302)
        self.assertFalse(response.wsgi_request.user.is_authenticated)

    def test_logout_rejects_get(self):
        User.objects.create_user(username='testuser', password='password123')
        self.client.login(username='testuser', password='password123')
        response = self.client.get(self.logout_url)
        self.assertEqual(response.status_code, 405)
        self.assertTrue(response.wsgi_request.user.is_authenticated)


class HealthCheckTests(TestCase):
    def test_healthz_reports_application_database_and_sha(self):
        response = self.client.get(reverse('exercises:healthz'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['status'], 'ok')
        self.assertEqual(response.json()['database'], 'ok')
        self.assertIn('sha', response.json())
        self.assertEqual(response.headers['Cache-Control'], 'no-store')
        self.assertEqual(self.client.post(reverse('exercises:healthz')).status_code, 405)

    @patch('exercises.views.connection.cursor', side_effect=Exception('database down'))
    def test_healthz_returns_503_when_database_is_unavailable(self, _cursor):
        response = self.client.get(reverse('exercises:healthz'))
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()['database'], 'error')


class ExerciseModelTests(TestCase):
    def test_duplicate_names_get_unique_slugs(self):
        first = Exercise.objects.create(
            name='Press Militar KB', description='x', category='strength', difficulty='beginner'
        )
        second = Exercise.objects.create(
            name='Press Militar KB', description='y', category='strength', difficulty='beginner'
        )
        self.assertNotEqual(first.slug, second.slug)
        self.assertTrue(second.slug.startswith(first.slug))

    def test_image_url_resolves_catalog_static_path(self):
        exercise = Exercise.objects.create(
            name='Con imagen', description='x', category='strength', difficulty='beginner',
            image='kettlebell_swing.jpg',
        )
        # The production manifest adds a content hash; development storage does not.
        self.assertEqual(
            exercise.image_url,
            static('exercises/img/catalog/kettlebell_swing.jpg'),
        )

    def test_image_url_empty_when_no_image(self):
        exercise = Exercise.objects.create(
            name='Sin imagen', description='x', category='strength', difficulty='beginner'
        )
        self.assertEqual(exercise.image_url, '')


class FavoriteTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username='favuser', password='password123')
        self.exercise = Exercise.objects.create(
            name='Swing de prueba',
            description='Basic swing',
            category='strength',
            difficulty='beginner'
        )
        self.toggle_url = reverse('exercises:toggle_favorite')

    def _toggle(self, payload):
        return self.client.post(self.toggle_url, payload, content_type='application/json')

    def test_toggle_favorite_authenticated(self):
        self.client.login(username='favuser', password='password123')

        response = self._toggle(json.dumps({'exercise_id': self.exercise.id}))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['is_favorite'])
        self.assertTrue(Favorite.objects.filter(user=self.user, exercise=self.exercise).exists())

        response = self._toggle(json.dumps({'exercise_id': self.exercise.id}))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()['is_favorite'])
        self.assertFalse(Favorite.objects.filter(user=self.user, exercise=self.exercise).exists())

    def test_toggle_favorite_invalid_payloads_return_400(self):
        self.client.login(username='favuser', password='password123')
        for payload in ('no-es-json', json.dumps({}), json.dumps({'exercise_id': 'abc'})):
            response = self._toggle(payload)
            self.assertEqual(response.status_code, 400)

    def test_toggle_favorite_unauthenticated_redirects_to_login(self):
        response = self._toggle(json.dumps({'exercise_id': self.exercise.id}))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('exercises:login'), response.url)


class WorkoutVisibilityTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.owner = User.objects.create_user(username='owner', password='password123')
        self.other = User.objects.create_user(username='other', password='password123')
        self.private_workout = Workout.objects.create(
            title='Rutina privada',
            description='x',
            difficulty='beginner',
            estimated_duration=30,
            created_by=self.owner,
            is_public=False,
        )
        self.public_workout = Workout.objects.create(
            title='Rutina publica',
            description='x',
            difficulty='beginner',
            estimated_duration=30,
            is_public=True,
        )

    def test_private_workout_hidden_from_other_users(self):
        self.client.login(username='other', password='password123')
        response = self.client.get(
            reverse('exercises:workout_detail', kwargs={'slug': self.private_workout.slug})
        )
        self.assertEqual(response.status_code, 404)

    def test_private_workout_visible_to_owner(self):
        self.client.login(username='owner', password='password123')
        response = self.client.get(
            reverse('exercises:workout_detail', kwargs={'slug': self.private_workout.slug})
        )
        self.assertEqual(response.status_code, 200)

    def test_public_workout_visible_anonymously(self):
        response = self.client.get(
            reverse('exercises:workout_detail', kwargs={'slug': self.public_workout.slug})
        )
        self.assertEqual(response.status_code, 200)

    def test_workout_list_only_shows_visible_workouts(self):
        self.client.login(username='other', password='password123')
        response = self.client.get(reverse('exercises:workout_list'))
        workouts = list(response.context['workouts'])
        self.assertIn(self.public_workout, workouts)
        self.assertNotIn(self.private_workout, workouts)

    def test_log_workout_rejects_foreign_private_workout(self):
        self.client.login(username='other', password='password123')
        response = self.client.post(
            reverse('exercises:log_workout'),
            json.dumps({'workout_id': self.private_workout.id}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 404)
        self.assertFalse(WorkoutLog.objects.filter(user=self.other).exists())

    def test_log_workout_success(self):
        self.client.login(username='owner', password='password123')
        response = self.client.post(
            reverse('exercises:log_workout'),
            json.dumps({'workout_id': self.private_workout.id}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(WorkoutLog.objects.filter(user=self.owner, workout=self.private_workout).count(), 1)


class RoutineGeneratorTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='genuser', password='password123')

    def test_generator_creates_private_owned_workout_with_exercises(self):
        generator = RoutineGenerator(
            user=self.user, duration_minutes=30, difficulty='intermediate', focus='mix'
        )
        workout = generator.generate()
        self.assertEqual(workout.created_by, self.user)
        self.assertFalse(workout.is_public)
        self.assertGreater(workout.exercises.count(), 0)

    def test_generate_view_redirects_to_new_workout(self):
        self.client.login(username='genuser', password='password123')
        response = self.client.post(reverse('exercises:generate_routine'), {
            'duration': 30,
            'difficulty': 'beginner',
            'focus': 'mix',
        })
        self.assertEqual(response.status_code, 302)
        workout = Workout.objects.filter(created_by=self.user).latest('created_at')
        self.assertIn(workout.slug, response.url)

    def test_generate_view_rejects_invalid_input(self):
        self.client.login(username='genuser', password='password123')
        response = self.client.post(reverse('exercises:generate_routine'), {
            'duration': 'mucho',
            'difficulty': 'imposible',
            'focus': 'mix',
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Workout.objects.filter(created_by=self.user).exists())


class ProfileTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='profuser', password='password123')
        self.client.login(username='profuser', password='password123')
        self.url = reverse('exercises:profile')

    def test_profile_page_creates_profile_on_first_visit(self):
        self.assertFalse(UserProfile.objects.filter(user=self.user).exists())
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(UserProfile.objects.filter(user=self.user).exists())

    def test_profile_update(self):
        response = self.client.post(self.url, {
            'level': 'advanced',
            'goal': 'strength',
            'available_weights': '8, 12, 16',
        })
        self.assertRedirects(response, self.url)
        profile = UserProfile.objects.get(user=self.user)
        self.assertEqual(profile.level, 'advanced')
        self.assertEqual(profile.goal, 'strength')
        self.assertEqual(profile.weights_list(), [8.0, 12.0, 16.0])

    def test_weights_list_ignores_garbage(self):
        profile = UserProfile.objects.create(
            user=self.user, available_weights='16, doce, , 8.5, 16'
        )
        self.assertEqual(profile.weights_list(), [8.5, 16.0])

    def test_generate_form_defaults_from_profile(self):
        UserProfile.objects.create(user=self.user, level='advanced', goal='fat_loss')
        response = self.client.get(reverse('exercises:generate_routine'))
        self.assertContains(response, 'value="advanced" checked')
        self.assertContains(response, 'value="cardio" checked')

    def test_generate_form_defaults_without_profile(self):
        response = self.client.get(reverse('exercises:generate_routine'))
        self.assertContains(response, 'value="intermediate" checked')
        self.assertContains(response, 'value="mix" checked')


class AdaptiveGeneratorTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='adaptuser', password='password123')
        self.strength = [
            Exercise.objects.create(
                name=f'Fuerza adaptativa {i}', description='x',
                category='strength', difficulty='intermediate',
            )
            for i in range(4)
        ]

    def _generate(self, duration=18):
        # duration=18 -> bloque principal de 2 ejercicios (sin ajuste RPE)
        return RoutineGenerator(
            user=self.user, duration_minutes=duration,
            difficulty='intermediate', focus='strength',
        ).generate()

    def test_avoids_exercises_from_recent_workouts(self):
        recent = self._generate()
        recent_ids = {
            we.exercise_id for we in recent.exercises.filter(exercise__category='strength')
        }
        self.assertEqual(len(recent_ids), 2)

        new = self._generate()
        new_ids = {
            we.exercise_id for we in new.exercises.filter(exercise__category='strength')
        }
        self.assertEqual(len(new_ids), 2)
        self.assertFalse(recent_ids & new_ids, 'No debería repetir ejercicios recientes')

    def test_fills_with_recent_when_catalog_is_short(self):
        # Con solo 4 ejercicios de fuerza, una rutina de 30 min (5 principales)
        # necesita reutilizar recientes en vez de quedarse corta.
        self._generate()
        workout = self._generate(duration=30)
        mains = workout.exercises.filter(exercise__category='strength').count()
        self.assertGreaterEqual(mains, 4)

    def test_rpe_high_reduces_volume(self):
        workout = Workout.objects.create(
            title='w', description='x', difficulty='intermediate',
            estimated_duration=20, created_by=self.user,
        )
        for _ in range(3):
            WorkoutLog.objects.create(user=self.user, workout=workout, rpe=9)
        generator = RoutineGenerator(user=self.user, difficulty='intermediate', focus='strength')
        self.assertEqual(generator._rpe_volume_adjustment(), -1)
        self.assertIn('Volumen reducido', generator.adaptation_note)

    def test_rpe_low_increases_volume(self):
        workout = Workout.objects.create(
            title='w', description='x', difficulty='intermediate',
            estimated_duration=20, created_by=self.user,
        )
        for _ in range(3):
            WorkoutLog.objects.create(user=self.user, workout=workout, rpe=3)
        generator = RoutineGenerator(user=self.user, difficulty='intermediate', focus='strength')
        self.assertEqual(generator._rpe_volume_adjustment(), 1)
        self.assertIn('Volumen aumentado', generator.adaptation_note)

    def test_no_history_no_adjustment(self):
        generator = RoutineGenerator(user=self.user, difficulty='intermediate', focus='strength')
        self.assertEqual(generator._rpe_volume_adjustment(), 0)
        self.assertEqual(generator.adaptation_note, '')

    def test_suggested_weight_by_level(self):
        UserProfile.objects.create(user=self.user, available_weights='8, 12, 16')
        cases = [('beginner', 8), ('intermediate', 12), ('advanced', 16)]
        for level, expected in cases:
            generator = RoutineGenerator(user=self.user, difficulty=level, focus='strength')
            self.assertEqual(generator._suggested_weight('strength'), expected)

    def test_suggested_weight_cardio_steps_down(self):
        UserProfile.objects.create(user=self.user, available_weights='8, 12, 16')
        generator = RoutineGenerator(user=self.user, difficulty='advanced', focus='cardio')
        self.assertEqual(generator._suggested_weight('cardio'), 12)
        # En el extremo inferior no baja más allá de la más liviana.
        generator = RoutineGenerator(user=self.user, difficulty='beginner', focus='cardio')
        self.assertEqual(generator._suggested_weight('cardio'), 8)

    def test_generated_notes_include_suggested_weight(self):
        UserProfile.objects.create(user=self.user, available_weights='8, 12, 16')
        workout = self._generate()
        main_notes = [
            we.notes for we in workout.exercises.filter(exercise__category='strength')
        ]
        self.assertTrue(main_notes)
        for notes in main_notes:
            self.assertIn('Peso sugerido: 12 kg', notes)

    def test_no_weight_suggestion_without_profile(self):
        workout = self._generate()
        for we in workout.exercises.all():
            self.assertNotIn('Peso sugerido', we.notes)

    def test_player_prefills_last_weight(self):
        workout = self._generate()
        WorkoutLog.objects.create(
            user=self.user, workout=workout, kettlebell_weight=16,
        )
        self.client.login(username='adaptuser', password='password123')
        response = self.client.get(
            reverse('exercises:workout_session', kwargs={'slug': workout.slug})
        )
        self.assertContains(response, 'value="16"')


class ExerciseSearchPaginationTests(TestCase):
    def setUp(self):
        # La migración 0008 precarga ejercicios de ejemplo; partimos de cero
        # para que los conteos del test sean deterministas.
        Exercise.objects.all().delete()
        for i in range(15):
            Exercise.objects.create(
                name=f'Ejercicio de prueba {i}',
                description='Descripción genérica',
                muscles_targeted='Glúteos, core' if i % 2 == 0 else 'Hombros',
                category='strength',
                difficulty='beginner',
            )
        self.url = reverse('exercises:exercise_list')

    def test_list_is_paginated(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context['exercises']), 12)
        self.assertTrue(response.context['page_obj'].has_next())

        response = self.client.get(self.url, {'page': 2})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context['page_obj'].has_next())

    def test_invalid_page_falls_back_gracefully(self):
        response = self.client.get(self.url, {'page': 'abc'})
        self.assertEqual(response.status_code, 200)
        response = self.client.get(self.url, {'page': 9999})
        self.assertEqual(response.status_code, 200)

    def test_search_filters_by_name(self):
        response = self.client.get(self.url, {'q': 'Ejercicio de prueba 3'})
        names = [ex.name for ex in response.context['exercises']]
        self.assertEqual(names, ['Ejercicio de prueba 3'])

    def test_search_filters_by_muscles(self):
        response = self.client.get(self.url, {'q': 'core'})
        self.assertEqual(len(response.context['exercises']), 8)

    def test_search_without_results_shows_empty_state(self):
        response = self.client.get(self.url, {'q': 'no-existe-esto'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context['exercises']), 0)


class WorkoutEditDeleteTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username='owner', password='password123')
        self.other = User.objects.create_user(username='other', password='password123')
        self.workout = Workout.objects.create(
            title='Mi rutina',
            description='x',
            difficulty='beginner',
            estimated_duration=30,
            created_by=self.owner,
            is_public=True,
        )
        self.edit_url = reverse('exercises:workout_edit', kwargs={'slug': self.workout.slug})
        self.delete_url = reverse('exercises:workout_delete', kwargs={'slug': self.workout.slug})

    def _formset_data(self, **overrides):
        data = {
            'title': 'Mi rutina editada',
            'description': 'Descripción nueva',
            'difficulty': 'intermediate',
            'estimated_duration': 45,
            'is_public': 'on',
            'exercises-TOTAL_FORMS': '0',
            'exercises-INITIAL_FORMS': '0',
            'exercises-MIN_NUM_FORMS': '0',
            'exercises-MAX_NUM_FORMS': '1000',
        }
        data.update(overrides)
        return data

    def test_owner_can_edit_workout(self):
        self.client.login(username='owner', password='password123')
        response = self.client.post(self.edit_url, self._formset_data())
        self.assertEqual(response.status_code, 302)
        self.workout.refresh_from_db()
        self.assertEqual(self.workout.title, 'Mi rutina editada')
        self.assertEqual(self.workout.difficulty, 'intermediate')

    def test_non_owner_cannot_edit_workout(self):
        self.client.login(username='other', password='password123')
        response = self.client.get(self.edit_url)
        self.assertEqual(response.status_code, 404)

    def test_owner_can_delete_workout(self):
        self.client.login(username='owner', password='password123')
        response = self.client.post(self.delete_url)
        self.assertRedirects(response, reverse('exercises:workout_list'))
        self.assertFalse(Workout.objects.filter(pk=self.workout.pk).exists())

    def test_non_owner_cannot_delete_workout(self):
        self.client.login(username='other', password='password123')
        response = self.client.post(self.delete_url)
        self.assertEqual(response.status_code, 404)
        self.assertTrue(Workout.objects.filter(pk=self.workout.pk).exists())

    def test_delete_requires_post(self):
        self.client.login(username='owner', password='password123')
        response = self.client.get(self.delete_url)
        self.assertEqual(response.status_code, 405)
        self.assertTrue(Workout.objects.filter(pk=self.workout.pk).exists())


class DashboardTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='dashuser', password='password123')
        self.other = User.objects.create_user(username='otheruser', password='password123')
        self.mine = Workout.objects.create(
            title='Rutina mía', description='x', difficulty='beginner',
            estimated_duration=20, created_by=self.user, is_public=False,
        )
        self.foreign = Workout.objects.create(
            title='Rutina ajena', description='x', difficulty='beginner',
            estimated_duration=20, created_by=self.other, is_public=True,
        )

    def test_dashboard_lists_only_own_workouts(self):
        self.client.login(username='dashuser', password='password123')
        response = self.client.get(reverse('exercises:dashboard'))
        workouts = list(response.context['my_workouts'])
        self.assertIn(self.mine, workouts)
        self.assertNotIn(self.foreign, workouts)

    def test_dashboard_stats_reflect_logs(self):
        WorkoutLog.objects.create(
            user=self.user, workout=self.mine, duration_minutes=25, rpe=7,
        )
        WorkoutLog.objects.create(
            user=self.user, workout=self.mine, duration_minutes=35, rpe=9,
        )
        WorkoutLog.objects.create(user=self.other, workout=self.foreign, rpe=1)

        self.client.login(username='dashuser', password='password123')
        response = self.client.get(reverse('exercises:dashboard'))

        self.assertEqual(response.context['total_workouts'], 2)
        self.assertEqual(response.context['sessions_this_week'], 2)
        self.assertEqual(response.context['streak_days'], 1)
        self.assertEqual(response.context['total_minutes'], 60)
        self.assertEqual(response.context['avg_rpe'], 8.0)
        chart = response.context['weekly_chart']
        self.assertEqual(len(chart), 8)
        self.assertEqual(chart[-1]['count'], 2)

    def test_dashboard_stats_empty_history(self):
        self.client.login(username='dashuser', password='password123')
        response = self.client.get(reverse('exercises:dashboard'))
        self.assertEqual(response.context['total_workouts'], 0)
        self.assertEqual(response.context['streak_days'], 0)
        self.assertEqual(response.context['total_minutes'], 0)
        self.assertIsNone(response.context['avg_rpe'])

    def test_dashboard_rpe_chart(self):
        WorkoutLog.objects.create(user=self.user, workout=self.mine, rpe=7)
        WorkoutLog.objects.create(user=self.user, workout=self.mine, rpe=9)
        self.client.login(username='dashuser', password='password123')
        response = self.client.get(reverse('exercises:dashboard'))
        rpe_chart = response.context['rpe_chart']
        self.assertEqual(len(rpe_chart), 8)
        # La última semana debería tener promedio 8.0
        self.assertEqual(rpe_chart[-1]['avg'], 8.0)

    def test_dashboard_personal_records(self):
        WorkoutLog.objects.create(
            user=self.user, workout=self.mine, duration_minutes=45,
            kettlebell_weight=20, rpe=8,
        )
        WorkoutLog.objects.create(
            user=self.user, workout=self.mine, duration_minutes=30,
            kettlebell_weight=16, rpe=6,
        )
        self.client.login(username='dashuser', password='password123')
        response = self.client.get(reverse('exercises:dashboard'))
        prs = response.context['personal_records']
        self.assertEqual(prs['max_weight'], 20.0)
        self.assertEqual(prs['longest_session'], 45)
        self.assertEqual(prs['best_week'], 2)

    def test_dashboard_personal_records_empty(self):
        self.client.login(username='dashuser', password='password123')
        response = self.client.get(reverse('exercises:dashboard'))
        prs = response.context['personal_records']
        self.assertNotIn('max_weight', prs)
        self.assertNotIn('longest_session', prs)
        self.assertEqual(prs['best_streak'], 0)
        self.assertEqual(prs['best_week'], 0)

    def test_dashboard_legacy_aggregate_history_is_not_used_as_suggestion(self):
        from datetime import timedelta

        from django.utils import timezone
        now = timezone.now()
        WorkoutLog.objects.create(
            user=self.user, workout=self.mine, kettlebell_weight=16,
        )
        # Crear el segundo log con completed_at explícito para asegurar orden
        log2 = WorkoutLog.objects.create(
            user=self.user, workout=self.mine, kettlebell_weight=20,
        )
        WorkoutLog.objects.filter(pk=log2.pk).update(completed_at=now + timedelta(seconds=1))
        self.client.login(username='dashuser', password='password123')
        response = self.client.get(reverse('exercises:dashboard'))
        # Un peso agregado de la rutina no identifica el ejercicio que debe
        # progresar y no debe aparecer como recomendación global.
        self.assertIsNone(response.context['suggested_weight'])
        self.assertIsNone(response.context['suggested_weight_exercise'])

    def test_dashboard_suggested_weight_comes_from_latest_exercise(self):
        exercise = Exercise.objects.create(
            name='Peso muerto del dashboard',
            description='x',
            category='strength',
            difficulty='beginner',
        )
        workout_exercise = WorkoutExercise.objects.create(
            workout=self.mine,
            exercise=exercise,
            order=1,
            sets=3,
            reps='10 reps',
        )
        UserProfile.objects.create(
            user=self.user,
            level='intermediate',
            available_weights='8, 12, 16',
        )
        first_log = WorkoutLog.objects.create(user=self.user, workout=self.mine, rpe=6)
        ExercisePerformance.objects.create(
            user=self.user,
            workout_log=first_log,
            workout_exercise=workout_exercise,
            exercise=exercise,
            completed=True,
            sets_completed=3,
            reps_completed=10,
            weight=8,
            rpe=6,
        )
        second_log = WorkoutLog.objects.create(user=self.user, workout=self.mine, rpe=6)
        ExercisePerformance.objects.create(
            user=self.user,
            workout_log=second_log,
            workout_exercise=workout_exercise,
            exercise=exercise,
            completed=True,
            sets_completed=3,
            reps_completed=10,
            weight=12,
            rpe=6,
        )

        self.client.login(username='dashuser', password='password123')
        response = self.client.get(reverse('exercises:dashboard'))

        self.assertEqual(response.context['suggested_weight'], 16.0)
        self.assertEqual(response.context['suggested_weight_exercise'], exercise)
        self.assertContains(response, 'Peso sugerido · Peso muerto del dashboard')

    def test_dashboard_hard_latest_exercise_does_not_fallback_upward(self):
        exercise = Exercise.objects.create(
            name='Press pesado del dashboard',
            description='x',
            category='strength',
            difficulty='beginner',
        )
        workout_exercise = WorkoutExercise.objects.create(
            workout=self.mine,
            exercise=exercise,
            order=1,
            sets=3,
            reps='10 reps',
        )
        UserProfile.objects.create(user=self.user, available_weights='8, 12')
        log = WorkoutLog.objects.create(user=self.user, workout=self.mine, rpe=9)
        ExercisePerformance.objects.create(
            user=self.user,
            workout_log=log,
            workout_exercise=workout_exercise,
            exercise=exercise,
            completed=True,
            sets_completed=3,
            reps_completed=10,
            weight=4,
            rpe=9,
        )

        self.client.login(username='dashuser', password='password123')
        response = self.client.get(reverse('exercises:dashboard'))

        self.assertIsNone(response.context['suggested_weight'])
        self.assertIsNone(response.context['suggested_weight_exercise'])
        self.assertContains(response, 'Siguiente: registra peso')

    def test_dashboard_suggested_weight_from_profile(self):
        UserProfile.objects.create(user=self.user, level='intermediate', available_weights='8, 12, 16')
        self.client.login(username='dashuser', password='password123')
        response = self.client.get(reverse('exercises:dashboard'))
        # Sin historial, fallback al perfil: intermediate -> index 1 -> 12
        self.assertEqual(response.context['suggested_weight'], 12.0)
        self.assertIsNone(response.context['suggested_weight_exercise'])

    def test_dashboard_suggested_weight_none_without_data(self):
        self.client.login(username='dashuser', password='password123')
        response = self.client.get(reverse('exercises:dashboard'))
        self.assertIsNone(response.context['suggested_weight'])


class WorkoutLogApiTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='loguser', password='password123')
        self.workout = Workout.objects.create(
            title='Rutina log', description='x', difficulty='beginner',
            estimated_duration=20, created_by=self.user, is_public=False,
        )
        self.url = reverse('exercises:log_workout')
        self.client.login(username='loguser', password='password123')

    def _log(self, payload):
        return self.client.post(self.url, json.dumps(payload), content_type='application/json')

    def test_log_with_metrics(self):
        response = self._log({
            'workout_id': self.workout.id,
            'duration_minutes': 32,
            'kettlebell_weight': 16.5,
            'rpe': 8,
            'notes': 'Buen ritmo, subir peso la próxima.',
        })
        self.assertEqual(response.status_code, 200)
        log = WorkoutLog.objects.get(user=self.user)
        self.assertEqual(log.duration_minutes, 32)
        self.assertEqual(float(log.kettlebell_weight), 16.5)
        self.assertEqual(log.rpe, 8)
        self.assertEqual(log.notes, 'Buen ritmo, subir peso la próxima.')

    def test_log_without_metrics_still_works(self):
        response = self._log({'workout_id': self.workout.id})
        self.assertEqual(response.status_code, 200)
        log = WorkoutLog.objects.get(user=self.user)
        self.assertIsNone(log.duration_minutes)
        self.assertIsNone(log.rpe)
        self.assertEqual(log.notes, '')

    def test_session_player_renders_with_metrics_form(self):
        response = self.client.get(
            reverse('exercises:workout_session', kwargs={'slug': self.workout.slug})
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="metrics-form"')
        self.assertContains(response, 'id="rpe-scale"')

    def test_log_rejects_invalid_metrics(self):
        for payload in (
            {'workout_id': self.workout.id, 'rpe': 11},
            {'workout_id': self.workout.id, 'rpe': 0},
            {'workout_id': self.workout.id, 'duration_minutes': 'mucho'},
            {'workout_id': self.workout.id, 'kettlebell_weight': -4},
            {'workout_id': self.workout.id, 'notes': 'x' * 301},
        ):
            response = self._log(payload)
            self.assertEqual(response.status_code, 400, payload)
        self.assertEqual(WorkoutLog.objects.count(), 0)


class ExercisePerformanceApiTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(username='performanceuser', password='password123')
        self.other = User.objects.create_user(username='otherperformance', password='password123')
        self.exercise = Exercise.objects.create(
            name='Press de prueba', description='x', category='strength', difficulty='beginner',
        )
        self.workout = Workout.objects.create(
            title='Rutina detallada', description='x', difficulty='beginner',
            estimated_duration=20, created_by=self.user, is_public=False,
        )
        self.workout_exercise = WorkoutExercise.objects.create(
            workout=self.workout, exercise=self.exercise, order=1, sets=3, reps='10 reps',
        )
        self.url = reverse('exercises:log_workout')
        self.client.login(username='performanceuser', password='password123')

    def _log(self, payload):
        return self.client.post(self.url, json.dumps(payload), content_type='application/json')

    def test_detailed_log_creates_performance_and_aggregates_metrics(self):
        response = self._log({
            'workout_id': self.workout.id,
            'duration_minutes': 25,
            'exercise_logs': [{
                'workout_exercise_id': self.workout_exercise.id,
                'completed': True,
                'sets_completed': 3,
                'reps_completed': 10,
                'weight': 16,
                'rpe': 6,
            }],
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['performance_count'], 1)
        log = WorkoutLog.objects.get(user=self.user)
        self.assertEqual(float(log.kettlebell_weight), 16.0)
        self.assertEqual(log.rpe, 6)
        performance = ExercisePerformance.objects.get(workout_log=log)
        self.assertEqual(performance.exercise, self.exercise)
        self.assertEqual(performance.sets_completed, 3)
        self.assertEqual(performance.reps_completed, 10)
        self.assertEqual(performance.volume, 480.0)

    def test_detailed_log_rejects_exercise_outside_workout(self):
        other_workout = Workout.objects.create(
            title='Otra rutina', description='x', difficulty='beginner',
            estimated_duration=20, created_by=self.user, is_public=False,
        )
        foreign_item = WorkoutExercise.objects.create(
            workout=other_workout, exercise=self.exercise, order=1, sets=3, reps='10 reps',
        )
        response = self._log({
            'workout_id': self.workout.id,
            'exercise_logs': [{'workout_exercise_id': foreign_item.id, 'weight': 16}],
        })
        self.assertEqual(response.status_code, 400)
        self.assertFalse(WorkoutLog.objects.exists())
        self.assertFalse(ExercisePerformance.objects.exists())

    def test_client_session_id_is_idempotent(self):
        client_session_id = str(uuid.uuid4())
        payload = {
            'workout_id': self.workout.id,
            'client_session_id': client_session_id,
            'exercise_logs': [{
                'workout_exercise_id': self.workout_exercise.id,
                'completed': True,
                'sets_completed': 3,
                'reps_completed': 10,
                'weight': 12,
            }],
        }
        first = self._log(payload)
        second = self._log(payload)
        self.assertEqual(first.status_code, 200)
        self.assertTrue(first.json()['created'])
        self.assertEqual(second.status_code, 200)
        self.assertFalse(second.json()['created'])
        self.assertEqual(WorkoutLog.objects.count(), 1)
        self.assertEqual(ExercisePerformance.objects.count(), 1)


class ExerciseProgressionTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='progressionuser', password='password123')
        self.other = User.objects.create_user(username='otherprogression', password='password123')
        UserProfile.objects.create(user=self.user, level='intermediate', available_weights='8, 12, 16')
        self.exercise = Exercise.objects.create(
            name='Sentadilla de progreso', description='x', category='strength', difficulty='beginner',
        )
        self.workout = Workout.objects.create(
            title='Rutina de progreso', description='x', difficulty='beginner',
            estimated_duration=20, created_by=self.user, is_public=True,
        )
        self.workout_exercise = WorkoutExercise.objects.create(
            workout=self.workout, exercise=self.exercise, order=1, sets=3, reps='10 reps',
        )

    def _performance(self, user, weight, rpe, completed=True, workout=None):
        workout = workout or self.workout
        log = WorkoutLog.objects.create(user=user, workout=workout, rpe=rpe)
        return ExercisePerformance.objects.create(
            user=user,
            workout_log=log,
            workout_exercise=self.workout_exercise,
            exercise=self.exercise,
            completed=completed,
            sets_completed=3,
            reps_completed=10,
            weight=weight,
            rpe=rpe,
        )

    def test_easy_rpe_progresses_one_available_weight(self):
        self._performance(self.user, 8, 6)
        self._performance(self.user, 12, 6)
        recommendation = recommend_exercise_progression(self.user, self.exercise)
        self.assertEqual(recommendation['suggested_weight'], 16.0)
        self.assertEqual(recommendation['status'], 'progress')

    def test_one_easy_session_is_not_enough_to_increase_weight(self):
        self._performance(self.user, 12, 6)
        recommendation = recommend_exercise_progression(self.user, self.exercise)
        self.assertEqual(recommendation['suggested_weight'], 12.0)
        self.assertEqual(recommendation['status'], 'maintain')

    def test_hard_rpe_recovers_one_available_weight(self):
        self._performance(self.user, 16, 9)
        recommendation = recommend_exercise_progression(self.user, self.exercise)
        self.assertEqual(recommendation['suggested_weight'], 12.0)
        self.assertEqual(recommendation['status'], 'deload')

    def test_recommendation_stays_inside_current_profile_inventory(self):
        self.user.profile.available_weights = '8, 12'
        self.user.profile.save()
        self._performance(self.user, 8, 6)
        self._performance(self.user, 16, 6)
        recommendation = recommend_exercise_progression(self.user, self.exercise)
        self.assertEqual(recommendation['suggested_weight'], 12.0)

    def test_moderate_rpe_uses_equal_or_lower_inventory_weight(self):
        self._performance(self.user, 10, 8)
        recommendation = recommend_exercise_progression(self.user, self.exercise)
        self.assertEqual(recommendation['suggested_weight'], 8.0)
        self.assertEqual(recommendation['status'], 'maintain')

    def test_moderate_rpe_does_not_fallback_upward_when_inventory_is_heavier(self):
        self._performance(self.user, 7, 8)
        recommendation = recommend_exercise_progression(self.user, self.exercise)
        self.assertIsNone(recommendation['suggested_weight'])
        self.assertEqual(recommendation['status'], 'maintain')
        self.assertIn('igual o menor', recommendation['reason'])

    def test_other_user_history_is_not_used(self):
        self._performance(self.other, 16, 6)
        recommendation = recommend_exercise_progression(self.user, self.exercise)
        self.assertEqual(recommendation['history_count'], 0)
        self.assertEqual(recommendation['suggested_weight'], 12.0)
        self.assertEqual(recommendation['status'], 'new')

    def test_detail_progress_summary_tracks_sessions_and_volume(self):
        self._performance(self.user, 12, 6)
        second_workout = Workout.objects.create(
            title='Rutina de progreso 2', description='x', difficulty='beginner',
            estimated_duration=20, created_by=self.user, is_public=True,
        )
        second_item = WorkoutExercise.objects.create(
            workout=second_workout, exercise=self.exercise, order=1, sets=3, reps='10 reps',
        )
        second_log = WorkoutLog.objects.create(user=self.user, workout=second_workout, rpe=7)
        ExercisePerformance.objects.create(
            user=self.user, workout_log=second_log, workout_exercise=second_item,
            exercise=self.exercise, sets_completed=3, reps_completed=10,
            weight=16, rpe=7,
        )
        summary = build_exercise_progress(self.user, self.exercise)
        self.assertEqual(summary['sessions'], 2)
        self.assertEqual(summary['max_weight'], 16.0)
        self.assertEqual(summary['best_volume'], 480.0)
        self.assertEqual(summary['recommendation']['suggested_weight'], 16.0)

    def test_session_and_detail_render_exercise_progression(self):
        self.client.login(username='progressionuser', password='password123')
        session_response = self.client.get(
            reverse('exercises:workout_session', kwargs={'slug': self.workout.slug})
        )
        self.assertEqual(session_response.status_code, 200)
        self.assertContains(session_response, f'data-workout-exercise-id="{self.workout_exercise.id}"')
        self.assertContains(session_response, '12 kg sugeridos')

        detail_response = self.client.get(
            reverse('exercises:detail', kwargs={'slug': self.exercise.slug})
        )
        self.assertEqual(detail_response.status_code, 200)
        self.assertContains(detail_response, 'Progreso en este ejercicio')


class HistoryProgressTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='historyuser', password='password123')
        self.other = User.objects.create_user(username='otherhistory', password='password123')
        UserProfile.objects.create(
            user=self.user,
            level='intermediate',
            goal='strength',
            available_weights='8, 12, 16',
        )
        self.exercise = Exercise.objects.create(
            name='Press de historial',
            description='x',
            category='strength',
            difficulty='beginner',
        )
        self.workout = Workout.objects.create(
            title='Rutina de historial',
            description='x',
            difficulty='beginner',
            estimated_duration=30,
            created_by=self.user,
            is_public=False,
        )
        self.workout_exercise = WorkoutExercise.objects.create(
            workout=self.workout,
            exercise=self.exercise,
            order=1,
            sets=3,
            reps='10 reps',
        )
        self.client.login(username='historyuser', password='password123')

    def _log(self, days_ago=0, details=True, weight=12, rpe=6, planned_session=None):
        log = WorkoutLog.objects.create(
            user=self.user,
            workout=self.workout,
            planned_session=planned_session,
            duration_minutes=30,
            kettlebell_weight=weight,
            rpe=rpe,
            notes='Registro original',
        )
        WorkoutLog.objects.filter(pk=log.pk).update(
            completed_at=timezone.now() - timedelta(days=days_ago),
        )
        if details:
            ExercisePerformance.objects.create(
                user=self.user,
                workout_log=log,
                workout_exercise=self.workout_exercise,
                exercise=self.exercise,
                completed=True,
                sets_completed=3,
                reps_completed=10,
                weight=weight,
                rpe=rpe,
                notes='Detalle original',
            )
        log.refresh_from_db()
        return log

    def _plan_session(self):
        today = timezone.localdate()
        plan = TrainingPlan.objects.create(
            user=self.user,
            goal='strength',
            level='intermediate',
            sessions_per_week=2,
            session_duration=30,
            preferred_weekdays=[today.weekday(), (today.weekday() + 2) % 7],
            start_date=today,
            end_date=today + timedelta(days=27),
        )
        return PlannedSession.objects.create(
            plan=plan,
            sequence=1,
            week_number=1,
            scheduled_date=today,
            focus='strength',
            session_kind='main',
            phase='base',
            estimated_duration=30,
            status='completed',
        )

    def _edit_payload(self, get_response, **overrides):
        formset = get_response.context['performance_formset']
        data = {
            'duration_minutes': '45',
            'rpe': '7',
            'notes': 'Corrección revisada',
            'performances-TOTAL_FORMS': str(formset.total_form_count()),
            'performances-INITIAL_FORMS': str(formset.initial_form_count()),
            'performances-MIN_NUM_FORMS': '0',
            'performances-MAX_NUM_FORMS': '1000',
        }
        for index, form in enumerate(formset.forms):
            data.update({
                f'performances-{index}-id': str(form.instance.id),
                f'performances-{index}-completed': 'on',
                f'performances-{index}-sets_completed': '2',
                f'performances-{index}-reps_completed': '8',
                f'performances-{index}-weight': '16',
                f'performances-{index}-rpe': '7',
                f'performances-{index}-notes': 'Detalle corregido',
            })
        data.update(overrides)
        return data

    def test_progress_overview_requires_authentication(self):
        self.client.logout()
        response = self.client.get(reverse('exercises:progress_overview'))
        self.assertRedirects(
            response,
            f"{reverse('exercises:login')}?next={reverse('exercises:progress_overview')}",
        )

    def test_progress_overview_filters_and_paginates_private_history(self):
        for index in range(13):
            self._log(days_ago=index % 5)
        self._log(days_ago=45, weight=8)
        planned = self._plan_session()
        self._log(days_ago=2, planned_session=planned)

        response = self.client.get(reverse('exercises:progress_overview'), {
            'period': '30',
            'source': 'standalone',
            'exercise': str(self.exercise.id),
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['history_page'].paginator.count, 13)
        self.assertEqual(len(response.context['history_page'].object_list), 12)
        self.assertTrue(response.context['history_page'].has_next())
        self.assertContains(response, 'Historial y progreso')
        self.assertContains(response, 'Rutina de historial')
        self.assertNotContains(response, 'Resultados anteriores')

    def test_weekly_review_uses_goal_and_same_elapsed_days(self):
        today = timezone.localdate()
        current_offset = 0 if today.weekday() == 0 else 1
        self._log(days_ago=current_offset, weight=16)
        self._log(days_ago=current_offset + 7, weight=8)

        review = build_weekly_review(self.user, today=today)
        self.assertEqual(review['current']['sessions'], 1)
        self.assertEqual(review['previous']['sessions'], 1)
        self.assertEqual(review['current']['total_volume'], 480.0)
        self.assertEqual(review['goal_highlight']['goal'], 'strength')
        self.assertEqual(review['goal_highlight']['label'], 'Volumen total')
        self.assertEqual(review['goal_highlight']['delta'], 240.0)

    def test_detail_shows_legacy_snapshot_without_performances(self):
        log = self._log(details=False, weight=8)
        self.workout.delete()
        response = self.client.get(
            reverse('exercises:progress_session_detail', kwargs={'log_id': log.id}),
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Rutina de historial')
        self.assertContains(response, 'registro es anterior al detalle por ejercicio')

    def test_detail_and_edit_are_isolated_by_user(self):
        log = self._log()
        other_workout = Workout.objects.create(
            title='Rutina ajena',
            description='x',
            difficulty='beginner',
            estimated_duration=20,
            created_by=self.other,
            is_public=False,
        )
        other_log = WorkoutLog.objects.create(user=self.other, workout=other_workout)
        for name, kwargs in (
            ('progress_session_detail', {'log_id': other_log.id}),
            ('progress_session_edit', {'log_id': other_log.id}),
        ):
            response = self.client.get(reverse(f'exercises:{name}', kwargs=kwargs))
            self.assertEqual(response.status_code, 404)
        self.assertEqual(
            self.client.get(
                reverse('exercises:progress_session_detail', kwargs={'log_id': log.id}),
            ).status_code,
            200,
        )

    def test_edit_updates_summary_and_details_without_changing_identity(self):
        log = self._log(weight=12)
        original_completed_at = log.completed_at
        original_workout_id = log.workout_id
        edit_url = reverse('exercises:progress_session_edit', kwargs={'log_id': log.id})
        get_response = self.client.get(edit_url)
        response = self.client.post(edit_url, self._edit_payload(get_response))
        self.assertRedirects(
            response,
            reverse('exercises:progress_session_detail', kwargs={'log_id': log.id}),
        )

        log.refresh_from_db()
        performance = ExercisePerformance.objects.get(workout_log=log)
        self.assertEqual(log.duration_minutes, 45)
        self.assertEqual(log.rpe, 7)
        self.assertEqual(log.notes, 'Corrección revisada')
        self.assertEqual(float(log.kettlebell_weight), 16.0)
        self.assertEqual(performance.sets_completed, 2)
        self.assertEqual(performance.reps_completed, 8)
        self.assertEqual(float(performance.weight), 16.0)
        self.assertIsNotNone(log.edited_at)
        self.assertEqual(log.completed_at, original_completed_at)
        self.assertEqual(log.workout_id, original_workout_id)

    def test_invalid_edit_is_atomic(self):
        log = self._log(weight=12)
        edit_url = reverse('exercises:progress_session_edit', kwargs={'log_id': log.id})
        get_response = self.client.get(edit_url)
        response = self.client.post(
            edit_url,
            self._edit_payload(get_response, **{'performances-0-weight': '999'}),
        )
        self.assertEqual(response.status_code, 200)
        log.refresh_from_db()
        performance = ExercisePerformance.objects.get(workout_log=log)
        self.assertEqual(log.duration_minutes, 30)
        self.assertIsNone(log.edited_at)
        self.assertEqual(float(performance.weight), 12.0)

    def test_legacy_edit_allows_general_weight(self):
        log = self._log(details=False, weight=8)
        edit_url = reverse('exercises:progress_session_edit', kwargs={'log_id': log.id})
        response = self.client.post(edit_url, {
            'duration_minutes': '25',
            'rpe': '5',
            'kettlebell_weight': '10',
            'notes': 'Sesión antigua corregida',
            'performances-TOTAL_FORMS': '0',
            'performances-INITIAL_FORMS': '0',
            'performances-MIN_NUM_FORMS': '0',
            'performances-MAX_NUM_FORMS': '1000',
        })
        self.assertRedirects(
            response,
            reverse('exercises:progress_session_detail', kwargs={'log_id': log.id}),
        )
        log.refresh_from_db()
        self.assertEqual(log.duration_minutes, 25)
        self.assertEqual(float(log.kettlebell_weight), 10.0)
        self.assertIsNotNone(log.edited_at)


class AdaptivePlanTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='planuser', password='password123')
        UserProfile.objects.create(
            user=self.user,
            level='beginner',
            goal='strength',
            available_weights='8, 12, 16',
        )
        self.exercises = []
        for category in ('strength', 'cardio', 'flexibility', 'full_body'):
            for index in range(2):
                self.exercises.append(Exercise.objects.create(
                    name=f'Plan {category} {index}',
                    description='x',
                    category=category,
                    difficulty='beginner',
                ))

    def _data(self, **overrides):
        data = {
            'level': 'beginner',
            'goal': 'strength',
            'available_weights': '8, 12, 16',
            'sessions_per_week': 3,
            'preferred_weekdays': ['0', '2', '4'],
            'session_duration': 30,
            'start_date': timezone.localdate().isoformat(),
            'reminders_enabled': False,
            'reminder_time': '19:00',
        }
        data.update(overrides)
        return data

    def test_schedule_creates_four_weeks_with_unique_dates(self):
        rows = build_schedule(
            timezone.localdate(), 'strength', 3, [0, 2, 4], 'beginner', 30,
        )
        self.assertEqual(len(rows), 12)
        self.assertEqual(len({row['scheduled_date'] for row in rows}), 12)
        self.assertEqual([row['phase'] for row in rows[::3]], ['base', 'base', 'build', 'deload'])
        self.assertEqual([row['session_kind'] for row in rows[:3]], ['main', 'main', 'recovery'])

    def test_schedule_preserves_weekdays_when_start_is_not_monday(self):
        today = timezone.localdate()
        start = today + timedelta(days=(2 - today.weekday()) % 7)
        rows = build_schedule(start, 'strength', 3, [0, 2, 4], 'beginner', 30)
        self.assertEqual(
            [row['scheduled_date'].weekday() for row in rows[:3]],
            [2, 4, 0],
        )

    def test_create_plan_view_persists_profile_and_calendar(self):
        self.client.login(username='planuser', password='password123')
        response = self.client.post(reverse('exercises:plan_create'), self._data())
        self.assertEqual(response.status_code, 302)
        plan = TrainingPlan.objects.get(user=self.user)
        self.assertEqual(plan.sessions_per_week, 3)
        self.assertEqual(plan.sessions.count(), 12)
        self.assertEqual(self.user.profile.goal, 'strength')

    def test_prepare_without_readiness_only_shows_check(self):
        plan, _ = create_training_plan(self.user, {
            **self._data(),
            'preferred_weekdays': [0, 2, 4],
            'start_date': timezone.localdate(),
        })
        session = plan.sessions.first()
        self.client.login(username='planuser', password='password123')
        response = self.client.post(
            reverse('exercises:plan_session_prepare', kwargs={'session_id': session.id}),
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Ajustemos tu sesión de hoy')
        session.refresh_from_db()
        self.assertIsNone(session.workout_id)

    def test_readiness_stop_does_not_materialize_workout(self):
        plan, _ = create_training_plan(self.user, {
            **self._data(),
            'preferred_weekdays': [0, 2, 4],
            'start_date': timezone.localdate(),
        })
        session = plan.sessions.first()
        self.client.login(username='planuser', password='password123')
        response = self.client.post(
            reverse('exercises:plan_session_prepare', kwargs={'session_id': session.id}),
            {'energy_level': 3, 'pain_level': 'stop', 'available_minutes': 30},
        )
        self.assertEqual(response.status_code, 302)
        session.refresh_from_db()
        self.assertIsNone(session.workout_id)
        self.assertIsNotNone(session.readiness_checked_at)
        self.assertIn('dolor', session.adaptation_reason)

    def test_readiness_stop_removes_unstarted_plan_routine(self):
        plan, _ = create_training_plan(self.user, {
            **self._data(),
            'preferred_weekdays': [0, 2, 4],
            'start_date': timezone.localdate(),
        })
        session = plan.sessions.first()
        prepare_planned_session(
            self.user,
            session,
            readiness={'energy_level': 3, 'pain_level': 'none', 'available_minutes': 30},
        )
        session.refresh_from_db()
        old_workout_id = session.workout_id
        self.client.login(username='planuser', password='password123')
        response = self.client.post(
            reverse('exercises:plan_session_prepare', kwargs={'session_id': session.id}),
            {'energy_level': 3, 'pain_level': 'stop', 'available_minutes': 30},
        )
        self.assertEqual(response.status_code, 302)
        session.refresh_from_db()
        self.assertIsNone(session.workout_id)
        self.assertFalse(Workout.objects.filter(pk=old_workout_id).exists())

    def test_low_readiness_shortens_session_and_lowers_volume(self):
        plan, _ = create_training_plan(self.user, {
            **self._data(),
            'preferred_weekdays': [0, 2, 4],
            'start_date': timezone.localdate(),
        })
        session = plan.sessions.first()
        self.client.login(username='planuser', password='password123')
        response = self.client.post(
            reverse('exercises:plan_session_prepare', kwargs={'session_id': session.id}),
            {'energy_level': 2, 'pain_level': 'none', 'available_minutes': 15},
        )
        self.assertEqual(response.status_code, 302)
        session.refresh_from_db()
        self.assertIsNotNone(session.workout_id)
        self.assertEqual(session.workout.estimated_duration, 15)
        self.assertIn('reducimos volumen', session.adaptation_reason)
        self.assertIn('acortada a 15 min', session.adaptation_reason)

    def test_planned_log_rejects_weight_outside_profile_inventory(self):
        plan, _ = create_training_plan(self.user, {
            **self._data(),
            'preferred_weekdays': [0, 2, 4],
            'start_date': timezone.localdate(),
        })
        session = plan.sessions.first()
        prepare_planned_session(
            self.user,
            session,
            readiness={'energy_level': 3, 'pain_level': 'none', 'available_minutes': 30},
        )
        self.client.login(username='planuser', password='password123')
        response = self.client.post(
            reverse('exercises:log_workout'),
            data=json.dumps({
                'workout_id': session.workout_id,
                'planned_session_id': session.id,
                'kettlebell_weight': 24,
            }),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(WorkoutLog.objects.filter(planned_session=session).exists())

    def test_plan_dashboard_and_detail_render(self):
        plan, _ = create_training_plan(self.user, {
            **self._data(),
            'preferred_weekdays': [0, 2, 4],
            'start_date': timezone.localdate(),
        })
        self.client.login(username='planuser', password='password123')
        dashboard = self.client.get(reverse('exercises:dashboard'))
        detail = self.client.get(reverse('exercises:plan_detail', kwargs={'plan_id': plan.id}))
        self.assertEqual(dashboard.status_code, 200)
        self.assertContains(dashboard, 'Ver mi plan')
        self.assertEqual(detail.status_code, 200)
        self.assertContains(detail, 'Tus sesiones')
        self.assertContains(detail, 'Semana 1')

    def test_public_page_cache_is_private_for_authenticated_users(self):
        anonymous = self.client.get(reverse('exercises:landing'))
        self.assertEqual(anonymous.headers['X-KB-Public-Cache'], '1')
        self.assertIn('public', anonymous.headers['Cache-Control'])

        self.client.login(username='planuser', password='password123')
        authenticated = self.client.get(reverse('exercises:landing'))
        self.assertEqual(authenticated.headers['X-KB-Public-Cache'], '0')
        self.assertIn('no-store', authenticated.headers['Cache-Control'])
        self.assertEqual(authenticated.headers['Pragma'], 'no-cache')

    def test_authenticated_api_response_is_not_cacheable(self):
        self.client.login(username='planuser', password='password123')
        response = self.client.post(
            reverse('exercises:push_subscription'),
            data=json.dumps({'endpoint': '', 'keys': {}}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn('no-store', response.headers['Cache-Control'])
        self.assertEqual(response.headers['Pragma'], 'no-cache')

    def test_prepare_session_and_log_complete_plan_session(self):
        plan, _ = create_training_plan(self.user, {
            **self._data(),
            'preferred_weekdays': [0, 2, 4],
            'start_date': timezone.localdate(),
        })
        session = plan.sessions.first()
        self.client.login(username='planuser', password='password123')
        response = self.client.post(
            reverse('exercises:plan_session_prepare', kwargs={'session_id': session.id}),
            {
                'energy_level': 3,
                'pain_level': 'none',
                'available_minutes': 30,
            },
        )
        self.assertEqual(response.status_code, 302)
        session.refresh_from_db()
        self.assertIsNotNone(session.workout_id)
        self.assertEqual(session.energy_level, 3)
        payload = {
            'workout_id': session.workout_id,
            'planned_session_id': session.id,
            'client_session_id': str(uuid.uuid4()),
            'duration_minutes': 25,
            'rpe': 6,
        }
        logged = self.client.post(
            reverse('exercises:log_workout'),
            data=json.dumps(payload),
            content_type='application/json',
        )
        self.assertEqual(logged.status_code, 200)
        session.refresh_from_db()
        plan.refresh_from_db()
        self.assertEqual(session.status, 'completed')
        self.assertEqual(WorkoutLog.objects.get(planned_session=session).workout_title_snapshot, session.workout.title)
        self.assertEqual(plan.status, 'active')

    def test_deleting_workout_preserves_log_snapshots(self):
        workout = Workout.objects.create(
            title='Rutina histórica', description='x', difficulty='beginner',
            estimated_duration=20, created_by=self.user, is_public=False,
        )
        item = WorkoutExercise.objects.create(
            workout=workout, exercise=self.exercises[0], order=1, sets=3, reps='10 reps',
        )
        log = WorkoutLog.objects.create(
            user=self.user,
            workout=workout,
            workout_title_snapshot=workout.title,
            workout_difficulty_snapshot=workout.difficulty,
            workout_duration_snapshot=workout.estimated_duration,
        )
        performance = ExercisePerformance.objects.create(
            user=self.user,
            workout_log=log,
            workout_exercise=item,
            exercise=self.exercises[0],
            exercise_name_snapshot=self.exercises[0].name,
            exercise_category_snapshot=self.exercises[0].category,
            target_sets=item.sets,
            target_reps=item.reps,
            sets_completed=3,
            reps_completed=10,
            weight=8,
        )
        workout.delete()
        log.refresh_from_db()
        performance.refresh_from_db()
        self.assertIsNone(log.workout)
        self.assertEqual(log.workout_title_snapshot, 'Rutina histórica')
        self.assertIsNone(performance.workout_exercise)
        self.assertEqual(performance.exercise_name_snapshot, self.exercises[0].name)

    def test_private_export_is_not_visible_to_other_user(self):
        workout = Workout.objects.create(
            title='Privada', description='x', difficulty='beginner',
            estimated_duration=20, created_by=self.user, is_public=False,
        )
        User.objects.create_user(username='planother', password='password123')
        self.client.login(username='planother', password='password123')
        response = self.client.get(reverse('exercises:workout_export', kwargs={'slug': workout.slug}))
        self.assertEqual(response.status_code, 404)

    @patch('exercises.management.commands.send_plan_reminders.send_push_to_user', return_value=1)
    def test_plan_reminder_is_sent_once(self, mock_send):
        plan, _ = create_training_plan(self.user, {
            **self._data(),
            'preferred_weekdays': [timezone.localdate().weekday(), (timezone.localdate().weekday() + 2) % 7, (timezone.localdate().weekday() + 4) % 7],
            'start_date': timezone.localdate(),
            'reminders_enabled': True,
            'reminder_time': '00:01',
        })
        first = plan.sessions.get(scheduled_date=timezone.localdate())
        from django.core.management import call_command
        call_command('send_plan_reminders')
        first.refresh_from_db()
        call_command('send_plan_reminders')
        self.assertIsNotNone(first.reminder_sent_at)
        mock_send.assert_called_once()


class BaseWorkoutsTests(TestCase):
    """Las rutinas base sembradas por la migración 0010 deben existir,
    ser públicas y no estar vacías (aunque la BD de test solo tenga los
    pocos ejercicios de la migración 0008)."""

    def test_base_workouts_exist_public_and_non_empty(self):
        base = Workout.objects.filter(created_by__isnull=True, is_public=True)
        self.assertGreaterEqual(base.count(), 1)
        for workout in base:
            self.assertGreater(
                workout.exercises.count(), 0,
                f'La rutina base "{workout.title}" no debería estar vacía',
            )

    def test_base_workouts_visible_to_anonymous(self):
        response = self.client.get(reverse('exercises:workout_list'))
        self.assertEqual(response.status_code, 200)
        self.assertGreaterEqual(len(response.context['workouts']), 1)


class TaxonomyViewTests(TestCase):
    def test_unknown_category_returns_404(self):
        response = self.client.get(
            reverse('exercises:category_detail', kwargs={'category': 'inexistente'})
        )
        self.assertEqual(response.status_code, 404)

    def test_unknown_difficulty_returns_404(self):
        response = self.client.get(
            reverse('exercises:difficulty_detail', kwargs={'difficulty': 'inexistente'})
        )
        self.assertEqual(response.status_code, 404)

    def test_landing_page_renders(self):
        response = self.client.get(reverse('exercises:landing'))
        self.assertEqual(response.status_code, 200)
        self.assertIn('featured_exercises', response.context)

    def test_landing_shows_limited_featured_set(self):
        Exercise.objects.all().delete()
        for i in range(20):
            Exercise.objects.create(
                name=f'Ejercicio landing {i}', description='x',
                category='strength', difficulty='beginner',
            )
        response = self.client.get(reverse('exercises:landing'))
        self.assertLessEqual(len(response.context['featured_exercises']), 8)
        self.assertEqual(response.context['total_exercises'], 20)


class PushSubscriptionTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(username='pushuser', password='password123')
        self.client.login(username='pushuser', password='password123')
        self.save_url = reverse('exercises:push_subscription')
        self.remove_url = reverse('exercises:push_subscription_remove')

    def test_save_push_subscription(self):
        payload = {
            'endpoint': 'https://fcm.googleapis.com/fcm/send/abc123',
            'keys': {'p256dh': 'key1', 'auth': 'auth1'},
        }
        response = self.client.post(
            self.save_url, json.dumps(payload), content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['status'], 'success')
        self.assertTrue(data['created'])
        self.assertTrue(
            PushSubscription.objects.filter(user=self.user, endpoint=payload['endpoint']).exists()
        )

    def test_save_push_subscription_updates_existing(self):
        endpoint = 'https://fcm.googleapis.com/fcm/send/abc123'
        PushSubscription.objects.create(
            user=self.user, endpoint=endpoint, p256dh='old', auth='old'
        )
        payload = {
            'endpoint': endpoint,
            'keys': {'p256dh': 'new_key', 'auth': 'new_auth'},
        }
        response = self.client.post(
            self.save_url, json.dumps(payload), content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()['created'])
        sub = PushSubscription.objects.get(user=self.user, endpoint=endpoint)
        self.assertEqual(sub.p256dh, 'new_key')
        self.assertEqual(sub.auth, 'new_auth')

    def test_save_push_subscription_missing_fields_returns_400(self):
        for payload in (
            {'endpoint': 'https://example.com', 'keys': {}},
            {'endpoint': 'https://example.com', 'keys': {'p256dh': 'k'}},
            {'keys': {'p256dh': 'k', 'auth': 'a'}},
            'not-json',
        ):
            response = self.client.post(
                self.save_url,
                json.dumps(payload) if isinstance(payload, dict) else payload,
                content_type='application/json',
            )
            self.assertEqual(response.status_code, 400, payload)

    def test_save_push_subscription_unauthenticated_redirects(self):
        self.client.logout()
        response = self.client.post(
            self.save_url,
            json.dumps({'endpoint': 'x', 'keys': {'p256dh': 'k', 'auth': 'a'}}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 302)

    def test_remove_push_subscription(self):
        endpoint = 'https://fcm.googleapis.com/fcm/send/abc123'
        PushSubscription.objects.create(
            user=self.user, endpoint=endpoint, p256dh='k', auth='a'
        )
        response = self.client.post(
            self.remove_url, json.dumps({'endpoint': endpoint}), content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['status'], 'success')
        self.assertFalse(
            PushSubscription.objects.filter(user=self.user, endpoint=endpoint).exists()
        )

    def test_remove_push_subscription_invalid_json(self):
        response = self.client.post(
            self.remove_url, 'not-json', content_type='application/json'
        )
        self.assertEqual(response.status_code, 400)

    def test_remove_push_subscription_unauthenticated_redirects(self):
        self.client.logout()
        response = self.client.post(
            self.remove_url,
            json.dumps({'endpoint': 'x'}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 302)

    @patch('pywebpush.webpush')
    @patch.object(django_settings, 'VAPID_PRIVATE_KEY', 'test-key')
    def test_send_test_notification(self, mock_webpush):
        PushSubscription.objects.create(
            user=self.user, endpoint='https://example.com/push',
            p256dh='k', auth='a',
        )
        test_url = reverse('exercises:push_subscription_test')
        response = self.client.post(test_url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['status'], 'success')
        self.assertEqual(response.json()['sent'], 1)
        mock_webpush.assert_called_once()

    @patch.object(django_settings, 'VAPID_PRIVATE_KEY', 'test-key')
    def test_send_test_notification_no_subscriptions(self):
        test_url = reverse('exercises:push_subscription_test')
        response = self.client.post(test_url)
        self.assertEqual(response.status_code, 400)
        self.assertIn('No tienes suscripciones', response.json()['message'])

    def test_send_test_notification_unauthenticated(self):
        self.client.logout()
        test_url = reverse('exercises:push_subscription_test')
        response = self.client.post(test_url)
        self.assertEqual(response.status_code, 302)


class ExerciseAutocompleteTests(TestCase):
    def setUp(self):
        Exercise.objects.all().delete()
        self.ex1 = Exercise.objects.create(
            name='Kettlebell Swing', description='x',
            category='strength', difficulty='intermediate',
            muscles_targeted='Glúteos, core',
        )
        self.ex2 = Exercise.objects.create(
            name='Kettlebell Snatch', description='x',
            category='strength', difficulty='advanced',
            muscles_targeted='Hombros, espalda',
        )
        self.ex3 = Exercise.objects.create(
            name='Goblet Squat', description='x',
            category='strength', difficulty='beginner',
            muscles_targeted='Glúteos, cuádriceps',
        )
        self.url = reverse('exercises:exercise_autocomplete')

    def test_short_query_returns_empty(self):
        response = self.client.get(self.url, {'q': 'k'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['suggestions'], [])

    def test_autocomplete_by_name(self):
        response = self.client.get(self.url, {'q': 'swing'})
        suggestions = response.json()['suggestions']
        self.assertEqual(len(suggestions), 1)
        self.assertEqual(suggestions[0]['name'], 'Kettlebell Swing')
        self.assertEqual(suggestions[0]['slug'], self.ex1.slug)
        self.assertEqual(suggestions[0]['category'], 'Fuerza')
        self.assertEqual(suggestions[0]['difficulty'], 'Intermedio')

    def test_autocomplete_by_muscles(self):
        response = self.client.get(self.url, {'q': 'glúteos'})
        suggestions = response.json()['suggestions']
        names = {s['name'] for s in suggestions}
        self.assertIn('Kettlebell Swing', names)
        self.assertIn('Goblet Squat', names)

    def test_autocomplete_limit_8(self):
        for i in range(10):
            Exercise.objects.create(
                name=f'Ejercicio test {i}', description='x',
                category='strength', difficulty='beginner',
            )
        response = self.client.get(self.url, {'q': 'test'})
        self.assertLessEqual(len(response.json()['suggestions']), 8)

    def test_autocomplete_no_results(self):
        response = self.client.get(self.url, {'q': 'zzz-no-existe'})
        self.assertEqual(response.json()['suggestions'], [])


class ExerciseFiltersTests(TestCase):
    def setUp(self):
        Exercise.objects.all().delete()
        Exercise.objects.create(
            name='Ex1', description='x', category='strength', difficulty='beginner',
            muscles_targeted='Glúteos, core',
        )
        Exercise.objects.create(
            name='Ex2', description='x', category='cardio', difficulty='intermediate',
            muscles_targeted='Hombros\ncore',
        )
        Exercise.objects.create(
            name='Ex3', description='x', category='flexibility', difficulty='advanced',
            muscles_targeted='',
        )
        self.url = reverse('exercises:exercise_filters')

    def test_filters_returns_muscles(self):
        response = self.client.get(self.url)
        data = response.json()
        self.assertIn('Glúteos', data['muscles'])
        self.assertIn('core', data['muscles'])
        self.assertIn('Hombros', data['muscles'])
        # Debe estar ordenado
        self.assertEqual(data['muscles'], sorted(data['muscles']))

    def test_filters_returns_categories_and_difficulties(self):
        response = self.client.get(self.url)
        data = response.json()
        cat_keys = [c[0] for c in data['categories']]
        diff_keys = [d[0] for d in data['difficulties']]
        self.assertIn('strength', cat_keys)
        self.assertIn('cardio', cat_keys)
        self.assertIn('beginner', diff_keys)
        self.assertIn('advanced', diff_keys)

    def test_filters_exercises_without_muscles(self):
        # Ex3 tiene muscles_targeted vacío, no debe aparecer ningún muscle vacío
        response = self.client.get(self.url)
        for muscle in response.json()['muscles']:
            self.assertTrue(len(muscle) > 0)


class WorkoutExportTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='exportuser', password='password123')
        self.ex1 = Exercise.objects.create(
            name='Swing Export', description='x',
            category='strength', difficulty='beginner',
        )
        self.ex2 = Exercise.objects.create(
            name='Squat Export', description='x',
            category='strength', difficulty='beginner',
        )
        self.workout = Workout.objects.create(
            title='Rutina Export', description='Para exportar',
            difficulty='intermediate', estimated_duration=30,
            created_by=self.user, is_public=True,
        )
        WorkoutExercise.objects.create(
            workout=self.workout, exercise=self.ex1, order=1, sets=3, reps='15', notes='Sin pausa'
        )
        WorkoutExercise.objects.create(
            workout=self.workout, exercise=self.ex2, order=2, sets=4, reps='12', notes=''
        )
        self.url = reverse('exercises:workout_export', kwargs={'slug': self.workout.slug})

    def test_export_returns_workout_data(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['title'], 'Rutina Export')
        self.assertEqual(data['description'], 'Para exportar')
        self.assertEqual(data['difficulty'], 'intermediate')
        self.assertEqual(data['duration'], 30)
        self.assertEqual(data['slug'], self.workout.slug)
        self.assertEqual(len(data['exercises']), 2)

    def test_export_exercises_ordered(self):
        data = self.client.get(self.url).json()
        self.assertEqual(data['exercises'][0]['name'], 'Swing Export')
        self.assertEqual(data['exercises'][0]['sets'], 3)
        self.assertEqual(data['exercises'][0]['reps'], '15')
        self.assertEqual(data['exercises'][0]['notes'], 'Sin pausa')
        self.assertEqual(data['exercises'][1]['name'], 'Squat Export')
        self.assertEqual(data['exercises'][1]['notes'], '')

    def test_export_nonexistent_workout_returns_404(self):
        url = reverse('exercises:workout_export', kwargs={'slug': 'no-existe'})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)

    def test_export_private_workout_visible_to_owner(self):
        self.workout.is_public = False
        self.workout.save()
        self.client.login(username='exportuser', password='password123')
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)

    def test_export_private_workout_is_hidden_from_other_users(self):
        """workout_export usa get_object_or_404 sin filtro de visibilidad,
        así que cualquier usuario con el slug puede acceder."""
        self.workout.is_public = False
        self.workout.save()
        User.objects.create_user(username='other', password='password123')
        self.client.login(username='other', password='password123')
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 404)


class UserProfileFocusTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='focususer', password='password123')

    def test_focus_maps_goals_correctly(self):
        expected = {
            'strength': 'strength',
            'fat_loss': 'cardio',
            'mobility': 'flexibility',
            'general': 'mix',
        }
        for goal, expected_focus in expected.items():
            profile = UserProfile(user=self.user, goal=goal)
            self.assertEqual(profile.focus, expected_focus, f'goal={goal}')

    def test_focus_defaults_to_mix_for_unknown(self):
        profile = UserProfile(user=self.user)
        profile.goal = 'unknown_goal'
        self.assertEqual(profile.focus, 'mix')


class RateLimitTests(TestCase):
    """Tests for the rate_limit decorator on API endpoints."""

    def setUp(self):
        self.user = User.objects.create_user(username='rluser', password='password123')
        self.client.login(username='rluser', password='password123')
        self.exercise = Exercise.objects.create(
            name='RL Test', description='x', category='strength', difficulty='beginner'
        )
        self.workout = Workout.objects.create(
            title='RL Workout', description='x', difficulty='beginner',
            estimated_duration=20, created_by=self.user, is_public=False,
        )

    def _clear_cache(self):
        from django.core.cache import cache
        cache.clear()

    def test_toggle_favorite_rate_limit(self):
        self._clear_cache()
        url = reverse('exercises:toggle_favorite')
        payload = json.dumps({'exercise_id': self.exercise.id})
        # 30 requests should pass
        for _ in range(30):
            resp = self.client.post(url, payload, content_type='application/json')
            self.assertIn(resp.status_code, (200, 400))
        # 31st should be rate limited
        resp = self.client.post(url, payload, content_type='application/json')
        self.assertEqual(resp.status_code, 429)
        self.assertIn('Demasiadas', resp.json()['message'])

    def test_log_workout_rate_limit(self):
        self._clear_cache()
        url = reverse('exercises:log_workout')
        payload = json.dumps({'workout_id': self.workout.id})
        # 10 requests should pass
        for _ in range(10):
            resp = self.client.post(url, payload, content_type='application/json')
            self.assertEqual(resp.status_code, 200)
        # 11th should be rate limited
        resp = self.client.post(url, payload, content_type='application/json')
        self.assertEqual(resp.status_code, 429)

    def test_push_subscription_rate_limit(self):
        self._clear_cache()
        url = reverse('exercises:push_subscription')
        for i in range(5):
            payload = json.dumps({
                'endpoint': f'https://example.com/push/{i}',
                'keys': {'p256dh': 'k', 'auth': 'a'},
            })
            resp = self.client.post(url, payload, content_type='application/json')
            self.assertEqual(resp.status_code, 200)
        # 6th should be rate limited
        payload = json.dumps({
            'endpoint': 'https://example.com/push/6',
            'keys': {'p256dh': 'k', 'auth': 'a'},
        })
        resp = self.client.post(url, payload, content_type='application/json')
        self.assertEqual(resp.status_code, 429)

    def test_autocomplete_rate_limit(self):
        self._clear_cache()
        url = reverse('exercises:exercise_autocomplete')
        # 60 requests should pass
        for _ in range(60):
            resp = self.client.get(url, {'q': 'test'})
            self.assertEqual(resp.status_code, 200)
        # 61st should be rate limited
        resp = self.client.get(url, {'q': 'test'})
        self.assertEqual(resp.status_code, 429)

    def test_rate_limit_is_per_user(self):
        """Different users have separate rate limit buckets."""
        self._clear_cache()
        User.objects.create_user(username='rl_other', password='password123')
        url = reverse('exercises:toggle_favorite')
        payload = json.dumps({'exercise_id': self.exercise.id})

        # Exhaust the first user's limit
        for _ in range(30):
            self.client.post(url, payload, content_type='application/json')

        # Other user should still be able to use the endpoint
        self.client.login(username='rl_other', password='password123')
        resp = self.client.post(url, payload, content_type='application/json')
        self.assertEqual(resp.status_code, 200)


class PushUtilsTests(TestCase):
    """Tests for exercises.push_utils module."""

    def setUp(self):
        self.user = User.objects.create_user(username='pushutil', password='password123')
        PushSubscription.objects.create(
            user=self.user, endpoint='https://example.com/push',
            p256dh='k', auth='a',
        )

    @patch('pywebpush.webpush')
    @patch.object(django_settings, 'VAPID_PRIVATE_KEY', 'test-key')
    def test_send_push_to_user(self, mock_webpush):
        from exercises.push_utils import send_push_to_user
        sent = send_push_to_user(self.user, {'title': 'Test', 'body': 'Hello'})
        self.assertEqual(sent, 1)
        mock_webpush.assert_called_once()

    @patch('pywebpush.webpush')
    @patch.object(django_settings, 'VAPID_PRIVATE_KEY', 'test-key')
    def test_send_push_cleans_expired_subscriptions(self, mock_webpush):
        from unittest.mock import MagicMock

        from pywebpush import WebPushException

        from exercises.push_utils import send_push_to_user

        mock_response = MagicMock()
        mock_response.status_code = 410
        mock_webpush.side_effect = WebPushException(
            'Gone', response=mock_response
        )

        sent = send_push_to_user(self.user, {'title': 'Test'})
        self.assertEqual(sent, 0)
        self.assertFalse(
            PushSubscription.objects.filter(user=self.user).exists()
        )

    @patch.object(django_settings, 'VAPID_PRIVATE_KEY', '')
    def test_send_push_without_vapid_returns_zero(self):
        from exercises.push_utils import send_push_to_user
        sent = send_push_to_user(self.user, {'title': 'Test'})
        self.assertEqual(sent, 0)

    @patch('pywebpush.webpush')
    @patch.object(django_settings, 'VAPID_PRIVATE_KEY', 'test-key')
    def test_send_workout_completed_push(self, mock_webpush):
        import json

        from exercises.push_utils import send_push_to_user
        # Call synchronously to avoid thread timing issues
        send_push_to_user(self.user, {
            'title': '¡Entrenamiento completado! 💪',
            'body': '"Rutina Fuerza" completada · 🔥 Racha de 5 días · 🏋️ 16 kg',
            'url': '/dashboard/',
            'type': 'workout_completed',
        })
        mock_webpush.assert_called_once()
        call_args = mock_webpush.call_args
        payload = json.loads(call_args.kwargs['data'])
        self.assertIn('Rutina Fuerza', payload['body'])
        self.assertEqual(payload['type'], 'workout_completed')

    @patch('pywebpush.webpush')
    @patch.object(django_settings, 'VAPID_PRIVATE_KEY', 'test-key')
    def test_send_streak_reminder_push(self, mock_webpush):
        from exercises.push_utils import send_push_to_user
        send_push_to_user(self.user, {
            'title': '¡No pierdas tu racha! 🔥',
            'body': 'Entrena hoy para mantener tu racha activa.',
            'url': '/dashboard/',
            'type': 'streak_reminder',
        })
        mock_webpush.assert_called_once()

    @patch('pywebpush.webpush')
    @patch.object(django_settings, 'VAPID_PRIVATE_KEY', 'test-key')
    def test_send_inactivity_push(self, mock_webpush):
        import json

        from exercises.push_utils import send_push_to_user
        send_push_to_user(self.user, {
            'title': 'Llevas 5 días sin entrenar 😟',
            'body': 'Vuelve a la acción. Una sesión corta cuenta.',
            'url': '/workouts/generate/',
            'type': 'inactivity_alert',
        })
        mock_webpush.assert_called_once()
        call_args = mock_webpush.call_args
        payload = json.loads(call_args.kwargs['data'])
        self.assertIn('5 días', payload['title'])
        self.assertEqual(payload['type'], 'inactivity_alert')

    @patch('pywebpush.webpush')
    @patch.object(django_settings, 'VAPID_PRIVATE_KEY', 'test-key')
    def test_send_new_pr_push(self, mock_webpush):
        import json

        from exercises.push_utils import send_push_to_user
        send_push_to_user(self.user, {
            'title': '¡Nuevo récord personal! 🏆',
            'body': 'Nuevo peso máximo: 24 kg 🏋️',
            'url': '/dashboard/',
            'type': 'new_pr',
        })
        mock_webpush.assert_called_once()
        call_args = mock_webpush.call_args
        payload = json.loads(call_args.kwargs['data'])
        self.assertIn('24', payload['body'])
        self.assertEqual(payload['type'], 'new_pr')


class PostWorkoutPushTests(TestCase):
    """Tests for push notifications triggered after logging a workout."""

    def setUp(self):
        self.user = User.objects.create_user(username='postpush', password='password123')
        self.client.login(username='postpush', password='password123')
        self.workout = Workout.objects.create(
            title='Rutina Test', description='x', difficulty='beginner',
            estimated_duration=20, created_by=self.user, is_public=False,
        )
        PushSubscription.objects.create(
            user=self.user, endpoint='https://example.com/push',
            p256dh='k', auth='a',
        )
        self.log_url = reverse('exercises:log_workout')

    @patch('exercises.push_utils._send_async')
    @patch.object(django_settings, 'VAPID_PRIVATE_KEY', 'test-key')
    def test_log_workout_triggers_push(self, mock_send):
        """log_workout should trigger push notification (via _send_async)."""
        resp = self.client.post(
            self.log_url,
            json.dumps({'workout_id': self.workout.id, 'kettlebell_weight': 16}),
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 200)
        # _send_async should have been called at least once (congratulations)
        self.assertTrue(mock_send.called)

    @patch('exercises.push_utils._send_async')
    @patch.object(django_settings, 'VAPID_PRIVATE_KEY', 'test-key')
    def test_log_workout_detects_weight_pr(self, mock_send):
        """New weight PR should trigger an extra push notification."""
        WorkoutLog.objects.create(
            user=self.user, workout=self.workout, kettlebell_weight=12,
        )
        self.client.post(
            self.log_url,
            json.dumps({'workout_id': self.workout.id, 'kettlebell_weight': 20}),
            content_type='application/json',
        )
        # Should be called at least twice: congratulations + PR
        self.assertGreaterEqual(mock_send.call_count, 2)
