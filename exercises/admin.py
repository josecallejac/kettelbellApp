from django.contrib import admin

from .models import (
    Exercise,
    ExercisePerformance,
    PlannedSession,
    TrainingPlan,
    UserProfile,
    Workout,
    WorkoutExercise,
    WorkoutLog,
)


@admin.register(Exercise)
class ExerciseAdmin(admin.ModelAdmin):
    list_display = ['name', 'category', 'difficulty', 'duration_minutes', 'calories_burned', 'created_at']
    list_filter = ['category', 'difficulty', 'created_at']
    search_fields = ['name', 'description', 'benefits', 'instructions', 'muscles_targeted', 'common_mistakes', 'equipment']
    prepopulated_fields = {'slug': ('name',)}
    readonly_fields = ['created_at', 'updated_at']
    
    fieldsets = (
        ('Información Básica', {
            'fields': ('name', 'slug', 'category', 'difficulty')
        }),
        ('Contenido', {
            'fields': ('description', 'instructions', 'benefits')
        }),
        ('Media', {
            'fields': ('image', 'video_url')
        }),
        ('Métricas', {
            'fields': ('duration_minutes', 'calories_burned')
        }),
        ('Detalles Avanzados', {
            'fields': ('equipment', 'muscles_targeted', 'variations', 'setup_tips', 'progressions', 'common_mistakes', 'precautions')
        }),
        ('Fechas', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


class WorkoutExerciseInline(admin.TabularInline):
    model = WorkoutExercise
    extra = 1
    autocomplete_fields = ['exercise']

@admin.register(Workout)
class WorkoutAdmin(admin.ModelAdmin):
    list_display = ['title', 'created_by', 'difficulty', 'estimated_duration', 'is_public', 'is_plan_managed', 'created_at']
    list_filter = ['difficulty', 'is_public', 'is_plan_managed']
    search_fields = ['title', 'description', 'created_by__username']
    prepopulated_fields = {'slug': ('title',)}
    inlines = [WorkoutExerciseInline]

@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ['user', 'level', 'goal', 'available_weights', 'updated_at']
    list_filter = ['level', 'goal']
    search_fields = ['user__username']


@admin.register(TrainingPlan)
class TrainingPlanAdmin(admin.ModelAdmin):
    list_display = ['user', 'goal', 'sessions_per_week', 'start_date', 'end_date', 'status', 'reminders_enabled']
    list_filter = ['goal', 'level', 'status', 'reminders_enabled']
    search_fields = ['user__username']


@admin.register(PlannedSession)
class PlannedSessionAdmin(admin.ModelAdmin):
    list_display = [
        'plan', 'sequence', 'scheduled_date', 'focus', 'phase', 'status', 'workout',
        'energy_level', 'pain_level', 'available_minutes', 'readiness_checked_at',
    ]
    list_filter = ['status', 'focus', 'phase', 'scheduled_date']
    search_fields = ['plan__user__username', 'adaptation_reason']


@admin.register(WorkoutLog)
class WorkoutLogAdmin(admin.ModelAdmin):
    list_display = ['user', 'workout', 'completed_at', 'edited_at', 'duration_minutes', 'kettlebell_weight', 'rpe']
    list_filter = ['completed_at', 'rpe']
    search_fields = ['user__username', 'workout__title', 'notes']


@admin.register(ExercisePerformance)
class ExercisePerformanceAdmin(admin.ModelAdmin):
    list_display = [
        'user', 'exercise', 'workout_log', 'completed',
        'sets_completed', 'reps_completed', 'weight', 'rpe', 'created_at',
    ]
    list_filter = ['completed', 'rpe', 'created_at']
    search_fields = ['user__username', 'exercise__name', 'notes']
    readonly_fields = ['created_at']
