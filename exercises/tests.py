import json

from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse

from .models import Exercise, Favorite, UserProfile, Workout, WorkoutLog
from .utils import RoutineGenerator


class AuthTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.register_url = reverse('exercises:register')
        self.login_url = reverse('exercises:login')
        self.logout_url = reverse('exercises:logout')

    def test_register_user(self):
        response = self.client.post(self.register_url, {
            'username': 'newuser',
            'email': 'new@example.com',
            'password1': 'S3gura-clave!',
            'password2': 'S3gura-clave!',
        })
        self.assertRedirects(response, reverse('exercises:landing'))
        self.assertTrue(User.objects.filter(username='newuser').exists())
        self.assertTrue(response.wsgi_request.user.is_authenticated)

    def test_register_password_mismatch_shows_errors(self):
        response = self.client.post(self.register_url, {
            'username': 'newuser',
            'email': 'new@example.com',
            'password1': 'S3gura-clave!',
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
        self.assertEqual(exercise.image_url, '/static/exercises/img/catalog/kettlebell_swing.jpg')

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
