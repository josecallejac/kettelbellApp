from django.db import models
from django.urls import reverse
from django.utils.text import slugify
from django.contrib.auth.models import User

class Favorite(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='favorites')
    exercise = models.ForeignKey('Exercise', on_delete=models.CASCADE, related_name='favorited_by')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'exercise')
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
        verbose_name='Categoría'
    )
    difficulty = models.CharField(
        max_length=20,
        choices=DIFFICULTY_CHOICES,
        verbose_name='Dificultad'
    )
    benefits = models.TextField(verbose_name='Beneficios', blank=True)
    image = models.ImageField(upload_to='exercises/', blank=True, null=True, verbose_name='Imagen')
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
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)
    
    def get_absolute_url(self):
        return reverse('exercises:detail', kwargs={'slug': self.slug})

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
    created_at = models.DateTimeField(auto_now_add=True)
    is_public = models.BooleanField(default=True, verbose_name='Es público')

    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = slugify(self.title)
            slug = base_slug
            counter = 1
            # Ensure unique slug
            while self.__class__.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug = f"{base_slug}-{counter}"
                counter += 1
            self.slug = slug
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

class WorkoutLog(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='workout_logs')
    workout = models.ForeignKey(Workout, on_delete=models.CASCADE)
    completed_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-completed_at']
        verbose_name = 'Registro de Entrenamiento'
        verbose_name_plural = 'Registros de Entrenamiento'
        
    def __str__(self):
        return f"{self.user.username} - {self.workout.title} ({self.completed_at.strftime('%Y-%m-%d')})"
