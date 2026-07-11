from django import forms
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.contrib.auth.models import User
from django.forms import inlineformset_factory

from .models import UserProfile, Workout, WorkoutExercise


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
