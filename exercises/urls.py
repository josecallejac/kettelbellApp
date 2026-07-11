from django.urls import path

from . import views

app_name = 'exercises'

urlpatterns = [
    path('', views.landing_page, name='landing'),
    path('exercises/', views.exercise_list, name='exercise_list'),
    path('categories/', views.category_list, name='category_list'),
    path('categories/<slug:category>/', views.category_detail, name='category_detail'),
    path('levels/', views.difficulty_list, name='difficulty_list'),
    path('levels/<slug:difficulty>/', views.difficulty_detail, name='difficulty_detail'),
    path('exercise/<slug:slug>/', views.exercise_detail, name='detail'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('register/', views.register_view, name='register'),
    path('favorites/', views.favorites_list, name='favorites'),
    path('api/toggle-favorite/', views.toggle_favorite, name='toggle_favorite'),
    # Workouts
    path('workouts/', views.workout_list, name='workout_list'),
    path('workouts/create/', views.create_workout, name='workout_create'),
    path('workouts/generate/', views.generate_routine_view, name='generate_routine'),
    path('workouts/<slug:slug>/', views.workout_detail, name='workout_detail'),
    path('workouts/<slug:slug>/start/', views.workout_session, name='workout_session'),
    path('workouts/<slug:slug>/edit/', views.edit_workout, name='workout_edit'),
    path('workouts/<slug:slug>/delete/', views.delete_workout, name='workout_delete'),
    
    # Dashboard & API
    path('dashboard/', views.dashboard, name='dashboard'),
    path('profile/', views.profile_view, name='profile'),
    path('api/log-workout/', views.log_workout, name='log_workout'),
]
