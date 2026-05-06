"""
Generated data migration to add example Exercise entries.
"""
from django.db import migrations
from django.utils.text import slugify


def create_example_exercises(apps, schema_editor):
    Exercise = apps.get_model('exercises', 'Exercise')

    examples = [
        {
            'name': 'Kettlebell Swing',
            'description': 'Movimiento balístico centrado en la extensión de cadera para generar potencia.',
            'instructions': '1. Colócate con los pies al ancho de caderas.\n2. Sujeta la kettlebell con ambas manos.\n3. Flexiona ligeramente las rodillas y empuja la cadera hacia atrás.\n4. Extiende la cadera con fuerza y deja que la kettlebell llegue a la altura del pecho.\n5. Controla la bajada con el core y repite.',
            'category': 'strength',
            'difficulty': 'intermediate',
            'benefits': 'Mejora la potencia de cadena posterior y la capacidad cardiovascular cuando se realiza en series.',
            'muscles_targeted': 'Glúteos, isquiotibiales, espalda baja, core, hombros (estabilización)',
            'common_mistakes': 'Uso excesivo de los brazos en lugar de la cadera; espalda redondeada; rango de movimiento demasiado corto.',
            'duration_minutes': 2,
            'calories_burned': 50,
            'equipment': 'Kettlebell',
            'variations': 'Russian swing (hasta el pecho), American swing (por encima de la cabeza), one-arm swing',
            'setup_tips': 'Coloca la kettlebell ligeramente delante de ti al inicio; mira al frente y mantén el pecho abierto.',
            'progressions': 'Aumentar el peso o las repeticiones; progresar a swings a una mano o con más rango.',
            'precautions': 'Evitar si existe dolor lumbar agudo o técnica inestable; empezar con poco peso.',
            'video_url': 'https://www.youtube.com/watch?v=0Kqs2ZqEmmA',
        },
        {
            'name': 'Goblet Squat',
            'description': 'Sentadilla con carga frontal para trabajar piernas y mantener la postura.',
            'instructions': '1. Sujeta la kettlebell por el asa frente al pecho.\n2. Baja en sentadilla manteniendo el pecho erguido y las rodillas alineadas con los pies.\n3. Empuja hacia arriba con los talones hasta volver a la posición inicial.',
            'category': 'strength',
            'difficulty': 'beginner',
            'benefits': 'Mejora fuerza de cuádriceps, glúteos y movilidad de cadera; fácil de aprender.',
            'muscles_targeted': 'Cuádriceps, glúteos, aductores, core',
            'common_mistakes': 'Inclinar demasiado el torso; rodillas que se colapsan hacia adentro.',
            'duration_minutes': 3,
            'calories_burned': 40,
            'equipment': 'Kettlebell',
            'variations': 'Sumo goblet squat, tempo goblet squat (descenso lento)',
            'setup_tips': 'Mantén los codos pegados al torso y la kettlebell cerca del pecho para facilitar la posición.',
            'progressions': 'Aumentar peso, pasar a sentadilla frontal con barra.',
            'precautions': 'Revisar movilidad de tobillo y rodilla; evitar si hay dolor articular agudo.',
            'video_url': 'https://www.youtube.com/watch?v=6xwGFn-J_Q4',
        },
        {
            'name': 'Turkish Get-Up',
            'description': 'Ejercicio completo para fuerza y movilidad, progresivo y técnico.',
            'instructions': '1. Acuéstate sujetando la kettlebell con un brazo extendido.\n2. Levanta el torso y apoya el antebrazo, luego la mano, despega la cadera y ponte de rodilla.\n3. Levántate hasta la posición de pie manteniendo la kettlebell estable.\n4. Deshaz los pasos en sentido inverso para volver al suelo.',
            'category': 'full_body',
            'difficulty': 'advanced',
            'benefits': 'Mejora estabilidad de hombro, fuerza del core y movilidad general.',
            'muscles_targeted': 'Hombros, core, glúteos, cuádriceps',
            'common_mistakes': 'Mover la kettlebell con el brazo en lugar de estabilizar; prisa en las transiciones.',
            'duration_minutes': 5,
            'calories_burned': 80,
            'equipment': 'Kettlebell, espacio libre',
            'variations': 'Get-up con peso ligero para aprender la técnica; progresión por pasos.',
            'setup_tips': 'Practicar sin peso primero; mantener la mirada hacia la kettlebell durante todo el movimiento.',
            'progressions': 'Aumentar peso gradualmente; reducir apoyo con la mano en el suelo.',
            'precautions': 'No realizar con hombro lesionado; avanzar despacio y controlar cada paso.',
            'video_url': 'https://www.youtube.com/watch?v=U2V3aFJ2P1o',
        },
    ]

    for ex in examples:
        slug = slugify(ex['name'])
        # Use update_or_create so running the migration twice won't duplicate
        Exercise.objects.update_or_create(slug=slug, defaults={**ex, 'slug': slug})


def delete_example_exercises(apps, schema_editor):
    Exercise = apps.get_model('exercises', 'Exercise')
    slugs = ['kettlebell-swing', 'goblet-squat', 'turkish-get-up']
    Exercise.objects.filter(slug__in=slugs).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('exercises', '0007_exercise_equipment_exercise_precautions_and_more'),
    ]

    operations = [
        migrations.RunPython(create_example_exercises, delete_example_exercises),
    ]
