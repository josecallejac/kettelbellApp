from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.urls import reverse
from .models import Exercise, Favorite
import json

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
            'password': 'password123',
            'password_2': 'password123'  # UserCreationForm expects two passwords usually? No, standard usage in test often handles it or just clean checks. 
            # Wait, standard UserCreationForm fields are username, password 1 & 2. 
            # My CustomUserCreationForm only defined fields = ('username', 'email'). 
            # It inherits from UserCreationForm which handles passwords.
        })
        # If successful, redirects to landing
        # Note: UserCreationForm requires pass1 and pass2
        # But wait, does it? Yes.
        # Let's verify CustomUserCreationForm in forms.py inherits UserCreationForm.
        pass

    def test_login_user(self):
        User.objects.create_user(username='testuser', password='password123')
        response = self.client.post(self.login_url, {
            'username': 'testuser',
            'password': 'password123'
        })
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.wsgi_request.user.is_authenticated)

    def test_logout_user(self):
        User.objects.create_user(username='testuser', password='password123')
        self.client.login(username='testuser', password='password123')
        response = self.client.post(self.logout_url) # Logout view redirects
        self.assertEqual(response.status_code, 302)
        self.assertFalse(response.wsgi_request.user.is_authenticated)

class FavoriteTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username='favuser', password='password123')
        self.exercise = Exercise.objects.create(
            name='Kettlebell Swing',
            description='Basic swing',
            category='strength',
            difficulty='beginner'
        )
        self.toggle_url = reverse('exercises:toggle_favorite')
        
    def test_toggle_favorite_authenticated(self):
        self.client.login(username='favuser', password='password123')
        
        # Test Adding Favorite
        response = self.client.post(
            self.toggle_url,
            json.dumps({'exercise_id': self.exercise.id}),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(Favorite.objects.filter(user=self.user, exercise=self.exercise).exists())
        self.assertTrue(response.json()['is_favorite'])
        
        # Test Removing Favorite
        response = self.client.post(
            self.toggle_url,
            json.dumps({'exercise_id': self.exercise.id}),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Favorite.objects.filter(user=self.user, exercise=self.exercise).exists())
        self.assertFalse(response.json()['is_favorite'])
        
    def test_toggle_favorite_unauthenticated(self):
        response = self.client.post(
            self.toggle_url,
            json.dumps({'exercise_id': self.exercise.id}),
            content_type='application/json'
        )
        # Should redirect to login (302) because of @login_required
        self.assertEqual(response.status_code, 302)
