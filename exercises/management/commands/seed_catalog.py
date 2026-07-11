from django.core.management.base import BaseCommand

from exercises.models import Exercise


class Command(BaseCommand):
    help = 'Puebla o actualiza el catalogo de ejercicios (upsert por nombre; seguro de re-ejecutar).'

    def add_arguments(self, parser):
        parser.add_argument(
            '--clear',
            action='store_true',
            help='Elimina todos los ejercicios existentes antes de poblar.',
        )

    def handle(self, *args, **options):
        # El catálogo vive en populate_exercises.py (raíz del repo, mismo
        # directorio que manage.py). Su django.setup() es idempotente.
        import populate_exercises as seed

        if options['clear']:
            seed.clear_exercises()

        created = seed.populate_exercises()
        total = Exercise.objects.count()
        self.stdout.write(self.style.SUCCESS(
            f'Catalogo sembrado: {created} ejercicios nuevos, {total} en total.'
        ))
