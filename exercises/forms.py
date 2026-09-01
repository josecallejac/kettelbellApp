from django import forms
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.contrib.auth.models import User
from django.forms import inlineformset_factory, modelformset_factory
from django.utils import timezone

from .models import ExercisePerformance, PlannedSession, UserProfile, Workout, WorkoutExercise, WorkoutLog
from .weights import invalid_weight_tokens, normalize_available_weights


def _clean_weight_inventory(value):
    invalid = invalid_weight_tokens(value)
    if invalid:
        labels = ', '.join(token or '(vacio)' for token in invalid)
        raise forms.ValidationError(
            'Cada peso debe ser un numero finito entre 0.1 y 200 kg. '
            f'Revisa: {labels}.'
        )
    return normalize_available_weights(value)


class CustomUserCreationForm(UserCreationForm):
    class Meta:
        model = User
        fields = ('username', 'email')
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.update({'class': 'form-control'})

class CustomAuthenticationForm(AuthenticationForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.update({'class': 'form-control'})

class WorkoutForm(forms.ModelForm):
    class Meta:
        model = Workout
        fields = ['title', 'description', 'difficulty', 'estimated_duration', 'is_public']
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'Ej: Rutina de Piernas Explosiva'}),
            'description': forms.Textarea(attrs={'class': 'form-input', 'rows': 3}),
            'difficulty': forms.Select(attrs={'class': 'form-select'}),
            'estimated_duration': forms.NumberInput(attrs={'class': 'form-input'}),
            'is_public': forms.CheckboxInput(attrs={'class': 'form-checkbox'}),
        }

class UserProfileForm(forms.ModelForm):
    class Meta:
        model = UserProfile
        fields = ['level', 'goal', 'available_weights']
        widgets = {
            'level': forms.Select(attrs={'class': 'form-select'}),
            'goal': forms.Select(attrs={'class': 'form-select'}),
            'available_weights': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'Ej: 8, 12, 16'}),
        }

    def clean_available_weights(self):
        return _clean_weight_inventory(self.cleaned_data.get('available_weights', ''))


class TrainingPlanForm(forms.Form):
    """Configuración del ciclo adaptativo de cuatro semanas."""

    WEEKDAY_CHOICES = [
        ('0', 'Lunes'),
        ('1', 'Martes'),
        ('2', 'Miércoles'),
        ('3', 'Jueves'),
        ('4', 'Viernes'),
        ('5', 'Sábado'),
        ('6', 'Domingo'),
    ]

    level = forms.ChoiceField(
        choices=UserProfile._meta.get_field('level').choices,
        widget=forms.Select(attrs={'class': 'form-select'}),
        label='Tu nivel',
    )
    goal = forms.ChoiceField(
        choices=UserProfile.GOAL_CHOICES,
        widget=forms.Select(attrs={'class': 'form-select'}),
        label='Tu objetivo',
    )
    available_weights = forms.CharField(
        required=False,
        max_length=100,
        widget=forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'Ej: 8, 12, 16'}),
        label='Kettlebells disponibles (kg)',
    )
    sessions_per_week = forms.IntegerField(
        min_value=2,
        max_value=5,
        initial=3,
        widget=forms.NumberInput(attrs={'class': 'form-input', 'min': 2, 'max': 5}),
        label='Sesiones por semana',
    )
    preferred_weekdays = forms.MultipleChoiceField(
        choices=WEEKDAY_CHOICES,
        widget=forms.CheckboxSelectMultiple,
        label='Días preferidos',
    )
    session_duration = forms.IntegerField(
        min_value=10,
        max_value=120,
        initial=30,
        widget=forms.NumberInput(attrs={'class': 'form-input', 'min': 10, 'max': 120, 'step': 5}),
        label='Duración habitual (minutos)',
    )
    start_date = forms.DateField(
        initial=timezone.localdate,
        widget=forms.DateInput(attrs={'class': 'form-input', 'type': 'date'}),
        label='Fecha de inicio',
    )
    reminders_enabled = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={'class': 'form-checkbox'}),
        label='Recordarme por push',
    )
    reminder_time = forms.TimeField(
        required=False,
        initial='19:00',
        input_formats=['%H:%M'],
        widget=forms.TimeInput(attrs={'class': 'form-input', 'type': 'time'}),
        label='Hora del recordatorio',
    )

    def __init__(self, *args, profile=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.profile = profile
        if profile and not args:
            self.initial.update({
                'level': profile.level,
                'goal': profile.goal,
                'available_weights': profile.available_weights,
            })
            if not self.initial.get('preferred_weekdays'):
                self.initial['preferred_weekdays'] = ['0', '2', '4']
        if not args:
            self.initial.setdefault('start_date', timezone.localdate())

    def clean_preferred_weekdays(self):
        days = sorted({int(day) for day in self.cleaned_data['preferred_weekdays']})
        sessions = self.cleaned_data.get('sessions_per_week')
        if sessions and len(days) != sessions:
            raise forms.ValidationError('Selecciona exactamente tantos días como sesiones semanales.')
        return days

    def clean_start_date(self):
        value = self.cleaned_data['start_date']
        if value < timezone.localdate():
            raise forms.ValidationError('La fecha de inicio no puede estar en el pasado.')
        return value

    def clean_available_weights(self):
        return _clean_weight_inventory(self.cleaned_data.get('available_weights', ''))

    def clean(self):
        cleaned = super().clean()
        if cleaned.get('reminders_enabled') and not cleaned.get('reminder_time'):
            self.add_error('reminder_time', 'Indica una hora para activar los recordatorios.')
        return cleaned


class SessionReadinessForm(forms.Form):
    """Chequeo breve que se completa antes de generar una sesión del plan."""

    energy_level = forms.TypedChoiceField(
        choices=PlannedSession.ENERGY_CHOICES,
        coerce=int,
        widget=forms.Select(attrs={'class': 'form-select'}),
        label='¿Cuánta energía tienes hoy?',
    )
    pain_level = forms.ChoiceField(
        choices=PlannedSession.PAIN_CHOICES,
        widget=forms.Select(attrs={'class': 'form-select'}),
        label='¿Tienes dolor o alguna molestia?',
    )
    available_minutes = forms.IntegerField(
        min_value=10,
        max_value=120,
        widget=forms.NumberInput(attrs={'class': 'form-input', 'min': 10, 'max': 120, 'step': 5}),
        label='¿Cuántos minutos tienes disponibles?',
    )


class WorkoutLogEditForm(forms.ModelForm):
    """Editable summary fields for one completed workout."""

    duration_minutes = forms.IntegerField(
        required=False,
        min_value=1,
        max_value=600,
        widget=forms.NumberInput(attrs={'class': 'form-input', 'min': 1, 'max': 600}),
        label='Duración real (minutos)',
    )
    rpe = forms.IntegerField(
        required=False,
        min_value=1,
        max_value=10,
        widget=forms.NumberInput(attrs={'class': 'form-input', 'min': 1, 'max': 10}),
        label='Esfuerzo percibido (RPE 1-10)',
    )
    kettlebell_weight = forms.DecimalField(
        required=False,
        min_value=1,
        max_value=200,
        max_digits=4,
        decimal_places=1,
        widget=forms.NumberInput(attrs={'class': 'form-input', 'min': 1, 'max': 200, 'step': '0.5'}),
        label='Peso general (kg)',
        help_text='Solo se usa cuando la sesión antigua no tiene métricas por ejercicio.',
    )
    notes = forms.CharField(
        required=False,
        max_length=300,
        widget=forms.TextInput(attrs={'class': 'form-input', 'maxlength': 300}),
        label='Notas',
    )

    class Meta:
        model = WorkoutLog
        fields = ['duration_minutes', 'rpe', 'kettlebell_weight', 'notes']

    def __init__(self, *args, has_details=False, **kwargs):
        super().__init__(*args, **kwargs)
        if has_details:
            self.fields.pop('kettlebell_weight', None)


class ExercisePerformanceEditForm(forms.ModelForm):
    """Editable metrics while keeping exercise identity and targets locked."""

    sets_completed = forms.IntegerField(
        min_value=0,
        max_value=100,
        widget=forms.NumberInput(attrs={'class': 'form-input', 'min': 0, 'max': 100}),
        label='Series',
    )
    reps_completed = forms.IntegerField(
        required=False,
        min_value=0,
        max_value=1000,
        widget=forms.NumberInput(attrs={'class': 'form-input', 'min': 0, 'max': 1000}),
        label='Repeticiones',
    )
    weight = forms.DecimalField(
        required=False,
        min_value=0.1,
        max_value=200,
        max_digits=5,
        decimal_places=1,
        widget=forms.NumberInput(attrs={'class': 'form-input', 'min': 0.1, 'max': 200, 'step': '0.1'}),
        label='Peso (kg)',
    )
    rpe = forms.IntegerField(
        required=False,
        min_value=1,
        max_value=10,
        widget=forms.NumberInput(attrs={'class': 'form-input', 'min': 1, 'max': 10}),
        label='RPE',
    )
    notes = forms.CharField(
        required=False,
        max_length=300,
        widget=forms.TextInput(attrs={'class': 'form-input', 'maxlength': 300}),
        label='Notas',
    )

    class Meta:
        model = ExercisePerformance
        fields = ['completed', 'sets_completed', 'reps_completed', 'weight', 'rpe', 'notes']
        widgets = {
            'completed': forms.CheckboxInput(attrs={'class': 'form-checkbox'}),
        }


ExercisePerformanceEditFormSet = modelformset_factory(
    ExercisePerformance,
    form=ExercisePerformanceEditForm,
    extra=0,
    can_delete=False,
)


WorkoutExerciseFormSet = inlineformset_factory(
    Workout, WorkoutExercise,
    fields=['exercise', 'sets', 'reps', 'notes'],
    extra=1,
    can_delete=True,
    widgets={
        'exercise': forms.Select(attrs={'class': 'form-select'}),
        'sets': forms.NumberInput(attrs={'class': 'form-input w-20'}),
        'reps': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'Ej: 10 reps'}),
        'notes': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'Opcional'}),
    }
)
