"""Browser-level smoke tests for the root service worker and plan wizard."""

import os
from datetime import date

from django.contrib.auth.models import User
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.urls import reverse
from playwright.sync_api import sync_playwright

from .models import Exercise, ExercisePerformance, Workout, WorkoutExercise, WorkoutLog

os.environ.setdefault('DJANGO_ALLOW_ASYNC_UNSAFE', 'true')


class AdaptivePlanBrowserTests(StaticLiveServerTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.playwright = sync_playwright().start()
        cls.browser = cls.playwright.chromium.launch(headless=True)

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()
        super().tearDownClass()

    def setUp(self):
        for category in ('strength', 'cardio', 'flexibility', 'full_body'):
            Exercise.objects.create(
                name=f'Browser {category}',
                description='x',
                category=category,
                difficulty='beginner',
            )
        self.context = self.browser.new_context()
        self.page = self.context.new_page()

    def tearDown(self):
        self.context.close()

    def test_root_service_worker_scope_and_private_cache_policy(self):
        response = self.page.request.get(f'{self.live_server_url}/sw.js')
        self.assertEqual(response.status, 200)
        self.assertEqual(response.headers.get('service-worker-allowed'), '/')
        body = response.text()
        self.assertIn('PUBLIC_DOCUMENT_PATHS', body)
        self.assertNotIn("'/dashboard/'", body)
        self.assertNotIn("'/progress/'", body)

        self.page.goto(f'{self.live_server_url}/')
        self.page.wait_for_function("navigator.serviceWorker.ready.then(() => true)")
        scope = self.page.evaluate("navigator.serviceWorker.ready.then(reg => reg.scope)")
        self.assertEqual(scope, f'{self.live_server_url}/')

    def test_user_can_create_plan_from_dashboard(self):
        self.page.goto(f'{self.live_server_url}/register/')
        self.page.locator('#id_username').fill('browseruser')
        self.page.locator('#id_email').fill('browser@example.com')
        self.page.locator('#id_password1').fill('S3gura-clave!')
        self.page.locator('#id_password2').fill('S3gura-clave!')
        self.page.locator('button[type="submit"]').click()
        self.page.goto(f'{self.live_server_url}/dashboard/')
        self.page.get_by_role('link', name='Crear mi plan').click()
        self.page.locator('input[name="preferred_weekdays"]').nth(0).check()
        self.page.locator('input[name="preferred_weekdays"]').nth(2).check()
        self.page.locator('input[name="preferred_weekdays"]').nth(4).check()
        self.page.locator('input[name="start_date"]').fill(date.today().isoformat())
        self.page.get_by_role('button', name='Crear mi plan').click()
        self.assertIn('/plan/', self.page.url)
        self.assertIn('Tu camino de entrenamiento', self.page.text_content('body'))

    def test_session_draft_can_be_restored_and_discarded(self):
        user = User.objects.create_user(username='draftuser', password='S3gura-clave!')
        exercise = Exercise.objects.get(name='Browser strength')
        workout = Workout.objects.create(
            title='Borrador de prueba',
            description='x',
            difficulty='beginner',
            estimated_duration=20,
            created_by=user,
            is_public=False,
        )
        workout_exercise = WorkoutExercise.objects.create(
            workout=workout,
            exercise=exercise,
            order=1,
            sets=2,
            reps='10 reps',
        )

        self.page.goto(f'{self.live_server_url}/login/')
        self.page.locator('#id_username').fill('draftuser')
        self.page.locator('#id_password').fill('S3gura-clave!')
        self.page.locator('button[type="submit"]').click()

        session_url = f'{self.live_server_url}{reverse("exercises:workout_session", kwargs={"slug": workout.slug})}'
        self.page.goto(session_url)
        draft_key = f'kb-session-draft:v1:{user.id}:{workout.id}:standalone'
        draft = {
            'version': 1,
            'savedAt': self.page.evaluate('Date.now()'),
            'currentStep': 0,
            'elapsedSeconds': 12,
            'timerSeconds': 4,
            'timerPhase': 'idle',
            'timerRemaining': 0,
            'clientSessionId': '00000000-0000-4000-8000-000000000001',
            'selectedRpe': 6,
            'weight': '16',
            'notes': 'retomar',
            'exercises': [{
                'id': workout_exercise.id,
                'activeSets': [0],
                'weight': '16',
                'reps': '10',
                'rpe': '6',
            }],
            'pendingPayload': None,
        }
        self.page.evaluate(
            '([key, value]) => localStorage.setItem(key, JSON.stringify(value))',
            [draft_key, draft],
        )
        self.page.reload()
        self.page.reload()
        self.page.get_by_role('button', name='Continuar borrador').click()
        self.assertEqual(self.page.locator('#weight-input').input_value(), '16')
        self.assertEqual(self.page.locator('#notes-input').input_value(), 'retomar')
        stored = self.page.evaluate('(key) => localStorage.getItem(key)', draft_key)
        self.assertNotIn('csrfToken', stored or '')

        self.page.evaluate(
            '([key, value]) => localStorage.setItem(key, JSON.stringify(value))',
            [draft_key, draft],
        )
        self.page.reload()
        self.page.get_by_role('button', name='Descartar').click()
        self.assertIsNone(self.page.evaluate('(key) => localStorage.getItem(key)', draft_key))

        invalid_draft = {'version': 1, 'savedAt': self.page.evaluate('Date.now()'), 'exercises': None}
        self.page.evaluate(
            '([key, value]) => localStorage.setItem(key, JSON.stringify(value))',
            [draft_key, invalid_draft],
        )
        self.page.reload()
        self.assertEqual(self.page.locator('.draft-recovery-banner').count(), 0)
        self.assertIsNone(self.page.evaluate('(key) => localStorage.getItem(key)', draft_key))

    def test_session_save_is_kept_and_retried_after_network_recovers(self):
        user = User.objects.create_user(username='retryuser', password='S3gura-clave!')
        exercise = Exercise.objects.get(name='Browser strength')
        workout = Workout.objects.create(
            title='Reintento de prueba',
            description='x',
            difficulty='beginner',
            estimated_duration=20,
            created_by=user,
            is_public=False,
        )
        WorkoutExercise.objects.create(
            workout=workout,
            exercise=exercise,
            order=1,
            sets=1,
            reps='10 reps',
        )

        self.page.goto(f'{self.live_server_url}/login/')
        self.page.locator('#id_username').fill('retryuser')
        self.page.locator('#id_password').fill('S3gura-clave!')
        self.page.locator('button[type="submit"]').click()
        session_url = f'{self.live_server_url}{reverse("exercises:workout_session", kwargs={"slug": workout.slug})}'
        self.page.goto(session_url)
        draft_key = f'kb-session-draft:v1:{user.id}:{workout.id}:standalone'

        self.page.route('**/api/log-workout/', lambda route: route.abort())
        self.page.locator('#next-btn').click()
        self.page.locator('#rpe-scale .rpe-bubble').nth(5).click()
        self.page.locator('#weight-input').fill('16')
        self.page.locator('#save-session-btn').click()
        self.page.wait_for_function(
            "document.getElementById('metrics-feedback').textContent.includes('No se pudo enviar todavía')"
        )
        stored = self.page.evaluate('(key) => localStorage.getItem(key)', draft_key)
        self.assertIn('pendingPayload', stored or '')

        self.page.unroute('**/api/log-workout/')
        self.page.evaluate("window.dispatchEvent(new Event('online'))")
        self.page.wait_for_url(f'{self.live_server_url}/dashboard/', timeout=5000)
        self.assertIsNone(self.page.evaluate('(key) => localStorage.getItem(key)', draft_key))

    def test_history_detail_and_edit_flow(self):
        user = User.objects.create_user(username='historybrowser', password='S3gura-clave!')
        exercise = Exercise.objects.get(name='Browser strength')
        workout = Workout.objects.create(
            title='Historial navegador',
            description='x',
            difficulty='beginner',
            estimated_duration=20,
            created_by=user,
            is_public=False,
        )
        workout_exercise = WorkoutExercise.objects.create(
            workout=workout,
            exercise=exercise,
            order=1,
            sets=2,
            reps='10 reps',
        )
        log = WorkoutLog.objects.create(
            user=user,
            workout=workout,
            duration_minutes=20,
            rpe=6,
            kettlebell_weight=12,
        )
        ExercisePerformance.objects.create(
            user=user,
            workout_log=log,
            workout_exercise=workout_exercise,
            exercise=exercise,
            completed=True,
            sets_completed=2,
            reps_completed=10,
            weight=12,
            rpe=6,
        )

        self.page.goto(f'{self.live_server_url}/login/')
        self.page.locator('#id_username').fill('historybrowser')
        self.page.locator('#id_password').fill('S3gura-clave!')
        self.page.locator('button[type="submit"]').click()
        self.page.goto(f'{self.live_server_url}/progress/?period=all')
        self.assertIn('Historial y progreso', self.page.text_content('body'))
        self.page.get_by_role('link', name='Revisar').click()
        self.assertIn('Historial navegador', self.page.text_content('body'))
        self.page.get_by_role('link', name='Corregir datos').click()
        self.page.locator('#id_duration_minutes').fill('35')
        self.page.locator('#id_rpe').fill('7')
        self.page.locator('#id_notes').fill('Corregida desde navegador')
        self.page.locator('#id_performances-0-weight').fill('16')
        with self.page.expect_navigation():
            self.page.get_by_role('button', name='Guardar corrección').click()
        self.assertEqual(self.page.url, f'{self.live_server_url}/progress/sessions/{log.id}/')
        self.assertIn('Sesión actualizada', self.page.text_content('body'))
        self.assertIn('Corregida desde navegador', self.page.text_content('body'))
