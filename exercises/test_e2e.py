import json
import os
from html.parser import HTMLParser

from django.apps import apps
from django.core.cache import cache
from django.core.management import call_command
from django.test import Client, TestCase
from django.urls import reverse


class SimpleHTMLParser(HTMLParser):
    """
    Lightweight helper to parse inputs, links, images, and text content
    from rendered templates without external dependencies like BeautifulSoup.
    """
    def __init__(self):
        super().__init__()
        self.tags = []
        self.inputs = {}
        self.links = []
        self.images = []
        self.texts = []
        self.current_tag = None

    def handle_starttag(self, tag, attrs):
        self.current_tag = tag
        attr_dict = dict(attrs)
        self.tags.append((tag, attr_dict))
        if tag == 'input':
            name = attr_dict.get('name')
            val = attr_dict.get('value', '')
            if name:
                self.inputs[name] = val
        elif tag == 'a':
            href = attr_dict.get('href')
            if href:
                self.links.append(href)
        elif tag == 'img':
            src = attr_dict.get('src')
            if src:
                self.images.append(src)

    def handle_data(self, data):
        cleaned = data.strip()
        if cleaned:
            self.texts.append(cleaned)

    def handle_endtag(self, tag):
        self.current_tag = None


class KettlebellE2ETestSuite(TestCase):
    def setUp(self):
        super().setUp()
        cache.clear()
        self.client = Client()
        call_command('seed_catalog', clear=True)
        
        # Opaque-Box scraping of catalog on startup to get seeded test data
        response = self.client.get(reverse('exercises:exercise_list'))
        parser = self.parse_html(response.content.decode('utf-8'))
        
        self.exercise_ids = []
        for tag, attrs in parser.tags:
            if tag == 'button' and 'favorite-btn' in attrs.get('class', ''):
                eid = attrs.get('data-id')
                if eid:
                    self.exercise_ids.append(int(eid))
        
        self.exercise_slugs = []
        for href in parser.links:
            if '/exercise/' in href:
                slug = href.split('/exercise/')[-1].strip('/')
                if slug not in self.exercise_slugs:
                    self.exercise_slugs.append(slug)

    # =========================================================================
    # E2E HELPER METHODS
    # =========================================================================
    def parse_html(self, html_string):
        parser = SimpleHTMLParser()
        parser.feed(html_string)
        return parser

    def register_user(self, username, email, password, confirm_password):
        url = reverse('exercises:register')
        return self.client.post(url, {
            'username': username,
            'email': email,
            'password1': password,
            'password2': confirm_password,
        })

    def login_user(self, username, password, next_url=None):
        url = reverse('exercises:login')
        data = {
            'username': username,
            'password': password,
        }
        if next_url:
            data['next'] = next_url
        return self.client.post(url, data)

    def logout_user(self):
        url = reverse('exercises:logout')
        return self.client.post(url)

    def toggle_favorite(self, exercise_id):
        url = reverse('exercises:toggle_favorite')
        return self.client.post(url, json.dumps({'exercise_id': exercise_id}), content_type='application/json')

    def log_workout(self, workout_id, duration_minutes=None, kettlebell_weight=None, rpe=None, notes=None):
        url = reverse('exercises:log_workout')
        payload = {'workout_id': workout_id}
        if duration_minutes is not None:
            payload['duration_minutes'] = duration_minutes
        if kettlebell_weight is not None:
            payload['kettlebell_weight'] = kettlebell_weight
        if rpe is not None:
            payload['rpe'] = rpe
        if notes is not None:
            payload['notes'] = notes
        return self.client.post(url, json.dumps(payload), content_type='application/json')

    def create_workout(self, title, description, difficulty, estimated_duration, is_public, exercises_data):
        url = reverse('exercises:workout_create')
        data = {
            'title': title,
            'description': description,
            'difficulty': difficulty,
            'estimated_duration': estimated_duration,
            'exercises-TOTAL_FORMS': len(exercises_data),
            'exercises-INITIAL_FORMS': 0,
            'exercises-MIN_NUM_FORMS': 0,
            'exercises-MAX_NUM_FORMS': 1000,
        }
        if is_public:
            data['is_public'] = 'on'
        for i, form_data in enumerate(exercises_data):
            data[f'exercises-{i}-id'] = ''
            data[f'exercises-{i}-exercise'] = form_data.get('exercise', '')
            data[f'exercises-{i}-sets'] = form_data.get('sets', 3)
            data[f'exercises-{i}-reps'] = form_data.get('reps', '10')
            data[f'exercises-{i}-notes'] = form_data.get('notes', '')
        return self.client.post(url, data)

    def edit_workout(self, slug, title, description, difficulty, estimated_duration, is_public, exercises_data):
        url = reverse('exercises:workout_edit', kwargs={'slug': slug})
        response = self.client.get(url)
        parser = self.parse_html(response.content.decode('utf-8'))
        
        data = {
            'title': title,
            'description': description,
            'difficulty': difficulty,
            'estimated_duration': estimated_duration,
            'exercises-TOTAL_FORMS': parser.inputs.get('exercises-TOTAL_FORMS', '0'),
            'exercises-INITIAL_FORMS': parser.inputs.get('exercises-INITIAL_FORMS', '0'),
            'exercises-MIN_NUM_FORMS': parser.inputs.get('exercises-MIN_NUM_FORMS', '0'),
            'exercises-MAX_NUM_FORMS': parser.inputs.get('exercises-MAX_NUM_FORMS', '1000'),
        }
        if is_public:
            data['is_public'] = 'on'
        
        total_forms = int(data['exercises-TOTAL_FORMS'])
        for k, v in parser.inputs.items():
            if k.startswith('exercises-'):
                data[k] = v
        
        for i, form_data in enumerate(exercises_data):
            idx = i
            if idx >= total_forms:
                data['exercises-TOTAL_FORMS'] = str(idx + 1)
            data[f'exercises-{idx}-exercise'] = form_data.get('exercise', '')
            data[f'exercises-{idx}-sets'] = form_data.get('sets', 3)
            data[f'exercises-{idx}-reps'] = form_data.get('reps', '10')
            data[f'exercises-{idx}-notes'] = form_data.get('notes', '')
            if 'id' in form_data:
                data[f'exercises-{idx}-id'] = form_data['id']
            if form_data.get('DELETE'):
                data[f'exercises-{idx}-DELETE'] = 'on'

        return self.client.post(url, data)

    def delete_workout_post(self, slug):
        url = reverse('exercises:workout_delete', kwargs={'slug': slug})
        return self.client.post(url)

    def generate_routine(self, duration, difficulty, focus):
        url = reverse('exercises:generate_routine')
        return self.client.post(url, {
            'duration': duration,
            'difficulty': difficulty,
            'focus': focus,
        })

    def update_profile(self, level, goal, available_weights):
        url = reverse('exercises:profile')
        return self.client.post(url, {
            'level': level,
            'goal': goal,
            'available_weights': available_weights,
        })

    def get_exercise_by_search(self, q):
        url = reverse('exercises:exercise_list') + f'?q={q}'
        response = self.client.get(url)
        parser = self.parse_html(response.content.decode('utf-8'))
        
        ids = []
        for tag, attrs in parser.tags:
            if tag == 'button' and 'favorite-btn' in attrs.get('class', ''):
                eid = attrs.get('data-id')
                if eid:
                    ids.append(int(eid))
        
        slugs = []
        for href in parser.links:
            if '/exercise/' in href:
                slug = href.split('/exercise/')[-1].strip('/')
                if slug not in slugs:
                    slugs.append(slug)
        return ids, slugs

    def verify_image_exists(self, img_url):
        response = self.client.get(img_url)
        if response.status_code == 200:
            return True
        from django.conf import settings
        static_url = settings.STATIC_URL or '/static/'
        if img_url.startswith(static_url):
            rel_path = img_url[len(static_url):]
            full_path = os.path.join('exercises', 'static', rel_path)
            if os.path.exists(full_path):
                return True
        return False

    # =========================================================================
    # FEATURE 1: USER AUTHENTICATION & SESSION MANAGEMENT (F1)
    # =========================================================================
    def test_f1_t1_register_happy(self):
        response = self.register_user('newuser', 'new@example.com', 'SecurePass123!', 'SecurePass123!')
        self.assertRedirects(response, reverse('exercises:landing'))
        self.assertTrue(response.wsgi_request.user.is_authenticated)

    def test_f1_t1_login_happy(self):
        self.register_user('loginuser', 'login@example.com', 'SecurePass123!', 'SecurePass123!')
        self.logout_user()
        response = self.login_user('loginuser', 'SecurePass123!')
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse('exercises:landing'))
        self.assertTrue(response.wsgi_request.user.is_authenticated)

    def test_f1_t1_logout_happy(self):
        self.register_user('logoutuser', 'log@example.com', 'SecurePass123!', 'SecurePass123!')
        response = self.logout_user()
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse('exercises:landing'))
        self.assertFalse(response.wsgi_request.user.is_authenticated)

    def test_f1_t1_dashboard_auth_restricted(self):
        response = self.client.get(reverse('exercises:dashboard'))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('exercises:login'), response.url)

    def test_f1_t1_profile_auth_restricted(self):
        response = self.client.get(reverse('exercises:profile'))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('exercises:login'), response.url)

    def test_f1_t2_register_password_mismatch(self):
        response = self.register_user('mismatchuser', 'mismatch@example.com', 'Pass1!', 'Pass2!')
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.wsgi_request.user.is_authenticated)

    def test_f1_t2_register_duplicate_username(self):
        self.register_user('duplicateuser', 'd1@example.com', 'SecurePass123!', 'SecurePass123!')
        self.logout_user()
        response = self.register_user('duplicateuser', 'd2@example.com', 'SecurePass123!', 'SecurePass123!')
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.wsgi_request.user.is_authenticated)

    def test_f1_t2_login_invalid_password(self):
        self.register_user('badpassuser', 'bp@example.com', 'SecurePass123!', 'SecurePass123!')
        self.logout_user()
        response = self.login_user('badpassuser', 'wrongpass')
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.wsgi_request.user.is_authenticated)

    def test_f1_t2_login_invalid_username(self):
        response = self.login_user('nonexistent', 'somepass')
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.wsgi_request.user.is_authenticated)

    def test_f1_t2_login_next_redirect_safety(self):
        self.register_user('safetyuser', 'sf@example.com', 'SecurePass123!', 'SecurePass123!')
        self.logout_user()
        response = self.login_user('safetyuser', 'SecurePass123!', next_url='https://evil.com')
        self.assertRedirects(response, reverse('exercises:landing'))

    # =========================================================================
    # FEATURE 2: EXERCISE CATALOG (SEARCH & PAGINATION) (F2)
    # =========================================================================
    def test_f2_t1_catalog_view(self):
        response = self.client.get(reverse('exercises:exercise_list'))
        self.assertEqual(response.status_code, 200)
        parser = self.parse_html(response.content.decode('utf-8'))
        self.assertTrue(len(parser.links) > 0)

    def test_f2_t1_search_by_name(self):
        ids, slugs = self.get_exercise_by_search('Swing')
        self.assertTrue(len(slugs) > 0)
        self.assertTrue(any('swing' in slug.lower() for slug in slugs))

    def test_f2_t1_search_by_muscle(self):
        ids, slugs = self.get_exercise_by_search('Glúteos')
        if not slugs:
            ids, slugs = self.get_exercise_by_search('Gluteos')
        self.assertTrue(len(slugs) > 0)

    def test_f2_t1_pagination_page_one(self):
        response = self.client.get(reverse('exercises:exercise_list'))
        parser = self.parse_html(response.content.decode('utf-8'))
        detail_links = [link for link in parser.links if '/exercise/' in link]
        self.assertLessEqual(len(set(detail_links)), 12)

    def test_f2_t1_pagination_next_page(self):
        response = self.client.get(reverse('exercises:exercise_list') + '?page=2')
        self.assertEqual(response.status_code, 200)

    def test_f2_t2_search_empty_results(self):
        response = self.client.get(reverse('exercises:exercise_list') + '?q=NonexistentExerciseSearchString')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'No hay ejercicios que coincidan')

    def test_f2_t2_search_special_characters(self):
        response = self.client.get(reverse('exercises:exercise_list') + '?q=<script>alert(1)</script>')
        self.assertEqual(response.status_code, 200)

    def test_f2_t2_pagination_invalid_page(self):
        response = self.client.get(reverse('exercises:exercise_list') + '?page=abc')
        self.assertEqual(response.status_code, 200)

    def test_f2_t2_pagination_out_of_bounds(self):
        response = self.client.get(reverse('exercises:exercise_list') + '?page=99999')
        self.assertEqual(response.status_code, 200)

    def test_f2_t2_search_case_insensitivity(self):
        ids1, slugs1 = self.get_exercise_by_search('swing')
        ids2, slugs2 = self.get_exercise_by_search('SWING')
        self.assertEqual(len(slugs1), len(slugs2))

    # =========================================================================
    # FEATURE 3: EXERCISE DETAIL & VISUAL ASSETS (IMAGES) (F3)
    # =========================================================================
    def test_f3_t1_detail_view(self):
        slug = self.exercise_slugs[0]
        response = self.client.get(reverse('exercises:detail', kwargs={'slug': slug}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Antes de partir')

    def test_f3_t1_detail_has_image(self):
        slug = self.exercise_slugs[0]
        response = self.client.get(reverse('exercises:detail', kwargs={'slug': slug}))
        parser = self.parse_html(response.content.decode('utf-8'))
        self.assertTrue(len(parser.images) > 0)

    def test_f3_t1_image_src_valid(self):
        slug = self.exercise_slugs[0]
        response = self.client.get(reverse('exercises:detail', kwargs={'slug': slug}))
        parser = self.parse_html(response.content.decode('utf-8'))
        for src in parser.images:
            if not src.startswith('data:'):
                self.assertTrue(src.startswith('/static/'))

    def test_f3_t1_image_not_404(self):
        slug = self.exercise_slugs[0]
        response = self.client.get(reverse('exercises:detail', kwargs={'slug': slug}))
        parser = self.parse_html(response.content.decode('utf-8'))
        if parser.images:
            self.assertTrue(self.verify_image_exists(parser.images[0]))

    def test_f3_t1_landing_featured_images(self):
        response = self.client.get(reverse('exercises:landing'))
        parser = self.parse_html(response.content.decode('utf-8'))
        self.assertTrue(len(parser.images) > 0)
        for src in parser.images:
            if 'catalog/' in src:
                self.assertTrue(self.verify_image_exists(src))

    def test_f3_t2_detail_invalid_slug(self):
        response = self.client.get(reverse('exercises:detail', kwargs={'slug': 'nonexistent-slug'}))
        self.assertEqual(response.status_code, 404)

    def test_f3_t2_no_image_fallback(self):
        Exercise = apps.get_model('exercises', 'Exercise')
        exercise = Exercise.objects.create(
            name='No Image Exercise',
            slug='no-image-exercise',
            description='Test exercise with no image',
            category='strength',
            difficulty='beginner',
            image=''
        )
        response = self.client.get(reverse('exercises:detail', kwargs={'slug': exercise.slug}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'No Image Exercise')

    def test_f3_t2_detail_rich_text_split(self):
        slug = self.exercise_slugs[0]
        response = self.client.get(reverse('exercises:detail', kwargs={'slug': slug}))
        self.assertEqual(response.status_code, 200)

    def test_f3_t2_all_catalog_images_exist(self):
        response = self.client.get(reverse('exercises:exercise_list'))
        parser = self.parse_html(response.content.decode('utf-8'))
        for src in parser.images:
            if 'catalog/' in src:
                self.assertTrue(self.verify_image_exists(src))

    def test_f3_t2_images_extensions(self):
        response = self.client.get(reverse('exercises:exercise_list'))
        parser = self.parse_html(response.content.decode('utf-8'))
        for src in parser.images:
            if 'catalog/' in src:
                self.assertTrue(src.lower().endswith('.jpg') or src.lower().endswith('.png') or src.lower().endswith('.webp'))

    # =========================================================================
    # FEATURE 4: CATEGORY & DIFFICULTY TAXONOMY (F4)
    # =========================================================================
    def test_f4_t1_categories_list(self):
        response = self.client.get(reverse('exercises:category_list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Categorias')

    def test_f4_t1_category_detail(self):
        response = self.client.get(reverse('exercises:category_detail', kwargs={'category': 'strength'}))
        self.assertEqual(response.status_code, 200)

    def test_f4_t1_difficulties_list(self):
        response = self.client.get(reverse('exercises:difficulty_list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Niveles')

    def test_f4_t1_difficulty_detail(self):
        response = self.client.get(reverse('exercises:difficulty_detail', kwargs={'difficulty': 'beginner'}))
        self.assertEqual(response.status_code, 200)

    def test_f4_t1_taxonomy_has_exercises(self):
        response = self.client.get(reverse('exercises:category_detail', kwargs={'category': 'strength'}))
        parser = self.parse_html(response.content.decode('utf-8'))
        detail_links = [link for link in parser.links if '/exercise/' in link]
        self.assertTrue(len(detail_links) > 0)

    def test_f4_t2_invalid_category_slug(self):
        response = self.client.get(reverse('exercises:category_detail', kwargs={'category': 'inexistente'}))
        self.assertEqual(response.status_code, 404)

    def test_f4_t2_invalid_difficulty_slug(self):
        response = self.client.get(reverse('exercises:difficulty_detail', kwargs={'difficulty': 'inexistente'}))
        self.assertEqual(response.status_code, 404)

    def test_f4_t2_empty_category(self):
        Exercise = apps.get_model('exercises', 'Exercise')
        Exercise.objects.filter(category='cardio').delete()
        response = self.client.get(reverse('exercises:category_detail', kwargs={'category': 'cardio'}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'No hay ejercicios')

    def test_f4_t2_empty_difficulty(self):
        Exercise = apps.get_model('exercises', 'Exercise')
        Exercise.objects.filter(difficulty='advanced').delete()
        response = self.client.get(reverse('exercises:difficulty_detail', kwargs={'difficulty': 'advanced'}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'No hay ejercicios')

    def test_f4_t2_taxonomy_case_sensitivity(self):
        response = self.client.get(reverse('exercises:category_detail', kwargs={'category': 'STRENGTH'}))
        self.assertEqual(response.status_code, 404)

    # =========================================================================
    # FEATURE 5: FAVORITES SYSTEM (F5)
    # =========================================================================
    def test_f5_t1_toggle_favorite_add(self):
        self.register_user('user_fav_add', 'u@example.com', 'SecurePass123!', 'SecurePass123!')
        eid = self.exercise_ids[0]
        response = self.toggle_favorite(eid)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json().get('is_favorite'))

    def test_f5_t1_toggle_favorite_remove(self):
        self.register_user('user_fav_rem', 'u@example.com', 'SecurePass123!', 'SecurePass123!')
        eid = self.exercise_ids[0]
        self.toggle_favorite(eid)
        response = self.toggle_favorite(eid)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json().get('is_favorite'))

    def test_f5_t1_favorites_list_page(self):
        self.register_user('user_fav_list', 'u@example.com', 'SecurePass123!', 'SecurePass123!')
        eid = self.exercise_ids[0]
        self.toggle_favorite(eid)
        response = self.client.get(reverse('exercises:favorites'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.exercise_slugs[0])

    def test_f5_t1_favorites_empty_state(self):
        self.register_user('user_fav_empty', 'u@example.com', 'SecurePass123!', 'SecurePass123!')
        response = self.client.get(reverse('exercises:favorites'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'No tienes favoritos aún')

    def test_f5_t1_favorite_button_present(self):
        slug = self.exercise_slugs[0]
        response = self.client.get(reverse('exercises:detail', kwargs={'slug': slug}))
        parser = self.parse_html(response.content.decode('utf-8'))
        has_fav_btn = False
        for tag, attrs in parser.tags:
            if tag == 'button' and 'favorite-btn' in attrs.get('class', ''):
                has_fav_btn = True
        self.assertTrue(has_fav_btn)

    def test_f5_t2_toggle_unauthenticated(self):
        eid = self.exercise_ids[0]
        response = self.toggle_favorite(eid)
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('exercises:login'), response.url)

    def test_f5_t2_toggle_invalid_id(self):
        self.register_user('user_fav_invalid', 'u@example.com', 'SecurePass123!', 'SecurePass123!')
        url = reverse('exercises:toggle_favorite')
        response = self.client.post(url, json.dumps({'exercise_id': 'abc'}), content_type='application/json')
        self.assertEqual(response.status_code, 400)

    def test_f5_t2_toggle_missing_id(self):
        self.register_user('user_fav_missing', 'u@example.com', 'SecurePass123!', 'SecurePass123!')
        url = reverse('exercises:toggle_favorite')
        response = self.client.post(url, json.dumps({}), content_type='application/json')
        self.assertEqual(response.status_code, 400)

    def test_f5_t2_toggle_non_json(self):
        self.register_user('user_fav_nonjson', 'u@example.com', 'SecurePass123!', 'SecurePass123!')
        url = reverse('exercises:toggle_favorite')
        response = self.client.post(url, 'exercise_id=123', content_type='application/x-www-form-urlencoded')
        self.assertEqual(response.status_code, 400)

    def test_f5_t2_list_unauthenticated(self):
        response = self.client.get(reverse('exercises:favorites'))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('exercises:login'), response.url)

    # =========================================================================
    # FEATURE 6: WORKOUT BUILDER CRUD (F6)
    # =========================================================================
    def test_f6_t1_create_workout(self):
        self.register_user('user_workout_crud', 'u@example.com', 'SecurePass123!', 'SecurePass123!')
        exercises_data = [{'exercise': self.exercise_ids[0], 'sets': 3, 'reps': '10', 'notes': 'Test'}]
        response = self.create_workout('Mi Rutina de Test', 'Desc', 'intermediate', 30, True, exercises_data)
        self.assertEqual(response.status_code, 302)
        self.assertTrue('/workouts/' in response.url)

    def test_f6_t1_view_workout_detail(self):
        self.register_user('user_workout_view', 'u@example.com', 'SecurePass123!', 'SecurePass123!')
        exercises_data = [{'exercise': self.exercise_ids[0], 'sets': 3, 'reps': '10', 'notes': 'Test'}]
        self.create_workout('Mi Rutina Ver', 'Desc', 'intermediate', 30, True, exercises_data)
        response = self.client.get(reverse('exercises:workout_detail', kwargs={'slug': 'mi-rutina-ver'}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Mi Rutina Ver')

    def test_f6_t1_edit_workout(self):
        self.register_user('user_workout_edit', 'u@example.com', 'SecurePass123!', 'SecurePass123!')
        exercises_data = [{'exercise': self.exercise_ids[0], 'sets': 3, 'reps': '10', 'notes': 'Test'}]
        self.create_workout('Mi Rutina Edit', 'Desc', 'intermediate', 30, True, exercises_data)
        from exercises.models import WorkoutExercise
        edited_exercises = [{'id': str(WorkoutExercise.objects.filter(workout__slug='mi-rutina-edit').first().id), 'exercise': self.exercise_ids[0], 'sets': 4, 'reps': '12', 'notes': 'Updated'}]
        response = self.edit_workout('mi-rutina-edit', 'Mi Rutina Edit Modificada', 'Nueva', 'advanced', 45, True, edited_exercises)
        self.assertEqual(response.status_code, 302)
        
        detail_response = self.client.get(reverse('exercises:workout_detail', kwargs={'slug': 'mi-rutina-edit'}))
        self.assertContains(detail_response, 'Mi Rutina Edit Modificada')

    def test_f6_t1_delete_workout(self):
        self.register_user('user_workout_del', 'u@example.com', 'SecurePass123!', 'SecurePass123!')
        exercises_data = [{'exercise': self.exercise_ids[0], 'sets': 3, 'reps': '10', 'notes': 'Test'}]
        self.create_workout('Mi Rutina Del', 'Desc', 'intermediate', 30, True, exercises_data)
        
        response = self.delete_workout_post('mi-rutina-del')
        self.assertEqual(response.status_code, 302)
        
        detail_response = self.client.get(reverse('exercises:workout_detail', kwargs={'slug': 'mi-rutina-del'}))
        self.assertEqual(detail_response.status_code, 404)

    def test_f6_t1_workout_list_view(self):
        self.register_user('user_workout_list', 'u@example.com', 'SecurePass123!', 'SecurePass123!')
        exercises_data = [{'exercise': self.exercise_ids[0], 'sets': 3, 'reps': '10', 'notes': 'Test'}]
        self.create_workout('Mi Rutina List', 'Desc', 'intermediate', 30, True, exercises_data)
        
        response = self.client.get(reverse('exercises:workout_list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Mi Rutina List')

    def test_f6_t2_workout_private_visibility(self):
        self.register_user('user_b', 'b@example.com', 'SecurePass123!', 'SecurePass123!')
        exercises_data = [{'exercise': self.exercise_ids[0], 'sets': 3, 'reps': '10', 'notes': 'Test'}]
        self.create_workout('Rutina Privada B', 'Desc', 'intermediate', 30, False, exercises_data)
        self.logout_user()
        
        self.register_user('user_a', 'a@example.com', 'SecurePass123!', 'SecurePass123!')
        response = self.client.get(reverse('exercises:workout_detail', kwargs={'slug': 'rutina-privada-b'}))
        self.assertEqual(response.status_code, 404)

    def test_f6_t2_workout_public_anonymous(self):
        self.register_user('user_b2', 'b2@example.com', 'SecurePass123!', 'SecurePass123!')
        exercises_data = [{'exercise': self.exercise_ids[0], 'sets': 3, 'reps': '10', 'notes': 'Test'}]
        self.create_workout('Rutina Publica B', 'Desc', 'intermediate', 30, True, exercises_data)
        self.logout_user()
        
        response = self.client.get(reverse('exercises:workout_detail', kwargs={'slug': 'rutina-publica-b'}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Rutina Publica B')

    def test_f6_t2_edit_workout_unauthorized(self):
        self.register_user('user_b3', 'b3@example.com', 'SecurePass123!', 'SecurePass123!')
        exercises_data = [{'exercise': self.exercise_ids[0], 'sets': 3, 'reps': '10', 'notes': 'Test'}]
        self.create_workout('Rutina B3', 'Desc', 'intermediate', 30, True, exercises_data)
        self.logout_user()
        
        self.register_user('user_a3', 'a3@example.com', 'SecurePass123!', 'SecurePass123!')
        url = reverse('exercises:workout_edit', kwargs={'slug': 'rutina-b3'})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)

    def test_f6_t2_delete_workout_unauthorized(self):
        self.register_user('user_b4', 'b4@example.com', 'SecurePass123!', 'SecurePass123!')
        exercises_data = [{'exercise': self.exercise_ids[0], 'sets': 3, 'reps': '10', 'notes': 'Test'}]
        self.create_workout('Rutina B4', 'Desc', 'intermediate', 30, True, exercises_data)
        self.logout_user()
        
        self.register_user('user_a4', 'a4@example.com', 'SecurePass123!', 'SecurePass123!')
        response = self.delete_workout_post('rutina-b4')
        self.assertEqual(response.status_code, 404)

    def test_f6_t2_delete_workout_get_rejected(self):
        self.register_user('user_b5', 'b5@example.com', 'SecurePass123!', 'SecurePass123!')
        exercises_data = [{'exercise': self.exercise_ids[0], 'sets': 3, 'reps': '10', 'notes': 'Test'}]
        self.create_workout('Rutina B5', 'Desc', 'intermediate', 30, True, exercises_data)
        
        url = reverse('exercises:workout_delete', kwargs={'slug': 'rutina-b5'})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 405)

    # =========================================================================
    # FEATURE 7: AUTOMATED ROUTINE GENERATOR (F7)
    # =========================================================================
    def test_f7_t1_generate_routine_form(self):
        self.register_user('user_gen_form', 'g@example.com', 'SecurePass123!', 'SecurePass123!')
        response = self.client.get(reverse('exercises:generate_routine'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="duration"')
        self.assertContains(response, 'name="difficulty"')
        self.assertContains(response, 'name="focus"')

    def test_f7_t1_generate_routine_submit(self):
        self.register_user('user_gen_submit', 'g@example.com', 'SecurePass123!', 'SecurePass123!')
        response = self.generate_routine(30, 'intermediate', 'mix')
        self.assertEqual(response.status_code, 302)
        self.assertTrue('/workouts/' in response.url)

    def test_f7_t1_routine_contains_exercises(self):
        self.register_user('user_gen_ex', 'g@example.com', 'SecurePass123!', 'SecurePass123!')
        response = self.generate_routine(30, 'intermediate', 'mix')
        detail_response = self.client.get(response.url)
        parser = self.parse_html(detail_response.content.decode('utf-8'))
        exercise_links = [link for link in parser.links if '/exercise/' in link]
        self.assertTrue(len(exercise_links) > 0)

    def test_f7_t1_routine_cooldown_warmup(self):
        self.register_user('user_gen_phase', 'g@example.com', 'SecurePass123!', 'SecurePass123!')
        response = self.generate_routine(30, 'intermediate', 'mix')
        detail_response = self.client.get(response.url)
        self.assertContains(detail_response, 'calentar')
        self.assertContains(detail_response, 'relajar')

    def test_f7_t1_routine_is_private(self):
        self.register_user('user_gen_priv', 'g@example.com', 'SecurePass123!', 'SecurePass123!')
        response = self.generate_routine(30, 'intermediate', 'mix')
        workout_url = response.url
        self.logout_user()
        
        self.register_user('other_user', 'o@example.com', 'SecurePass123!', 'SecurePass123!')
        detail_response = self.client.get(workout_url)
        self.assertEqual(detail_response.status_code, 404)

    def test_f7_t2_generate_invalid_duration(self):
        self.register_user('user_gen_inv_dur', 'g@example.com', 'SecurePass123!', 'SecurePass123!')
        response = self.client.post(reverse('exercises:generate_routine'), {
            'duration': -5,
            'difficulty': 'intermediate',
            'focus': 'mix'
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'no son válidos')

    def test_f7_t2_generate_invalid_difficulty(self):
        self.register_user('user_gen_inv_diff', 'g@example.com', 'SecurePass123!', 'SecurePass123!')
        response = self.client.post(reverse('exercises:generate_routine'), {
            'duration': 30,
            'difficulty': 'invalid_choice',
            'focus': 'mix'
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'no son válidos')

    def test_f7_t2_generator_volume_adaptation_high(self):
        self.register_user('user_vol_high', 'g@example.com', 'SecurePass123!', 'SecurePass123!')
        exercises_data = [{'exercise': self.exercise_ids[0], 'sets': 3, 'reps': '10', 'notes': 'Test'}]
        self.create_workout('Workout to Log', 'Desc', 'intermediate', 30, True, exercises_data)
        
        Workout = apps.get_model('exercises', 'Workout')
        workout_id = Workout.objects.get(slug='workout-to-log').id
        
        for _ in range(5):
            self.log_workout(workout_id, duration_minutes=30, kettlebell_weight=12, rpe=9, notes='Hard')
        
        gen_res = self.generate_routine(30, 'intermediate', 'mix')
        self.assertEqual(gen_res.status_code, 302)
        detail_res = self.client.get(gen_res.url)
        self.assertContains(detail_res, 'Volumen reducido')

    def test_f7_t2_generator_volume_adaptation_low(self):
        self.register_user('user_vol_low', 'g@example.com', 'SecurePass123!', 'SecurePass123!')
        exercises_data = [{'exercise': self.exercise_ids[0], 'sets': 3, 'reps': '10', 'notes': 'Test'}]
        self.create_workout('Workout to Log Low', 'Desc', 'intermediate', 30, True, exercises_data)
        
        Workout = apps.get_model('exercises', 'Workout')
        workout_id = Workout.objects.get(slug='workout-to-log-low').id
        
        for _ in range(5):
            self.log_workout(workout_id, duration_minutes=30, kettlebell_weight=12, rpe=4, notes='Easy')
            
        gen_res = self.generate_routine(30, 'intermediate', 'mix')
        self.assertEqual(gen_res.status_code, 302)
        detail_res = self.client.get(gen_res.url)
        self.assertContains(detail_res, 'Volumen aumentado')

    def test_f7_t2_suggested_weights_profile(self):
        self.register_user('user_sug_weight', 'g@example.com', 'SecurePass123!', 'SecurePass123!')
        self.update_profile('intermediate', 'general', '8, 12, 16')
        gen_res = self.generate_routine(30, 'intermediate', 'mix')
        detail_res = self.client.get(gen_res.url)
        self.assertContains(detail_res, 'Peso sugerido:')

    # =========================================================================
    # FEATURE 8: WORKOUT SESSION TRACKER & LOGGING (F8)
    # =========================================================================
    def test_f8_t1_session_view(self):
        self.register_user('user_sess_view', 'u@example.com', 'SecurePass123!', 'SecurePass123!')
        exercises_data = [{'exercise': self.exercise_ids[0], 'sets': 3, 'reps': '10', 'notes': 'Test'}]
        self.create_workout('Workout Session', 'Desc', 'intermediate', 30, True, exercises_data)
        
        response = self.client.get(reverse('exercises:workout_session', kwargs={'slug': 'workout-session'}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Workout Session')

    def test_f8_t1_log_workout_happy(self):
        self.register_user('user_log_happy', 'u@example.com', 'SecurePass123!', 'SecurePass123!')
        exercises_data = [{'exercise': self.exercise_ids[0], 'sets': 3, 'reps': '10', 'notes': 'Test'}]
        self.create_workout('Workout Log Happy', 'Desc', 'intermediate', 30, True, exercises_data)
        
        Workout = apps.get_model('exercises', 'Workout')
        workout_id = Workout.objects.get(slug='workout-log-happy').id
        
        response = self.log_workout(workout_id, duration_minutes=25, kettlebell_weight=16, rpe=7, notes='Excellent session')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json().get('status'), 'success')

    def test_f8_t1_dashboard_stats(self):
        self.register_user('user_dash_stats', 'u@example.com', 'SecurePass123!', 'SecurePass123!')
        exercises_data = [{'exercise': self.exercise_ids[0], 'sets': 3, 'reps': '10', 'notes': 'Test'}]
        self.create_workout('Workout Dash', 'Desc', 'intermediate', 30, True, exercises_data)
        
        Workout = apps.get_model('exercises', 'Workout')
        workout_id = Workout.objects.get(slug='workout-dash').id
        
        self.log_workout(workout_id, duration_minutes=35, kettlebell_weight=12, rpe=6, notes='Good')
        
        response = self.client.get(reverse('exercises:dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '35')
        self.assertContains(response, '1')

    def test_f8_t1_profile_view(self):
        self.register_user('user_profile_view', 'u@example.com', 'SecurePass123!', 'SecurePass123!')
        response = self.client.get(reverse('exercises:profile'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Preferencias de entrenamiento')

    def test_f8_t1_profile_update_happy(self):
        self.register_user('user_profile_update', 'u@example.com', 'SecurePass123!', 'SecurePass123!')
        response = self.update_profile('advanced', 'strength', '12, 16, 24')
        self.assertEqual(response.status_code, 302)
        
        profile_response = self.client.get(reverse('exercises:profile'))
        self.assertContains(profile_response, '12, 16, 24')

    def test_f8_t2_log_workout_invalid_rpe(self):
        self.register_user('user_log_inv_rpe', 'u@example.com', 'SecurePass123!', 'SecurePass123!')
        exercises_data = [{'exercise': self.exercise_ids[0], 'sets': 3, 'reps': '10', 'notes': 'Test'}]
        self.create_workout('Workout Inv Rpe', 'Desc', 'intermediate', 30, True, exercises_data)
        
        Workout = apps.get_model('exercises', 'Workout')
        workout_id = Workout.objects.get(slug='workout-inv-rpe').id
        
        response = self.log_workout(workout_id, duration_minutes=30, kettlebell_weight=12, rpe=11)
        self.assertEqual(response.status_code, 400)

    def test_f8_t2_log_workout_unauthenticated(self):
        response = self.log_workout(1, duration_minutes=30, kettlebell_weight=12, rpe=7)
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('exercises:login'), response.url)

    def test_f8_t2_log_workout_private_unauthorized(self):
        self.register_user('user_b_log_priv', 'b@example.com', 'SecurePass123!', 'SecurePass123!')
        exercises_data = [{'exercise': self.exercise_ids[0], 'sets': 3, 'reps': '10', 'notes': 'Test'}]
        self.create_workout('Workout Priv B Log', 'Desc', 'intermediate', 30, False, exercises_data)
        
        Workout = apps.get_model('exercises', 'Workout')
        workout_id = Workout.objects.get(slug='workout-priv-b-log').id
        self.logout_user()
        
        self.register_user('user_a_log_priv', 'a@example.com', 'SecurePass123!', 'SecurePass123!')
        response = self.log_workout(workout_id, duration_minutes=30, kettlebell_weight=12, rpe=7)
        self.assertEqual(response.status_code, 404)

    def test_f8_t2_dashboard_empty_stats(self):
        self.register_user('user_dash_empty', 'u@example.com', 'SecurePass123!', 'SecurePass123!')
        response = self.client.get(reverse('exercises:dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '—')

    def test_f8_t2_profile_weights_garbage(self):
        self.register_user('user_prof_garbage', 'u@example.com', 'SecurePass123!', 'SecurePass123!')
        response = self.update_profile('intermediate', 'general', '8, abc, 12, 16')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Cada peso debe ser un numero finito')

        response = self.update_profile('intermediate', 'general', '8, 12, 16')
        self.assertEqual(response.status_code, 302)
        
        gen_res = self.generate_routine(30, 'intermediate', 'mix')
        detail_res = self.client.get(gen_res.url)
        self.assertContains(detail_res, 'Peso sugerido: 12 kg')

    # =========================================================================
    # TIER 3: CROSS-FEATURE COMBINATIONS
    # =========================================================================
    def test_t3_01_profile_pref_affects_generator(self):
        self.register_user('user_t3_01', 'u@example.com', 'SecurePass123!', 'SecurePass123!')
        self.update_profile('advanced', 'strength', '16')
        
        response = self.client.get(reverse('exercises:generate_routine'))
        self.assertContains(response, 'value="advanced" checked')
        self.assertContains(response, 'value="strength" checked')

    def test_t3_02_favorite_detail_to_list(self):
        self.register_user('user_t3_02', 'u@example.com', 'SecurePass123!', 'SecurePass123!')
        eid = self.exercise_ids[0]
        self.toggle_favorite(eid)
        
        response = self.client.get(reverse('exercises:favorites'))
        self.assertContains(response, self.exercise_slugs[0])

    def test_t3_03_create_workout_view_catalog(self):
        self.register_user('user_t3_03', 'u@example.com', 'SecurePass123!', 'SecurePass123!')
        exercises_data = [{'exercise': self.exercise_ids[0], 'sets': 3, 'reps': '10', 'notes': 'Test'}]
        self.create_workout('Workout T3 03', 'Desc', 'intermediate', 30, True, exercises_data)
        
        detail_response = self.client.get(reverse('exercises:workout_detail', kwargs={'slug': 'workout-t3-03'}))
        self.assertContains(detail_response, 'Workout T3 03')
        self.assertContains(detail_response, self.exercise_slugs[0])

    def test_t3_04_generate_workout_log_dashboard(self):
        self.register_user('user_t3_04', 'u@example.com', 'SecurePass123!', 'SecurePass123!')
        response = self.generate_routine(30, 'intermediate', 'mix')
        workout_url = response.url
        
        Workout = apps.get_model('exercises', 'Workout')
        slug = workout_url.split('/workouts/')[-1].strip('/')
        workout_id = Workout.objects.get(slug=slug).id
        
        self.log_workout(workout_id, duration_minutes=30, kettlebell_weight=16, rpe=9, notes='Tough')
        dash_res = self.client.get(reverse('exercises:dashboard'))
        self.assertContains(dash_res, '30')
        self.assertContains(dash_res, '9')

    def test_t3_05_auth_favorites_isolation(self):
        self.register_user('user_a_t3_05', 'a@example.com', 'SecurePass123!', 'SecurePass123!')
        self.toggle_favorite(self.exercise_ids[0])
        self.logout_user()
        
        self.register_user('user_b_t3_05', 'b@example.com', 'SecurePass123!', 'SecurePass123!')
        response = self.client.get(reverse('exercises:favorites'))
        self.assertNotContains(response, self.exercise_slugs[0])

    def test_t3_06_auth_workout_crud_isolation(self):
        self.register_user('user_b_t3_06', 'b@example.com', 'SecurePass123!', 'SecurePass123!')
        exercises_data = [{'exercise': self.exercise_ids[0], 'sets': 3, 'reps': '10', 'notes': 'Test'}]
        self.create_workout('Workout B Private', 'Desc', 'intermediate', 30, False, exercises_data)
        self.logout_user()
        
        self.register_user('user_a_t3_06', 'a@example.com', 'SecurePass123!', 'SecurePass123!')
        slug = 'workout-b-private'
        self.assertEqual(self.client.get(reverse('exercises:workout_detail', kwargs={'slug': slug})).status_code, 404)
        self.assertEqual(self.client.get(reverse('exercises:workout_edit', kwargs={'slug': slug})).status_code, 404)
        self.assertEqual(self.delete_workout_post(slug).status_code, 404)

    def test_t3_07_catalog_search_to_detail(self):
        self.register_user('user_t3_07', 'u@example.com', 'SecurePass123!', 'SecurePass123!')
        ids, slugs = self.get_exercise_by_search('Deadlift')
        self.assertTrue(len(slugs) > 0)
        target_slug = slugs[0]
        target_id = ids[0]
        
        response = self.client.get(reverse('exercises:detail', kwargs={'slug': target_slug}))
        self.assertEqual(response.status_code, 200)
        
        fav_response = self.toggle_favorite(target_id)
        self.assertEqual(fav_response.status_code, 200)
        self.assertTrue(fav_response.json().get('is_favorite'))

    def test_t3_08_log_workout_affects_session_prefill(self):
        self.register_user('user_t3_08', 'u@example.com', 'SecurePass123!', 'SecurePass123!')
        exercises_data = [{'exercise': self.exercise_ids[0], 'sets': 3, 'reps': '10', 'notes': 'Test'}]
        self.create_workout('Workout T3 08', 'Desc', 'intermediate', 30, True, exercises_data)
        
        Workout = apps.get_model('exercises', 'Workout')
        workout_id = Workout.objects.get(slug='workout-t3-08').id
        
        self.log_workout(workout_id, duration_minutes=30, kettlebell_weight=24, rpe=8)
        
        response = self.client.get(reverse('exercises:workout_session', kwargs={'slug': 'workout-t3-08'}))
        self.assertContains(response, 'value="24"')

    # =========================================================================
    # TIER 4: REAL-WORLD SCENARIOS
    # =========================================================================
    def test_t4_01_onboarding_and_routine_generation(self):
        self.register_user('onboard_user', 'on@example.com', 'SecurePass123!', 'SecurePass123!')
        self.update_profile('beginner', 'strength', '8, 12')
        
        gen_form = self.client.get(reverse('exercises:generate_routine'))
        self.assertContains(gen_form, 'value="beginner" checked')
        self.assertContains(gen_form, 'value="strength" checked')
        
        response = self.generate_routine(30, 'beginner', 'strength')
        self.assertEqual(response.status_code, 302)
        
        detail_response = self.client.get(response.url)
        self.assertContains(detail_response, 'Peso sugerido: 8 kg')

    def test_t4_02_manual_workout_curation(self):
        self.register_user('curator_user', 'cur@example.com', 'SecurePass123!', 'SecurePass123!')
        ids_swing, slugs_swing = self.get_exercise_by_search('Swing')
        ids_clean, slugs_clean = self.get_exercise_by_search('Clean')
        self.assertTrue(len(ids_swing) > 0)
        self.assertTrue(len(ids_clean) > 0)
        
        self.toggle_favorite(ids_swing[0])
        self.toggle_favorite(ids_clean[0])
        
        exercises_data = [
            {'exercise': ids_swing[0], 'sets': 3, 'reps': '10', 'notes': 'Focus on swing technique'},
            {'exercise': ids_clean[0], 'sets': 3, 'reps': '8', 'notes': 'Clean transition'}
        ]
        response = self.create_workout('Manual Curation Workout', 'Custom', 'intermediate', 45, True, exercises_data)
        self.assertEqual(response.status_code, 302)
        
        detail_response = self.client.get(response.url)
        self.assertContains(detail_response, 'Manual Curation Workout')
        self.assertContains(detail_response, slugs_swing[0])
        self.assertContains(detail_response, slugs_clean[0])

    def test_t4_03_progressive_training_session(self):
        self.register_user('prog_user', 'prog@example.com', 'SecurePass123!', 'SecurePass123!')
        exercises_data = [{'exercise': self.exercise_ids[0], 'sets': 3, 'reps': '10', 'notes': 'Go hard'}]
        self.create_workout('Progressive Workout', 'Desc', 'advanced', 30, True, exercises_data)
        
        Workout = apps.get_model('exercises', 'Workout')
        workout_id = Workout.objects.get(slug='progressive-workout').id
        
        sess_res = self.client.get(reverse('exercises:workout_session', kwargs={'slug': 'progressive-workout'}))
        self.assertEqual(sess_res.status_code, 200)
        
        for _ in range(5):
            self.log_workout(workout_id, duration_minutes=40, kettlebell_weight=16, rpe=9, notes='Extreme')
        
        dash_res = self.client.get(reverse('exercises:dashboard'))
        self.assertContains(dash_res, '200')
        self.assertContains(dash_res, '9')
        self.assertContains(dash_res, '5')
        
        gen_res = self.generate_routine(30, 'advanced', 'mix')
        detail_res = self.client.get(gen_res.url)
        self.assertContains(detail_res, 'Volumen reducido')

    def test_t4_04_anonymous_exploration(self):
        landing_res = self.client.get(reverse('exercises:landing'))
        self.assertEqual(landing_res.status_code, 200)
        
        slug = self.exercise_slugs[0]
        detail_res = self.client.get(reverse('exercises:detail', kwargs={'slug': slug}))
        self.assertEqual(detail_res.status_code, 200)
        
        cat_list_res = self.client.get(reverse('exercises:category_list'))
        self.assertEqual(cat_list_res.status_code, 200)
        
        strength_res = self.client.get(reverse('exercises:category_detail', kwargs={'category': 'strength'}))
        self.assertEqual(strength_res.status_code, 200)
        
        eid = self.exercise_ids[0]
        fav_res = self.toggle_favorite(eid)
        self.assertEqual(fav_res.status_code, 302)
        self.assertIn(reverse('exercises:login'), fav_res.url)
        
        workouts_res = self.client.get(reverse('exercises:workout_list'))
        self.assertEqual(workouts_res.status_code, 200)

    def test_t4_05_account_migration_and_data_cleanup(self):
        self.register_user('migrator_user', 'mig@example.com', 'SecurePass123!', 'SecurePass123!')
        ex_data = [{'exercise': self.exercise_ids[0], 'sets': 3, 'reps': '10', 'notes': 'Test'}]
        self.create_workout('Workout W1', 'Desc 1', 'intermediate', 30, True, ex_data)
        self.create_workout('Workout W2', 'Desc 2', 'intermediate', 30, True, ex_data)
        
        Workout = apps.get_model('exercises', 'Workout')
        w1_id = Workout.objects.get(slug='workout-w1').id
        
        self.log_workout(w1_id, duration_minutes=30, kettlebell_weight=12, rpe=7, notes='L1')
        self.toggle_favorite(self.exercise_ids[0])
        self.toggle_favorite(self.exercise_ids[1])
        self.update_profile('advanced', 'fat_loss', '12, 16')
        
        self.delete_workout_post('workout-w1')
        w1_detail = self.client.get(reverse('exercises:workout_detail', kwargs={'slug': 'workout-w1'}))
        self.assertEqual(w1_detail.status_code, 404)
        
        dash_res = self.client.get(reverse('exercises:dashboard'))
        self.assertContains(dash_res, '30')
        self.assertContains(dash_res, '7')
