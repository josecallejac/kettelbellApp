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
    path('healthz/', views.healthz, name='healthz'),
    path('favorites/', views.favorites_list, name='favorites'),
    path('api/toggle-favorite/', views.toggle_favorite, name='toggle_favorite'),
    path('api/exercises/autocomplete/', views.exercise_autocomplete, name='exercise_autocomplete'),
    path('api/exercises/filters/', views.exercise_filters, name='exercise_filters'),
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
    path('progress/', views.progress_overview, name='progress_overview'),
    path('progress/sessions/<int:log_id>/', views.progress_session_detail, name='progress_session_detail'),
    path('progress/sessions/<int:log_id>/edit/', views.progress_session_edit, name='progress_session_edit'),
    path('profile/', views.profile_view, name='profile'),
    path('plan/', views.plan_overview, name='plan_overview'),
    path('plan/create/', views.plan_create, name='plan_create'),
    path('plan/<int:plan_id>/', views.plan_detail, name='plan_detail'),
    path('plan/<int:plan_id>/pause/', views.toggle_plan_pause, name='plan_pause'),
    path('plan/<int:plan_id>/cancel/', views.cancel_plan, name='plan_cancel'),
    path('plan/sessions/<int:session_id>/prepare/', views.prepare_plan_session_view, name='plan_session_prepare'),
    path('plan/sessions/<int:session_id>/reschedule/', views.reschedule_plan_session, name='plan_session_reschedule'),
    path('plan/sessions/<int:session_id>/skip/', views.skip_plan_session, name='plan_session_skip'),
    path('api/dismiss-plan-invite/', views.dismiss_plan_invite, name='dismiss_plan_invite'),
    path('api/log-workout/', views.log_workout, name='log_workout'),
    path('api/push-subscription/', views.save_push_subscription, name='push_subscription'),
    path('api/push-subscription/remove/', views.remove_push_subscription, name='push_subscription_remove'),
    path('api/push-subscription/test/', views.send_test_notification, name='push_subscription_test'),
    path('api/workout-export/<slug:slug>/', views.workout_export, name='workout_export'),
]
