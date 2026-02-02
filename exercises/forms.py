from django import forms
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.contrib.auth.models import User

class CustomUserCreationForm(UserCreationForm):
    class Meta:
        model = User
        fields = ('username', 'email')
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.update({
                'class': 'w-full bg-gray-700 border border-gray-600 rounded-lg px-4 py-3 text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent transition duration-200'
            })

class CustomAuthenticationForm(AuthenticationForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.update({
                'class': 'w-full bg-gray-700 border border-gray-600 rounded-lg px-4 py-3 text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent transition duration-200'
            })

from django.forms import inlineformset_factory
from .models import Workout, WorkoutExercise

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
