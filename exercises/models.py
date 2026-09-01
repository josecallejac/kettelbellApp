from decimal import Decimal

from django.contrib.auth.models import User
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.templatetags.static import static
from django.urls import reverse
from django.utils.text import slugify

from .weights import parse_available_weights


def build_unique_slug(instance, source_text):
    """Genera un slug único para el modelo de la instancia a partir del texto dado."""
    base_slug = slugify(source_text) or 'item'
    slug = base_slug
    counter = 1
    queryset = instance.__class__.objects.exclude(pk=instance.pk)
    while queryset.filter(slug=slug).exists():
        slug = f"{base_slug}-{counter}"
        counter += 1
    return slug

class Favorite(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='favorites')
    exercise = models.ForeignKey('Exercise', on_delete=models.CASCADE, related_name='favorited_by')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['user', 'exercise'], name='unique_user_exercise_favorite'),
        ]
        verbose_name = 'Favorito'
        verbose_name_plural = 'Favoritos'

    def __str__(self):
        return f"{self.user.username} - {self.exercise.name}"

class Exercise(models.Model):
    CATEGORY_CHOICES = [
        ('strength', 'Fuerza'),
        ('cardio', 'Cardio'),
        ('flexibility', 'Flexibilidad'),
        ('full_body', 'Cuerpo Completo'),
    ]
    
    DIFFICULTY_CHOICES = [
        ('beginner', 'Principiante'),
        ('intermediate', 'Intermedio'),
        ('advanced', 'Avanzado'),
    ]
    
    name = models.CharField(max_length=200, verbose_name='Nombre')
    slug = models.SlugField(max_length=250, unique=True, null=True, blank=True, verbose_name='URL amigable')
    description = models.TextField(verbose_name='Descripción')
    instructions = models.TextField(
        verbose_name='Instrucciones paso a paso',
        blank=True,
        help_text='Instrucciones detalladas para realizar el ejercicio correctamente'
    )
    category = models.CharField(
        max_length=20,
        choices=CATEGORY_CHOICES,
        db_index=True,
        verbose_name='Categoría'
    )
    difficulty = models.CharField(
        max_length=20,
        choices=DIFFICULTY_CHOICES,
        db_index=True,
        verbose_name='Dificultad'
    )
    benefits = models.TextField(verbose_name='Beneficios', blank=True)
    image = models.CharField(
        max_length=200,
        blank=True,
        default='',
        verbose_name='Imagen',
        help_text='Nombre de archivo dentro de exercises/static/exercises/img/catalog/ (ej: kettlebell_swing.jpg)'
    )
    video_url = models.URLField(
        verbose_name='URL del video',
        blank=True,
        help_text='URL de YouTube o Vimeo'
    )
    muscles_targeted = models.TextField(
        verbose_name='Músculos trabajados',
        blank=True,
        help_text='Lista de músculos principales y secundarios trabajados'
    )
    common_mistakes = models.TextField(
        verbose_name='Errores comunes',
        blank=True,
        help_text='Errores frecuentes a evitar y cómo corregirlos'
    )
    equipment = models.CharField(
        max_length=200,
        verbose_name='Equipo necesario',
        blank=True,
        help_text='Equipo necesario, separado por comas (ej: Kettlebell, esterilla)'
    )
    variations = models.TextField(
        verbose_name='Variaciones',
        blank=True,
        help_text='Variantes o alternativas del ejercicio'
    )
    setup_tips = models.TextField(
        verbose_name='Consejos de preparación',
        blank=True,
        help_text='Consejos para colocación, agarre y preparación'
    )
    progressions = models.TextField(
        verbose_name='Progresiones y regresiones',
        blank=True,
        help_text='Cómo progresar o simplificar el ejercicio'
    )
    precautions = models.TextField(
        verbose_name='Precauciones',
        blank=True,
        help_text='Precauciones, contraindicaciones y señales de alarma'
    )
    duration_minutes = models.PositiveIntegerField(
        verbose_name='Duración (minutos)',
        blank=True,
        null=True,
        help_text='Duración estimada del ejercicio en minutos'
    )
    calories_burned = models.PositiveIntegerField(
        verbose_name='Calorías quemadas',
        blank=True,
        null=True,
        help_text='Calorías aproximadas quemadas'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = 'Ejercicio'
        verbose_name_plural = 'Ejercicios'
        ordering = ['category', 'difficulty', 'name']
    
    def __str__(self):
        return self.name
    
    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = build_unique_slug(self, self.name)
        super().save(*args, **kwargs)
    
    def get_absolute_url(self):
        return reverse('exercises:detail', kwargs={'slug': self.slug})

    @property
    def image_url(self):
        """URL estática de la imagen del catálogo, o '' si no tiene o no existe."""
        if not self.image:
            return ''
        try:
            return static(f'exercises/img/catalog/{self.image}')
        except ValueError:
            # Con ManifestStaticFilesStorage un archivo inexistente lanza
            # ValueError; mejor no mostrar imagen que romper la página.
            return ''

class Workout(models.Model):
    DIFFICULTY_CHOICES = [
        ('beginner', 'Principiante'),
        ('intermediate', 'Intermedio'),
        ('advanced', 'Avanzado'),
    ]

    title = models.CharField(max_length=200, verbose_name='Título')
    slug = models.SlugField(max_length=250, unique=True, null=True, blank=True)
    description = models.TextField(verbose_name='Descripción')
    difficulty = models.CharField(max_length=20, choices=DIFFICULTY_CHOICES, verbose_name='Dificultad')
    estimated_duration = models.PositiveIntegerField(help_text='Duración estimada en minutos', verbose_name='Duración estimada')
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='workouts',
        verbose_name='Creado por',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    is_public = models.BooleanField(default=True, verbose_name='Es público')
    is_plan_managed = models.BooleanField(
        default=False,
        db_index=True,
        verbose_name='Gestionado por un plan',
        help_text='Las rutinas internas de un plan no se muestran en la biblioteca personal.',
    )

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = build_unique_slug(self, self.title)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.title
    
    class Meta:
        verbose_name = 'Entrenamiento'
        verbose_name_plural = 'Entrenamientos'

class WorkoutExercise(models.Model):
    workout = models.ForeignKey(Workout, related_name='exercises', on_delete=models.CASCADE)
    exercise = models.ForeignKey(Exercise, on_delete=models.CASCADE)
    order = models.PositiveIntegerField(default=0, verbose_name='Orden')
    sets = models.PositiveIntegerField(default=3, verbose_name='Series')
    reps = models.CharField(max_length=50, blank=True, help_text='Ej: 10-12 reps o 30 segs', verbose_name='Repeticiones/Tiempo')
    notes = models.CharField(max_length=200, blank=True, help_text='Notas específicas para esta rutina', verbose_name='Notas')

    class Meta:
        ordering = ['order']
        verbose_name = 'Ejercicio de Rutina'
        verbose_name_plural = 'Ejercicios de Rutina'

    def __str__(self):
        return f"{self.workout.title} - {self.exercise.name}"

class UserProfile(models.Model):
    GOAL_CHOICES = [
        ('strength', 'Ganar fuerza'),
        ('fat_loss', 'Perder grasa'),
        ('mobility', 'Movilidad y flexibilidad'),
        ('general', 'Acondicionamiento general'),
    ]

    # Mapea el objetivo del perfil al enfoque que entiende el generador.
    GOAL_TO_FOCUS = {
        'strength': 'strength',
        'fat_loss': 'cardio',
        'mobility': 'flexibility',
        'general': 'mix',
    }

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    level = models.CharField(
        max_length=20,
        choices=Exercise.DIFFICULTY_CHOICES,
        default='beginner',
        verbose_name='Nivel',
    )
    goal = models.CharField(
        max_length=20,
        choices=GOAL_CHOICES,
        default='general',
        verbose_name='Objetivo',
    )
    available_weights = models.CharField(
        max_length=100,
        blank=True,
        default='',
        verbose_name='Kettlebells disponibles (kg)',
        help_text='Separadas por comas, ej: 8, 12, 16',
    )
    plan_prompt_dismissed_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='Aviso de plan descartado',
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Perfil'
        verbose_name_plural = 'Perfiles'

    def __str__(self):
        return f"Perfil de {self.user.username}"

    @property
    def focus(self):
        return self.GOAL_TO_FOCUS.get(self.goal, 'mix')

    def weights_list(self):
        """Pesos disponibles como lista de números ordenada, ignorando basura."""
        return parse_available_weights(self.available_weights)


class TrainingPlan(models.Model):
    """Ciclo guiado de cuatro semanas para un usuario."""

    STATUS_CHOICES = [
        ('active', 'Activo'),
        ('paused', 'Pausado'),
        ('completed', 'Completado'),
        ('cancelled', 'Cancelado'),
    ]

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='training_plans',
        verbose_name='Usuario',
    )
    goal = models.CharField(
        max_length=20,
        choices=UserProfile.GOAL_CHOICES,
        default='general',
        verbose_name='Objetivo',
    )
    level = models.CharField(
        max_length=20,
        choices=Exercise.DIFFICULTY_CHOICES,
        default='beginner',
        verbose_name='Nivel',
    )
    sessions_per_week = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(2), MaxValueValidator(5)],
        verbose_name='Sesiones por semana',
    )
    session_duration = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(10), MaxValueValidator(120)],
        verbose_name='Duración de sesión (minutos)',
    )
    preferred_weekdays = models.JSONField(
        default=list,
        verbose_name='Días preferidos',
        help_text='Lista de días ISO: 0=lunes, 6=domingo.',
    )
    start_date = models.DateField(verbose_name='Inicio')
    end_date = models.DateField(verbose_name='Fin')
    reminders_enabled = models.BooleanField(default=False, verbose_name='Recordatorios activos')
    reminder_time = models.TimeField(null=True, blank=True, verbose_name='Hora del recordatorio')
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default='active', db_index=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Plan de entrenamiento'
        verbose_name_plural = 'Planes de entrenamiento'
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(
                fields=['user'],
                condition=models.Q(status__in=['active', 'paused']),
                name='unique_open_training_plan_per_user',
            ),
        ]
        indexes = [
            models.Index(fields=['user', 'status']),
            models.Index(fields=['user', '-created_at']),
        ]

    def __str__(self):
        return f"Plan de {self.user.username} ({self.start_date:%d/%m/%Y})"


class PlannedSession(models.Model):
    """Sesión del calendario; la rutina concreta se materializa al iniciarla."""

    STATUS_CHOICES = [
        ('pending', 'Pendiente'),
        ('completed', 'Completada'),
        ('skipped', 'Omitida'),
    ]

    ENERGY_CHOICES = [
        (1, '1 - Muy baja'),
        (2, '2 - Baja'),
        (3, '3 - Normal'),
        (4, '4 - Buena'),
        (5, '5 - Muy buena'),
    ]
    PAIN_CHOICES = [
        ('none', 'Sin dolor'),
        ('mild', 'Molestia leve'),
        ('stop', 'Dolor: detener'),
    ]

    plan = models.ForeignKey(
        TrainingPlan,
        on_delete=models.CASCADE,
        related_name='sessions',
        verbose_name='Plan',
    )
    sequence = models.PositiveSmallIntegerField(verbose_name='Orden')
    week_number = models.PositiveSmallIntegerField(verbose_name='Semana')
    scheduled_date = models.DateField(verbose_name='Fecha programada')
    focus = models.CharField(max_length=20, verbose_name='Enfoque')
    session_kind = models.CharField(max_length=20, default='main', verbose_name='Tipo de sesión')
    phase = models.CharField(max_length=20, default='base', verbose_name='Fase')
    estimated_duration = models.PositiveSmallIntegerField(verbose_name='Duración estimada')
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default='pending', db_index=True)
    energy_level = models.PositiveSmallIntegerField(
        choices=ENERGY_CHOICES,
        null=True,
        blank=True,
        verbose_name='Energía antes de entrenar',
    )
    pain_level = models.CharField(
        max_length=5,
        choices=PAIN_CHOICES,
        null=True,
        blank=True,
        verbose_name='Dolor o molestia',
    )
    available_minutes = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(10), MaxValueValidator(120)],
        null=True,
        blank=True,
        verbose_name='Minutos disponibles',
    )
    readiness_checked_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='Chequeo de preparación',
    )
    workout = models.OneToOneField(
        Workout,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='planned_session',
        verbose_name='Rutina generada',
    )
    adaptation_reason = models.CharField(max_length=300, blank=True, default='', verbose_name='Motivo del ajuste')
    completed_at = models.DateTimeField(null=True, blank=True)
    reminder_sent_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Sesión planificada'
        verbose_name_plural = 'Sesiones planificadas'
        ordering = ['scheduled_date', 'sequence']
        constraints = [
            models.UniqueConstraint(fields=['plan', 'sequence'], name='unique_plan_session_sequence'),
            models.UniqueConstraint(fields=['plan', 'scheduled_date'], name='unique_plan_session_date'),
        ]
        indexes = [
            models.Index(fields=['plan', 'scheduled_date', 'status']),
            models.Index(fields=['scheduled_date', 'status', 'reminder_sent_at']),
        ]

    def __str__(self):
        return f"{self.plan} - sesión {self.sequence}"

    @property
    def is_overdue(self):
        from django.utils import timezone

        return self.status == 'pending' and self.scheduled_date < timezone.localdate()


class WorkoutLog(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='workout_logs')
    workout = models.ForeignKey(Workout, on_delete=models.SET_NULL, null=True, blank=True)
    planned_session = models.OneToOneField(
        'PlannedSession',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='completed_log',
        verbose_name='Sesión planificada',
    )
    workout_title_snapshot = models.CharField(max_length=200, blank=True, default='')
    workout_difficulty_snapshot = models.CharField(max_length=20, blank=True, default='')
    workout_duration_snapshot = models.PositiveIntegerField(null=True, blank=True)
    completed_at = models.DateTimeField(auto_now_add=True)
    edited_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='Última edición',
    )
    duration_minutes = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name='Duración real (minutos)',
    )
    kettlebell_weight = models.DecimalField(
        max_digits=4,
        decimal_places=1,
        null=True,
        blank=True,
        verbose_name='Peso de kettlebell (kg)',
    )
    rpe = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(10)],
        verbose_name='Esfuerzo percibido (RPE 1-10)',
    )
    notes = models.CharField(max_length=300, blank=True, default='', verbose_name='Notas')
    client_session_id = models.UUIDField(
        null=True,
        blank=True,
        verbose_name='Identificador de sesión del cliente',
        help_text='Evita duplicar una sesión cuando el navegador reintenta el guardado.',
    )
    
    class Meta:
        ordering = ['-completed_at']
        verbose_name = 'Registro de Entrenamiento'
        verbose_name_plural = 'Registros de Entrenamiento'
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'client_session_id'],
                condition=models.Q(client_session_id__isnull=False),
                name='unique_user_client_session',
            ),
        ]

    def save(self, *args, **kwargs):
        if self.workout_id and self.workout:
            self.workout_title_snapshot = self.workout_title_snapshot or self.workout.title
            self.workout_difficulty_snapshot = self.workout_difficulty_snapshot or self.workout.difficulty
            self.workout_duration_snapshot = self.workout_duration_snapshot or self.workout.estimated_duration
        super().save(*args, **kwargs)
        
    def __str__(self):
        title = self.workout.title if self.workout else self.workout_title_snapshot or 'Rutina eliminada'
        return f"{self.user.username} - {title} ({self.completed_at.strftime('%Y-%m-%d')})"


class ExercisePerformance(models.Model):
    """Métricas de un ejercicio dentro de una sesión completada.

    ``WorkoutLog`` conserva las métricas agregadas de la rutina para no romper
    datos existentes. Este modelo permite registrar el progreso real de cada
    ejercicio sin trasladar el peso de un movimiento a otro.
    """

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='exercise_performances',
        verbose_name='Usuario',
    )
    workout_log = models.ForeignKey(
        WorkoutLog,
        on_delete=models.CASCADE,
        related_name='exercise_performances',
        verbose_name='Sesión',
    )
    workout_exercise = models.ForeignKey(
        WorkoutExercise,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='performances',
        verbose_name='Ejercicio de la rutina',
    )
    exercise = models.ForeignKey(
        Exercise,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='performance_logs',
        verbose_name='Ejercicio',
    )
    completed = models.BooleanField(default=True, verbose_name='Completado')
    sets_completed = models.PositiveSmallIntegerField(default=0, verbose_name='Series completadas')
    reps_completed = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name='Repeticiones completadas',
    )
    weight = models.DecimalField(
        max_digits=5,
        decimal_places=1,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal('0.1')), MaxValueValidator(Decimal('200'))],
        verbose_name='Peso usado (kg)',
    )
    rpe = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(10)],
        verbose_name='RPE del ejercicio',
    )
    notes = models.CharField(max_length=300, blank=True, default='', verbose_name='Notas')
    exercise_name_snapshot = models.CharField(max_length=200, blank=True, default='')
    exercise_category_snapshot = models.CharField(max_length=20, blank=True, default='')
    target_sets = models.PositiveSmallIntegerField(null=True, blank=True)
    target_reps = models.CharField(max_length=50, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-workout_log__completed_at', '-created_at']
        verbose_name = 'Rendimiento por ejercicio'
        verbose_name_plural = 'Rendimientos por ejercicio'
        constraints = [
            models.UniqueConstraint(
                fields=['workout_log', 'workout_exercise'],
                condition=models.Q(workout_exercise__isnull=False),
                name='unique_performance_per_workout_exercise',
            ),
        ]
        indexes = [
            models.Index(fields=['user', 'exercise', '-created_at']),
            models.Index(fields=['workout_log', 'exercise']),
        ]

    def save(self, *args, **kwargs):
        if self.exercise_id and self.exercise:
            self.exercise_name_snapshot = self.exercise_name_snapshot or self.exercise.name
            self.exercise_category_snapshot = self.exercise_category_snapshot or self.exercise.category
        if self.workout_exercise_id and self.workout_exercise:
            self.target_sets = self.target_sets if self.target_sets is not None else self.workout_exercise.sets
            self.target_reps = self.target_reps or self.workout_exercise.reps
        super().save(*args, **kwargs)

    def __str__(self):
        exercise_name = self.exercise.name if self.exercise else self.exercise_name_snapshot or 'Ejercicio eliminado'
        return f"{self.user.username} - {exercise_name}"

    @property
    def volume(self):
        """Volumen aproximado (series × repeticiones × peso), si está disponible."""
        if not self.sets_completed or not self.reps_completed or self.weight is None:
            return None
        return float(self.sets_completed * self.reps_completed * self.weight)


class PushSubscription(models.Model):
    """Suscripcion push de un navegador para notificaciones."""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='push_subscriptions')
    endpoint = models.URLField(max_length=500)
    p256dh = models.CharField(max_length=255)
    auth = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'endpoint')
        verbose_name = 'Suscripcion Push'
        verbose_name_plural = 'Suscripciones Push'

    def __str__(self):
        return f"Push: {self.user.username} ({self.endpoint[:50]}...)"
