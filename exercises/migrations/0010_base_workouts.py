"""
Rutinas base públicas para que la sección de entrenamientos nunca esté vacía.

Se resuelven los ejercicios por nombre de forma flexible (coincide tanto con el
catálogo "Kettlebell X" de populate_exercises.py como con los nombres cortos de
la migración 0008). Si algún ejercicio no existe en la base de datos, la rutina
se rellena con los ejercicios disponibles para que nunca quede vacía.
"""
from django.db import migrations
from django.utils.text import slugify


# reps/notas por defecto según la categoría del ejercicio
CATEGORY_PRESCRIPTION = {
    'strength': ('8-12 reps', 'Descanso de 60-90s entre series.'),
    'cardio': ('40s trabajo / 20s descanso', 'Mantén la intensidad alta.'),
    'flexibility': ('45-60 segs', 'Movimiento lento y controlado.'),
    'full_body': ('10-12 reps', 'Cuida la técnica en cada repetición.'),
}
DEFAULT_PRESCRIPTION = ('10-12 reps', '')

# Cada rutina base: título, descripción, dificultad, duración y los términos de
# ejercicio que la componen (en orden). Los términos se buscan de forma flexible.
BASE_WORKOUTS = [
    {
        'title': 'Full Body Express',
        'description': 'Rutina rápida de cuerpo completo para activar todo el cuerpo en poco tiempo. Ideal para empezar.',
        'difficulty': 'beginner',
        'estimated_duration': 20,
        'exercises': ['Deadlift', 'Goblet Squat', 'Row', 'Swing', 'Halo'],
    },
    {
        'title': 'Fuerza Total',
        'description': 'Entrenamiento de fuerza con los patrones básicos de empuje, tracción y sentadilla usando kettlebell.',
        'difficulty': 'intermediate',
        'estimated_duration': 35,
        'exercises': ['Goblet Squat', 'Press', 'Row', 'Front Squat', 'Turkish Get-Up', 'Deadlift'],
    },
    {
        'title': 'Cardio Quema',
        'description': 'Circuito metabólico de alta intensidad para elevar pulsaciones y quemar calorías con la kettlebell.',
        'difficulty': 'intermediate',
        'estimated_duration': 25,
        'exercises': ['Swing', 'High Pull', 'Thruster', 'Burpee', 'March in Place'],
    },
    {
        'title': 'Movilidad y Core',
        'description': 'Sesión centrada en movilidad, estabilidad del core y control postural con carga ligera.',
        'difficulty': 'intermediate',
        'estimated_duration': 20,
        'exercises': ['Halo', 'Windmill', 'Cossack Squat', 'Arm Bar', 'Overhead Squat'],
    },
    {
        'title': 'Principiante Total',
        'description': 'Primera toma de contacto con la kettlebell: movimientos sencillos para aprender la técnica base.',
        'difficulty': 'beginner',
        'estimated_duration': 30,
        'exercises': ['Deadlift', 'Goblet Squat', 'Row', 'Farmer Walk', 'Halo', 'March in Place'],
    },
]

MIN_EXERCISES_PER_WORKOUT = 4


def find_exercise(Exercise, term):
    """Resuelve un ejercicio por nombre de forma tolerante al prefijo 'Kettlebell'."""
    return (
        Exercise.objects.filter(name__iexact=term).first()
        or Exercise.objects.filter(name__iexact=f'Kettlebell {term}').first()
        or Exercise.objects.filter(name__icontains=term).first()
    )


def unique_slug(Workout, title):
    base = slugify(title) or 'rutina'
    slug = base
    counter = 1
    while Workout.objects.filter(slug=slug).exists():
        slug = f'{base}-{counter}'
        counter += 1
    return slug


def create_base_workouts(apps, schema_editor):
    Workout = apps.get_model('exercises', 'Workout')
    WorkoutExercise = apps.get_model('exercises', 'WorkoutExercise')
    Exercise = apps.get_model('exercises', 'Exercise')

    if not Exercise.objects.exists():
        return  # sin ejercicios no hay nada que enlazar

    for spec in BASE_WORKOUTS:
        if Workout.objects.filter(title=spec['title'], created_by__isnull=True).exists():
            continue  # idempotente: no duplicar

        # Resolver ejercicios por nombre, sin repetir
        resolved = []
        seen_ids = set()
        for term in spec['exercises']:
            ex = find_exercise(Exercise, term)
            if ex and ex.id not in seen_ids:
                resolved.append(ex)
                seen_ids.add(ex.id)

        # Rellenar para que nunca quede por debajo del mínimo (ni vacía)
        if len(resolved) < MIN_EXERCISES_PER_WORKOUT:
            filler = Exercise.objects.exclude(id__in=seen_ids).order_by('difficulty', 'name')
            for ex in filler:
                resolved.append(ex)
                seen_ids.add(ex.id)
                if len(resolved) >= MIN_EXERCISES_PER_WORKOUT:
                    break

        if not resolved:
            continue

        workout = Workout.objects.create(
            title=spec['title'],
            slug=unique_slug(Workout, spec['title']),
            description=spec['description'],
            difficulty=spec['difficulty'],
            estimated_duration=spec['estimated_duration'],
            created_by=None,
            is_public=True,
        )

        for order, ex in enumerate(resolved, start=1):
            reps, notes = CATEGORY_PRESCRIPTION.get(ex.category, DEFAULT_PRESCRIPTION)
            WorkoutExercise.objects.create(
                workout=workout,
                exercise=ex,
                order=order,
                sets=3,
                reps=reps,
                notes=notes,
            )


def remove_base_workouts(apps, schema_editor):
    Workout = apps.get_model('exercises', 'Workout')
    titles = [spec['title'] for spec in BASE_WORKOUTS]
    Workout.objects.filter(title__in=titles, created_by__isnull=True).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('exercises', '0009_workout_created_by'),
    ]

    operations = [
        migrations.RunPython(create_base_workouts, remove_base_workouts),
    ]
