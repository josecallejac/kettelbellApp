from django.contrib import admin
from .models import Exercise, Workout, WorkoutExercise, WorkoutLog

@admin.register(Exercise)
class ExerciseAdmin(admin.ModelAdmin):
    list_display = ['name', 'category', 'difficulty', 'duration_minutes', 'calories_burned', 'created_at']
    list_filter = ['category', 'difficulty', 'created_at']
    search_fields = ['name', 'description', 'benefits', 'instructions']
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
    list_display = ['title', 'difficulty', 'estimated_duration', 'is_public', 'created_at']
    list_filter = ['difficulty', 'is_public']
    search_fields = ['title', 'description']
    prepopulated_fields = {'slug': ('title',)}
    inlines = [WorkoutExerciseInline]

@admin.register(WorkoutLog)
class WorkoutLogAdmin(admin.ModelAdmin):
    list_display = ['user', 'workout', 'completed_at']
    list_filter = ['completed_at']
    search_fields = ['user__username', 'workout__title']
