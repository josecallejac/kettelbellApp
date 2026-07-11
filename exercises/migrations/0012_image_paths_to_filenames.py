# Las imágenes del catálogo pasaron de media/exercises/ a
# exercises/static/exercises/img/catalog/; el campo image ahora guarda solo
# el nombre de archivo (ej: kettlebell_swing.jpg) en lugar de la ruta de media.
from django.db import migrations


def strip_media_prefix(apps, schema_editor):
    Exercise = apps.get_model('exercises', 'Exercise')
    for exercise in Exercise.objects.exclude(image=''):
        if '/' in exercise.image:
            exercise.image = exercise.image.rsplit('/', 1)[-1]
            exercise.save(update_fields=['image'])


def restore_media_prefix(apps, schema_editor):
    Exercise = apps.get_model('exercises', 'Exercise')
    for exercise in Exercise.objects.exclude(image=''):
        if '/' not in exercise.image:
            exercise.image = f'exercises/{exercise.image}'
            exercise.save(update_fields=['image'])


class Migration(migrations.Migration):

    dependencies = [
        ('exercises', '0011_alter_favorite_unique_together_and_more'),
    ]

    operations = [
        migrations.RunPython(strip_media_prefix, restore_media_prefix),
    ]
