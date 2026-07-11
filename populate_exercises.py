"""
Script para poblar la base de datos con ejercicios de kettlebell.
Ejecutar con: python manage.py shell < populate_exercises.py
O: python populate_exercises.py
"""

import os
import sys
from pathlib import Path

import django

# Configurar Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'kettelbell.settings')
django.setup()

from django.conf import settings
from django.utils.text import slugify

from exercises.models import Exercise

CATALOG_IMAGES_DIR = Path(settings.BASE_DIR) / 'exercises/static/exercises/img/catalog'


def catalog_image_for(name):
    """Nombre de archivo de la imagen del catalogo si existe en static, o ''."""
    filename = name.lower().replace(':', '').replace(',', '').replace(' ', '_') + '.jpg'
    if (CATALOG_IMAGES_DIR / filename).exists():
        return filename
    return ''

def clear_exercises():
    """Eliminar todos los ejercicios existentes (opcional)"""
    Exercise.objects.all().delete()
    print("[OK] Base de datos limpiada")

def populate_exercises():
    """Poblar la base de datos con ejercicios de kettlebell"""
    
    exercises_data = [
        # ==================== EJERCICIOS DE FUERZA - PRINCIPIANTE ====================
        {
            'name': 'Kettlebell Deadlift',
            'description': 'El peso muerto con kettlebell es un ejercicio fundamental que trabaja toda la cadena posterior del cuerpo.',
            'instructions': '''1. Coloca la kettlebell entre tus pies, separados al ancho de hombros
2. Flexiona las caderas y rodillas para agarrar la kettlebell con ambas manos
3. Mantén la espalda recta y el pecho elevado
4. Empuja a través de los talones para levantar la kettlebell
5. Extiende completamente las caderas en la parte superior
6. Baja la kettlebell de forma controlada a la posición inicial''',
            'category': 'strength',
            'difficulty': 'beginner',
            'benefits': 'Fortalece glúteos, isquiotibiales, espalda baja y core. Mejora la postura y la fuerza funcional.',
            'duration_minutes': 10,
            'calories_burned': 80,
            'video_url': 'https://www.youtube.com/watch?v=V7iXfwMCX24',
        },
        {
            'name': 'Kettlebell Goblet Squat',
            'description': 'Sentadilla sosteniendo la kettlebell frente al pecho, excelente para aprender la técnica correcta de sentadilla.',
            'instructions': '''1. Sostén la kettlebell con ambas manos frente a tu pecho
2. Mantén los codos apuntando hacia abajo
3. Separa los pies al ancho de hombros
4. Baja en sentadilla manteniendo el pecho elevado
5. Desciende hasta que los codos toquen las rodillas
6. Empuja a través de los talones para volver arriba''',
            'category': 'strength',
            'difficulty': 'beginner',
            'benefits': 'Desarrolla fuerza en piernas y glúteos. Mejora la movilidad de cadera y tobillo. Fortalece el core.',
            'duration_minutes': 12,
            'calories_burned': 90,
            'video_url': 'https://www.youtube.com/watch?v=2gP2F7ryJnU',
        },
        {
            'name': 'Kettlebell Row',
            'description': 'Remo con kettlebell para desarrollar la espalda y los brazos.',
            'instructions': '''1. Coloca una mano en un banco y la otra sostiene la kettlebell
2. Mantén la espalda paralela al suelo
3. Tira de la kettlebell hacia tu cadera
4. Mantén el codo cerca del cuerpo
5. Baja de forma controlada
6. Completa todas las repeticiones antes de cambiar de lado''',
            'category': 'strength',
            'difficulty': 'beginner',
            'benefits': 'Fortalece la espalda media y superior, bíceps y core. Mejora la postura.',
            'duration_minutes': 10,
            'calories_burned': 70,
            'video_url': 'https://www.youtube.com/watch?v=j2jeLc3UdhQ',
        },
        {
            'name': 'Kettlebell Halo',
            'description': 'Ejercicio de movilidad y fuerza para hombros que consiste en rotar la kettlebell alrededor de la cabeza.',
            'instructions': '''1. Sostén la kettlebell boca abajo frente a tu pecho
2. Mueve la kettlebell alrededor de tu cabeza en círculo
3. Mantén el core activado y la postura erguida
4. Completa el círculo de forma controlada
5. Alterna la dirección después de cada serie''',
            'category': 'strength',
            'difficulty': 'beginner',
            'benefits': 'Mejora la movilidad de hombros. Fortalece los músculos estabilizadores del hombro y el core.',
            'duration_minutes': 8,
            'calories_burned': 50,
            'video_url': 'https://www.youtube.com/watch?v=Trp0gHfveJM',
        },
        {
            'name': 'Kettlebell Farmer Walk',
            'description': 'Caminar sosteniendo kettlebells a los lados, excelente para fuerza de agarre y core.',
            'instructions': '''1. Sostén una kettlebell en cada mano a los lados
2. Mantén los hombros hacia atrás y el pecho elevado
3. Camina con pasos controlados manteniendo la postura
4. Mantén el core activado durante todo el movimiento
5. Camina la distancia deseada o por tiempo''',
            'category': 'strength',
            'difficulty': 'beginner',
            'benefits': 'Desarrolla fuerza de agarre, estabilidad del core y resistencia. Mejora la postura.',
            'duration_minutes': 10,
            'calories_burned': 75,
            'video_url': 'https://www.youtube.com/watch?v=CZ5XzjMgd6U',
        },

        # ==================== EJERCICIOS DE FUERZA - INTERMEDIO ====================
        {
            'name': 'Kettlebell Swing',
            'description': 'El swing es el ejercicio más icónico con kettlebell, un movimiento explosivo de cadera.',
            'instructions': '''1. Coloca la kettlebell a un pie frente a ti
2. Flexiona las caderas y agarra la kettlebell con ambas manos
3. Balancea la kettlebell entre las piernas
4. Impulsa explosivamente con las caderas
5. La kettlebell debe elevarse hasta la altura del pecho
6. Deja que la kettlebell caiga naturalmente entre las piernas
7. Repite el movimiento de forma fluida''',
            'category': 'strength',
            'difficulty': 'intermediate',
            'benefits': 'Desarrolla potencia explosiva, fortalece glúteos, isquiotibiales y core. Excelente para acondicionamiento.',
            'duration_minutes': 15,
            'calories_burned': 150,
            'video_url': 'https://www.youtube.com/watch?v=aSYap2yhW8s',
        },
        {
            'name': 'Kettlebell Clean',
            'description': 'Movimiento técnico que lleva la kettlebell desde el suelo hasta la posición de rack.',
            'instructions': '''1. Comienza con la kettlebell entre los pies
2. Agarra la kettlebell con una mano
3. Balancea la kettlebell entre las piernas
4. Impulsa con las caderas y tira de la kettlebell hacia arriba
5. Rota la muñeca y recibe la kettlebell en posición de rack
6. La kettlebell debe descansar en el antebrazo
7. Baja de forma controlada y repite''',
            'category': 'strength',
            'difficulty': 'intermediate',
            'benefits': 'Desarrolla potencia, coordinación y fuerza total del cuerpo. Mejora la técnica para movimientos avanzados.',
            'duration_minutes': 12,
            'calories_burned': 110,
            'video_url': 'https://www.youtube.com/watch?v=arDE41m8qP8',
        },
        {
            'name': 'Kettlebell Press',
            'description': 'Press militar con kettlebell para desarrollar fuerza de hombros.',
            'instructions': '''1. Comienza con la kettlebell en posición de rack
2. Mantén el core activado y los glúteos apretados
3. Presiona la kettlebell hacia arriba en línea recta
4. Extiende completamente el brazo en la parte superior
5. Baja de forma controlada a la posición de rack
6. Mantén la muñeca recta durante todo el movimiento''',
            'category': 'strength',
            'difficulty': 'intermediate',
            'benefits': 'Fortalece hombros, tríceps y core. Mejora la estabilidad del hombro.',
            'duration_minutes': 10,
            'calories_burned': 85,
            'video_url': 'https://www.youtube.com/watch?v=kdPSGNnzqJs',
        },
        {
            'name': 'Kettlebell Turkish Get-Up',
            'description': 'Ejercicio complejo que involucra levantarse desde el suelo hasta estar de pie con la kettlebell sobre la cabeza.',
            'instructions': '''1. Acuéstate boca arriba con la kettlebell en una mano
2. Presiona la kettlebell hacia arriba con el brazo extendido
3. Flexiona la rodilla del mismo lado
4. Apóyate en el codo opuesto
5. Levanta las caderas del suelo
6. Pasa la pierna extendida hacia atrás
7. Ponte de pie manteniendo la kettlebell arriba
8. Invierte los pasos para volver al suelo''',
            'category': 'strength',
            'difficulty': 'intermediate',
            'benefits': 'Ejercicio de cuerpo completo que mejora fuerza, movilidad, estabilidad y coordinación.',
            'duration_minutes': 15,
            'calories_burned': 120,
            'video_url': 'https://www.youtube.com/watch?v=mTZE6EeWUeA',
        },
        {
            'name': 'Kettlebell Windmill',
            'description': 'Ejercicio de movilidad y fuerza que trabaja oblicuos, hombros y caderas.',
            'instructions': '''1. Presiona la kettlebell sobre la cabeza con un brazo
2. Gira los pies 45 grados alejándose del brazo con kettlebell
3. Mantén la vista en la kettlebell
4. Flexiona lateralmente hacia el lado opuesto
5. Baja hasta tocar el suelo con la mano libre
6. Mantén el brazo con kettlebell vertical
7. Vuelve a la posición inicial''',
            'category': 'strength',
            'difficulty': 'intermediate',
            'benefits': 'Mejora la movilidad de cadera y hombro. Fortalece oblicuos y estabilizadores del hombro.',
            'duration_minutes': 12,
            'calories_burned': 95,
            'video_url': 'https://www.youtube.com/watch?v=WwwtyQghUqQ',
        },
        {
            'name': 'Kettlebell Snatch',
            'description': 'Movimiento explosivo que lleva la kettlebell desde el suelo hasta sobre la cabeza en un solo movimiento.',
            'instructions': '''1. Comienza con la kettlebell entre los pies
2. Agarra la kettlebell con una mano
3. Balancea entre las piernas
4. Impulsa explosivamente con las caderas
5. Tira de la kettlebell hacia arriba en línea recta
6. Perfora el brazo hacia arriba cuando la kettlebell pase la cabeza
7. Recibe la kettlebell con el brazo extendido
8. Baja de forma controlada''',
            'category': 'strength',
            'difficulty': 'intermediate',
            'benefits': 'Desarrolla potencia explosiva máxima. Fortalece todo el cuerpo y mejora el acondicionamiento.',
            'duration_minutes': 15,
            'calories_burned': 140,
            'video_url': 'https://www.youtube.com/watch?v=KUj0N9R6jN8',
        },

        # ==================== EJERCICIOS DE FUERZA - AVANZADO ====================
        {
            'name': 'Kettlebell Double Clean and Press',
            'description': 'Clean y press con dos kettlebells simultáneamente, requiere gran fuerza y coordinación.',
            'instructions': '''1. Coloca dos kettlebells entre los pies
2. Agarra ambas kettlebells
3. Realiza un clean doble a posición de rack
4. Desde rack, presiona ambas kettlebells simultáneamente
5. Baja a rack y luego al suelo de forma controlada
6. Mantén el core activado durante todo el movimiento''',
            'category': 'strength',
            'difficulty': 'advanced',
            'benefits': 'Desarrolla fuerza máxima en todo el cuerpo. Mejora la coordinación bilateral y la estabilidad del core.',
            'duration_minutes': 15,
            'calories_burned': 160,
            'video_url': 'https://www.youtube.com/watch?v=U_wXNO10hQ0',
        },
        {
            'name': 'Kettlebell Double Snatch',
            'description': 'Snatch con dos kettlebells simultáneamente, movimiento explosivo avanzado.',
            'instructions': '''1. Coloca dos kettlebells entre los pies
2. Agarra ambas kettlebells
3. Balancea entre las piernas
4. Impulsa explosivamente con las caderas
5. Tira de ambas kettlebells hacia arriba
6. Perfora ambos brazos simultáneamente
7. Recibe con brazos extendidos sobre la cabeza
8. Baja de forma controlada''',
            'category': 'strength',
            'difficulty': 'advanced',
            'benefits': 'Máximo desarrollo de potencia explosiva. Fortalece todo el cuerpo y mejora el acondicionamiento extremo.',
            'duration_minutes': 15,
            'calories_burned': 180,
            'video_url': 'https://www.youtube.com/watch?v=yk9mXD3iGD4',
        },
        {
            'name': 'Kettlebell Pistol Squat',
            'description': 'Sentadilla a una pierna sosteniendo la kettlebell, requiere fuerza y equilibrio excepcionales.',
            'instructions': '''1. Sostén la kettlebell frente al pecho
2. Levanta una pierna del suelo
3. Baja en sentadilla sobre una sola pierna
4. Mantén la pierna elevada extendida al frente
5. Desciende lo más bajo posible
6. Empuja a través del talón para volver arriba
7. Completa todas las repeticiones antes de cambiar de pierna''',
            'category': 'strength',
            'difficulty': 'advanced',
            'benefits': 'Desarrolla fuerza unilateral extrema en piernas. Mejora el equilibrio y la movilidad de tobillo.',
            'duration_minutes': 12,
            'calories_burned': 130,
            'video_url': 'https://www.youtube.com/watch?v=Iy0J5Z4LWgE',
        },
        {
            'name': 'Kettlebell Bent Press',
            'description': 'Press antiguo que combina fuerza y movilidad, llevando la kettlebell desde rack hasta overhead mediante flexión lateral.',
            'instructions': '''1. Comienza con la kettlebell en posición de rack
2. Flexiona lateralmente alejándote de la kettlebell
3. Mantén la vista en la kettlebell
4. Continúa flexionando mientras extiendes el brazo
5. Termina con el brazo completamente extendido
6. Vuelve a la posición inicial de forma controlada''',
            'category': 'strength',
            'difficulty': 'advanced',
            'benefits': 'Desarrolla fuerza de hombro única. Mejora la movilidad de cadera y torso.',
            'duration_minutes': 12,
            'calories_burned': 100,
            'video_url': 'https://www.youtube.com/watch?v=C4DwND4eit4',
        },
        {
            'name': 'Kettlebell Bottoms-Up Press',
            'description': 'Press con la kettlebell invertida, requiere estabilidad extrema del hombro y muñeca.',
            'instructions': '''1. Limpia la kettlebell a posición de rack
2. Rota la kettlebell para que la bola quede arriba
3. Mantén la kettlebell equilibrada con el mango hacia abajo
4. Presiona hacia arriba manteniendo el equilibrio
5. Mantén la muñeca fuerte y estable
6. Baja de forma controlada a rack''',
            'category': 'strength',
            'difficulty': 'advanced',
            'benefits': 'Desarrolla estabilidad extrema de hombro y muñeca. Mejora la fuerza de agarre y el control motor.',
            'duration_minutes': 10,
            'calories_burned': 90,
            'video_url': 'https://www.youtube.com/shorts/LYTecEEmhUc',
        },

        # ==================== EJERCICIOS DE CARDIO - PRINCIPIANTE ====================
        {
            'name': 'Kettlebell March in Place',
            'description': 'Marcha en el lugar sosteniendo la kettlebell, excelente para principiantes.',
            'instructions': '''1. Sostén la kettlebell frente al pecho
2. Marcha en el lugar elevando las rodillas
3. Mantén el core activado
4. Alterna las piernas de forma rítmica
5. Mantén la postura erguida durante todo el ejercicio''',
            'category': 'cardio',
            'difficulty': 'beginner',
            'benefits': 'Mejora la resistencia cardiovascular. Fortalece el core y las piernas de forma segura.',
            'duration_minutes': 10,
            'calories_burned': 60,
            'video_url': 'https://www.youtube.com/shorts/ZdFD9WXgQqY',
        },
        {
            'name': 'Kettlebell Around the World',
            'description': 'Pasar la kettlebell alrededor del cuerpo en círculo.',
            'instructions': '''1. Sostén la kettlebell con una mano a la altura de la cadera
2. Pasa la kettlebell detrás de la espalda
3. Tómala con la otra mano
4. Trae la kettlebell al frente
5. Completa el círculo de forma fluida
6. Alterna la dirección después de cada serie''',
            'category': 'cardio',
            'difficulty': 'beginner',
            'benefits': 'Mejora la coordinación y el acondicionamiento. Fortalece el core y los oblicuos.',
            'duration_minutes': 8,
            'calories_burned': 55,
            'video_url': 'https://www.youtube.com/shorts/Go3ep5bsKEs',
        },

        # ==================== EJERCICIOS DE CARDIO - INTERMEDIO ====================
        {
            'name': 'Kettlebell High Pull',
            'description': 'Variación del swing donde se tira de la kettlebell más alto, trabajando más los hombros.',
            'instructions': '''1. Comienza como un swing normal
2. Impulsa con las caderas
3. Tira de la kettlebell hacia arriba hasta la barbilla
4. Mantén los codos altos
5. Baja de forma controlada
6. Repite de forma fluida''',
            'category': 'cardio',
            'difficulty': 'intermediate',
            'benefits': 'Desarrolla potencia y acondicionamiento. Fortalece hombros, trapecios y caderas.',
            'duration_minutes': 15,
            'calories_burned': 140,
            'video_url': 'https://www.youtube.com/watch?v=ak5zrJ4eehU',
        },
        {
            'name': 'Kettlebell Thruster',
            'description': 'Combinación de goblet squat y press, ejercicio de cuerpo completo muy demandante.',
            'instructions': '''1. Sostén la kettlebell en posición de goblet
2. Baja en sentadilla profunda
3. Impulsa hacia arriba explosivamente
4. Usa el impulso para presionar la kettlebell sobre la cabeza
5. Baja la kettlebell al pecho mientras desciendes en squat
6. Repite de forma continua''',
            'category': 'cardio',
            'difficulty': 'intermediate',
            'benefits': 'Quema calorías rápidamente. Desarrolla fuerza y resistencia de cuerpo completo.',
            'duration_minutes': 12,
            'calories_burned': 150,
            'video_url': 'https://www.youtube.com/watch?v=XbguThOPoEM',
        },
        {
            'name': 'Kettlebell Burpee',
            'description': 'Burpee sosteniendo las kettlebells, ejercicio de acondicionamiento extremo.',
            'instructions': '''1. Coloca dos kettlebells en el suelo
2. Agarra las kettlebells y salta los pies hacia atrás
3. Realiza una flexión con las manos en las kettlebells
4. Salta los pies hacia adelante
5. Levanta las kettlebells y salta
6. Repite de forma continua''',
            'category': 'cardio',
            'difficulty': 'intermediate',
            'benefits': 'Acondicionamiento cardiovascular máximo. Quema calorías extremadamente rápido.',
            'duration_minutes': 10,
            'calories_burned': 160,
            'video_url': 'https://www.youtube.com/watch?v=iru4DocrH6U',
        },

        # ==================== EJERCICIOS DE CARDIO - AVANZADO ====================
        {
            'name': 'Kettlebell Long Cycle',
            'description': 'Combinación de clean y jerk repetido, ejercicio de competición.',
            'instructions': '''1. Realiza un clean doble a rack
2. Flexiona ligeramente las rodillas
3. Impulsa las kettlebells hacia arriba
4. Recibe con brazos extendidos
5. Baja a rack de forma controlada
6. Repite sin pausa''',
            'category': 'cardio',
            'difficulty': 'advanced',
            'benefits': 'Acondicionamiento de élite. Desarrolla resistencia muscular y cardiovascular extrema.',
            'duration_minutes': 20,
            'calories_burned': 200,
            'video_url': 'https://youtu.be/1tAXvhkFbOM',
        },
        {
            'name': 'Kettlebell Jerk',
            'description': 'Movimiento explosivo que lleva la kettlebell desde rack hasta overhead usando impulso de piernas.',
            'instructions': '''1. Comienza con kettlebells en posición de rack
2. Flexiona ligeramente las rodillas (dip)
3. Impulsa explosivamente hacia arriba
4. Empuja las kettlebells mientras te hundes debajo
5. Recibe con brazos extendidos y rodillas flexionadas
6. Extiende las piernas para terminar de pie
7. Baja a rack de forma controlada''',
            'category': 'cardio',
            'difficulty': 'advanced',
            'benefits': 'Desarrolla potencia explosiva máxima. Excelente para acondicionamiento de alta intensidad.',
            'duration_minutes': 15,
            'calories_burned': 170,
            'video_url': 'https://youtu.be/NYf6x3ubbSg',
        },

        # ==================== EJERCICIOS DE CUERPO COMPLETO - PRINCIPIANTE ====================
        {
            'name': 'Kettlebell Sumo Deadlift',
            'description': 'Variación del deadlift con postura amplia, enfatiza más los aductores.',
            'instructions': '''1. Coloca la kettlebell entre los pies
2. Separa los pies más allá del ancho de hombros
3. Apunta los dedos de los pies hacia afuera
4. Agarra la kettlebell con ambas manos
5. Mantén la espalda recta y levanta
6. Extiende completamente las caderas arriba
7. Baja de forma controlada''',
            'category': 'full_body',
            'difficulty': 'beginner',
            'benefits': 'Fortalece piernas, glúteos y espalda. Mejora la movilidad de cadera.',
            'duration_minutes': 10,
            'calories_burned': 85,
            'video_url': 'https://www.youtube.com/watch?v=F2F15HRuZtk',
        },
        {
            'name': 'Kettlebell Front Squat',
            'description': 'Sentadilla con dos kettlebells en posición de rack.',
            'instructions': '''1. Limpia dos kettlebells a posición de rack
2. Mantén los codos apuntando hacia adelante
3. Baja en sentadilla manteniendo el torso vertical
4. Desciende hasta que los muslos estén paralelos al suelo
5. Empuja a través de los talones para subir
6. Mantén las kettlebells en rack durante todo el movimiento''',
            'category': 'full_body',
            'difficulty': 'beginner',
            'benefits': 'Desarrolla fuerza en piernas y core. Mejora la postura y la movilidad de tobillo.',
            'duration_minutes': 12,
            'calories_burned': 95,
            'video_url': 'https://www.youtube.com/watch?v=GGLH7x-JtMY',
        },

        # ==================== EJERCICIOS DE CUERPO COMPLETO - INTERMEDIO ====================
        {
            'name': 'Kettlebell Clean and Press',
            'description': 'Combinación de clean y press, ejercicio fundamental de cuerpo completo.',
            'instructions': '''1. Comienza con la kettlebell entre los pies
2. Realiza un clean a posición de rack
3. Sin pausa, presiona la kettlebell sobre la cabeza
4. Baja a rack
5. Baja la kettlebell al suelo
6. Repite de forma fluida''',
            'category': 'full_body',
            'difficulty': 'intermediate',
            'benefits': 'Desarrolla fuerza y potencia de cuerpo completo. Mejora la coordinación.',
            'duration_minutes': 15,
            'calories_burned': 130,
            'video_url': 'https://www.youtube.com/watch?v=rhJ2RBcytbo',
        },
        {
            'name': 'Kettlebell Renegade Row',
            'description': 'Plancha con remo alternado, ejercicio desafiante de core y espalda.',
            'instructions': '''1. Coloca dos kettlebells en el suelo
2. Adopta posición de plancha con manos en las kettlebells
3. Mantén el core activado y el cuerpo recto
4. Rema una kettlebell hacia la cadera
5. Baja de forma controlada
6. Alterna los lados manteniendo la estabilidad''',
            'category': 'full_body',
            'difficulty': 'intermediate',
            'benefits': 'Fortalece core, espalda y estabilizadores. Mejora el equilibrio y la fuerza anti-rotacional.',
            'duration_minutes': 12,
            'calories_burned': 110,
            'video_url': 'https://www.youtube.com/watch?v=DYyPlXk-Itg',
        },
        {
            'name': 'Kettlebell Swing to Squat',
            'description': 'Combinación de swing y goblet squat en un movimiento fluido.',
            'instructions': '''1. Realiza un swing con ambas manos
2. En la parte superior, sostén la kettlebell
3. Baja inmediatamente en goblet squat
4. Sube de la sentadilla
5. Balancea la kettlebell entre las piernas
6. Repite de forma continua''',
            'category': 'full_body',
            'difficulty': 'intermediate',
            'benefits': 'Combina potencia y fuerza. Excelente para acondicionamiento metabólico.',
            'duration_minutes': 15,
            'calories_burned': 145,
            'video_url': 'https://www.youtube.com/watch?v=-U7cScerlpY',
        },

        # ==================== EJERCICIOS DE CUERPO COMPLETO - AVANZADO ====================
        {
            'name': 'Kettlebell Complex: Clean, Squat, Press',
            'description': 'Complejo de tres movimientos realizados sin soltar la kettlebell.',
            'instructions': '''1. Realiza un clean a rack
2. Desde rack, baja en front squat
3. Sube de la sentadilla
4. Presiona la kettlebell sobre la cabeza
5. Baja a rack
6. Baja la kettlebell al suelo
7. Repite la secuencia completa''',
            'category': 'full_body',
            'difficulty': 'advanced',
            'benefits': 'Desarrolla fuerza, resistencia y coordinación de élite. Quema calorías masivamente.',
            'duration_minutes': 18,
            'calories_burned': 180,
            'video_url': 'https://www.youtube.com/shorts/-WwPduyV1To',
        },
        {
            'name': 'Kettlebell Man Maker',
            'description': 'Combinación de burpee, renegade row y clean and press.',
            'instructions': '''1. Coloca dos kettlebells en el suelo
2. Realiza un burpee con manos en las kettlebells
3. En posición de plancha, realiza un remo con cada brazo
4. Salta los pies hacia adelante
5. Limpia las kettlebells a rack
6. Presiona ambas kettlebells sobre la cabeza
7. Baja y repite''',
            'category': 'full_body',
            'difficulty': 'advanced',
            'benefits': 'Acondicionamiento extremo de cuerpo completo. Desarrolla fuerza, potencia y resistencia.',
            'duration_minutes': 15,
            'calories_burned': 200,
            'video_url': 'https://www.youtube.com/watch?v=3EdJZDLTVRc',
        },

        # ==================== EJERCICIOS DE FLEXIBILIDAD ====================
        {
            'name': 'Kettlebell Overhead Squat',
            'description': 'Sentadilla con la kettlebell sobre la cabeza, requiere movilidad excepcional.',
            'instructions': '''1. Presiona la kettlebell sobre la cabeza
2. Mantén el brazo completamente extendido y bloqueado
3. Baja en sentadilla manteniendo la kettlebell arriba
4. Mantén la vista en la kettlebell
5. Desciende lo más bajo posible
6. Sube manteniendo el brazo vertical''',
            'category': 'flexibility',
            'difficulty': 'intermediate',
            'benefits': 'Mejora la movilidad de hombro, cadera y tobillo. Desarrolla estabilidad y fuerza.',
            'duration_minutes': 12,
            'calories_burned': 100,
            'video_url': 'https://www.youtube.com/watch?v=W0xSZ9e3Ju8',
        },
        {
            'name': 'Kettlebell Cossack Squat',
            'description': 'Sentadilla lateral que mejora la movilidad de cadera y aductores.',
            'instructions': '''1. Sostén la kettlebell frente al pecho
2. Da un paso lateral amplio
3. Baja en sentadilla sobre una pierna
4. Mantén la otra pierna extendida
5. Empuja para volver al centro
6. Alterna los lados''',
            'category': 'flexibility',
            'difficulty': 'intermediate',
            'benefits': 'Mejora la movilidad de cadera y flexibilidad de aductores. Fortalece piernas de forma unilateral.',
            'duration_minutes': 10,
            'calories_burned': 80,
            'video_url': 'https://www.youtube.com/shorts/jjWebJi2vdw',
        },
        {
            'name': 'Kettlebell Arm Bar',
            'description': 'Ejercicio de movilidad de hombro y estabilidad del core.',
            'instructions': '''1. Acuéstate de lado con la kettlebell presionada arriba
2. Mantén la vista en la kettlebell
3. Rota el cuerpo hacia abajo manteniendo el brazo vertical
4. Termina boca abajo con el brazo aún extendido
5. Mantén la posición por tiempo
6. Vuelve de forma controlada''',
            'category': 'flexibility',
            'difficulty': 'intermediate',
            'benefits': 'Mejora la movilidad de hombro y columna torácica. Fortalece los estabilizadores del hombro.',
            'duration_minutes': 10,
            'calories_burned': 60,
            'video_url': 'https://www.youtube.com/watch?v=_xXaAS6fVmU',
        },
    ]

    details_by_name = {
        'Kettlebell Deadlift': {
            'equipment': '1 kettlebell',
            'muscles_targeted': 'Principales: glúteos, isquiotibiales, espalda baja.\nSecundarios: core, dorsales, antebrazos.',
            'setup_tips': 'Pies al ancho de caderas con la kettlebell bajo el pecho.\nCadera atrás, espalda neutra y mirada al frente.',
            'common_mistakes': 'Redondear la espalda.\nSubir con brazos en vez de empujar con caderas.\nRodillas colapsan hacia adentro.',
            'variations': 'Deadlift sumo.\nDeadlift a una pierna asistido.',
            'progressions': 'Progresión: aumenta el peso o agrega pausa de 1s arriba.\nRegresión: eleva la kettlebell sobre un bloque.',
            'precautions': 'Evita si hay dolor lumbar agudo.\nMantén columna neutra en todo el rango.',
        },
        'Kettlebell Goblet Squat': {
            'equipment': '1 kettlebell',
            'muscles_targeted': 'Principales: cuádriceps, glúteos.\nSecundarios: core, aductores.',
            'setup_tips': 'Agarra por las "orejas", codos apuntan al suelo.\nPies al ancho de hombros, puntas levemente hacia afuera.',
            'common_mistakes': 'Talones se levantan.\nRodillas colapsan hacia adentro.\nTorso se inclina excesivamente.',
            'variations': 'Box squat.\nGoblet squat con pausa.',
            'progressions': 'Progresión: mayor peso o tempo 3-1-1.\nRegresión: rango parcial.',
            'precautions': 'Evita dolor de rodilla.\nMantén columna neutra y core activo.',
        },
        'Kettlebell Row': {
            'equipment': '1 kettlebell, banco o apoyo estable',
            'muscles_targeted': 'Principales: dorsales, romboides.\nSecundarios: bíceps, core.',
            'setup_tips': 'Columna paralela al suelo, cadera nivelada.\nHombros lejos de las orejas.',
            'common_mistakes': 'Girar el torso al remar.\nEncoger hombros.\nBajar sin control.',
            'variations': 'Remo renegado.\nRemo con apoyo en banco.',
            'progressions': 'Progresión: pausa de 1s arriba o más peso.\nRegresión: menor carga.',
            'precautions': 'Evita si hay dolor de hombro.\nMantén muñeca neutra.',
        },
        'Kettlebell Halo': {
            'equipment': '1 kettlebell ligera',
            'muscles_targeted': 'Principales: deltoides, manguito rotador.\nSecundarios: core, trapecio.',
            'setup_tips': 'Agarre firme, codos cerca del cuerpo.\nMovimiento lento y controlado.',
            'common_mistakes': 'Extender el cuello.\nArcos muy amplios sin control.',
            'variations': 'Halo medio arrodillado.\nHalo con kettlebell invertida.',
            'progressions': 'Progresión: más peso o más repeticiones.\nRegresión: arco más corto.',
            'precautions': 'Evita dolor en hombro.\nNo forzar el rango.',
        },
        'Kettlebell Farmer Walk': {
            'equipment': '2 kettlebells',
            'muscles_targeted': 'Principales: antebrazos, core, trapecio.\nSecundarios: glúteos, piernas.',
            'setup_tips': 'Hombros abajo y atrás.\nPasos cortos y controlados.',
            'common_mistakes': 'Encoger hombros.\nBalanceo excesivo del tronco.',
            'variations': 'Suitcase carry (una mano).\nFarmer walk con pausa.',
            'progressions': 'Progresión: más distancia o más peso.\nRegresión: una kettlebell ligera.',
            'precautions': 'Evita si hay dolor lumbar.\nMantén columna neutra.',
        },
        'Kettlebell Swing': {
            'equipment': '1 kettlebell',
            'muscles_targeted': 'Principales: glúteos, isquiotibiales.\nSecundarios: core, dorsales, antebrazos.',
            'setup_tips': 'Bisagra de cadera, tibias casi verticales.\nLos brazos actúan como ganchos.',
            'common_mistakes': 'Levantar con hombros.\nHacer una sentadilla en lugar de bisagra.\nHiperextender la espalda al final.',
            'variations': 'Swing ruso.\nSwing a una mano.',
            'progressions': 'Progresión: una mano o mayor peso.\nRegresión: deadlift + swing corto.',
            'precautions': 'Evita dolor lumbar.\nControla el arco lumbar.',
        },
        'Kettlebell Clean': {
            'equipment': '1 kettlebell',
            'muscles_targeted': 'Principales: glúteos, espalda.\nSecundarios: antebrazos, core, hombros.',
            'setup_tips': 'Cadera atrás, agarre firme.\nCodo pegado al costado al subir.',
            'common_mistakes': 'Golpear la muñeca.\nTirar con el brazo en vez de caderas.',
            'variations': 'Clean colgado.\nClean doble.',
            'progressions': 'Progresión: clean y press.\nRegresión: high pull.',
            'precautions': 'Evita dolor en muñeca.\nMantén muñeca neutra.',
        },
        'Kettlebell Press': {
            'equipment': '1 kettlebell',
            'muscles_targeted': 'Principales: deltoides, tríceps.\nSecundarios: core, dorsal.',
            'setup_tips': 'Rack sólido, muñeca alineada.\nGlúteos activos para estabilizar.',
            'common_mistakes': 'Arquear la zona lumbar.\nCodo muy abierto.',
            'variations': 'Push press.\nPress medio arrodillado.',
            'progressions': 'Progresión: bottoms-up press.\nRegresión: menos peso.',
            'precautions': 'Evita dolor en hombro.\nNo bloquees con dolor.',
        },
        'Kettlebell Turkish Get-Up': {
            'equipment': '1 kettlebell',
            'muscles_targeted': 'Principales: core, hombro estabilizador.\nSecundarios: glúteos, espalda.',
            'setup_tips': 'Brazo vertical todo el tiempo.\nMira la kettlebell hasta estar de pie.',
            'common_mistakes': 'Doblar el brazo.\nPerder la alineación muñeca-hombro.',
            'variations': 'Get-up parcial por fases.\nSin peso.',
            'progressions': 'Progresión: mayor peso.\nRegresión: practicar cada fase.',
            'precautions': 'Evita dolor de hombro.\nControl total del rango.',
        },
        'Kettlebell Windmill': {
            'equipment': '1 kettlebell',
            'muscles_targeted': 'Principales: oblicuos, hombro.\nSecundarios: isquiotibiales, glúteos.',
            'setup_tips': 'Pies a 45°, mirada arriba.\nCadera se desplaza hacia atrás.',
            'common_mistakes': 'Perder la vertical del brazo.\nRedondear la espalda.',
            'variations': 'Windmill con kettlebell ligera.\nWindmill sin peso.',
            'progressions': 'Progresión: más peso.\nRegresión: rango parcial.',
            'precautions': 'Evita mareos.\nNo forzar movilidad.',
        },
        'Kettlebell Snatch': {
            'equipment': '1 kettlebell',
            'muscles_targeted': 'Principales: glúteos, espalda, hombros.\nSecundarios: core, antebrazos.',
            'setup_tips': 'Trayectoria cerca del cuerpo.\nPerfora el brazo al final.',
            'common_mistakes': 'Golpear el antebrazo.\nTirar con el brazo.',
            'variations': 'Snatch con pausa arriba.\nSnatch desde colgado.',
            'progressions': 'Progresión: mayor peso o volumen.\nRegresión: clean.',
            'precautions': 'Evita dolor en hombro.\nMantén muñeca neutra.',
        },
        'Kettlebell Double Clean and Press': {
            'equipment': '2 kettlebells',
            'muscles_targeted': 'Principales: glúteos, espalda, hombros.\nSecundarios: core, tríceps.',
            'setup_tips': 'Caderas simétricas.\nRack sólido antes de presionar.',
            'common_mistakes': 'Desfase entre brazos.\nPerder el rack.',
            'variations': 'Clean doble + push press.\nClean doble con pausa.',
            'progressions': 'Progresión: más peso o series.\nRegresión: una kettlebell.',
            'precautions': 'Evita dolor lumbar.\nControla las muñecas.',
        },
        'Kettlebell Double Snatch': {
            'equipment': '2 kettlebells',
            'muscles_targeted': 'Principales: glúteos, espalda, hombros.\nSecundarios: core, antebrazos.',
            'setup_tips': 'Bisagra potente.\nBrazos paralelos, cerca del cuerpo.',
            'common_mistakes': 'Golpear antebrazos.\nPerder sincronía.',
            'variations': 'Snatch doble desde colgado.\nSnatch alterno.',
            'progressions': 'Progresión: mayor peso.\nRegresión: clean doble.',
            'precautions': 'Evita dolor de hombro.\nBuena movilidad.',
        },
        'Kettlebell Pistol Squat': {
            'equipment': '1 kettlebell',
            'muscles_targeted': 'Principales: cuádriceps, glúteos.\nSecundarios: core, estabilizadores de tobillo.',
            'setup_tips': 'Mirada al frente.\nPeso en talón y medio pie.',
            'common_mistakes': 'Rodilla colapsa.\nTalón se levanta.',
            'variations': 'Pistol a caja.\nPistol asistida.',
            'progressions': 'Progresión: mayor profundidad.\nRegresión: TRX o apoyo.',
            'precautions': 'Evita dolor de rodilla.\nNo forzar tobillo.',
        },
        'Kettlebell Bent Press': {
            'equipment': '1 kettlebell',
            'muscles_targeted': 'Principales: hombro, oblicuos.\nSecundarios: cadera, espalda.',
            'setup_tips': 'Codo en rack, mirada a la kettlebell.\nFlexión lateral controlada.',
            'common_mistakes': 'Perder la línea del brazo.\nRotar demasiado el torso.',
            'variations': 'Bent press ligero.\nWindmill + press.',
            'progressions': 'Progresión: más peso.\nRegresión: windmill.',
            'precautions': 'Evita dolor de hombro.\nMovilidad primero.',
        },
        'Kettlebell Bottoms-Up Press': {
            'equipment': '1 kettlebell',
            'muscles_targeted': 'Principales: hombro estabilizador, antebrazo.\nSecundarios: core, tríceps.',
            'setup_tips': 'Agarre fuerte, muñeca neutra.\nSube lento.',
            'common_mistakes': 'Muñeca doblada.\nPerder el balance.',
            'variations': 'Bottoms-up hold.\nPress medio arrodillado.',
            'progressions': 'Progresión: más peso.\nRegresión: press normal.',
            'precautions': 'Evita dolor de muñeca.\nNo usar peso excesivo.',
        },
        'Kettlebell March in Place': {
            'equipment': '1 kettlebell',
            'muscles_targeted': 'Principales: core, flexores de cadera.\nSecundarios: glúteos, pantorrillas.',
            'setup_tips': 'Kettlebell en rack o goblet.\nRodillas altas.',
            'common_mistakes': 'Inclinar el torso.\nPerder ritmo.',
            'variations': 'Marcha en rack unilateral.\nMarcha con pausa.',
            'progressions': 'Progresión: más tiempo o peso.\nRegresión: sin peso.',
            'precautions': 'Evita dolor de cadera.\nMantén postura.',
        },
        'Kettlebell Around the World': {
            'equipment': '1 kettlebell',
            'muscles_targeted': 'Principales: oblicuos, core.\nSecundarios: hombros, antebrazos.',
            'setup_tips': 'Cadera estable.\nCambio de mano suave.',
            'common_mistakes': 'Mover el tronco.\nSoltar el agarre.',
            'variations': 'Around the world en zancada.\nReverse halo.',
            'progressions': 'Progresión: más rápido.\nRegresión: movimiento más lento.',
            'precautions': 'Evita dolor de espalda.\nNo arquear.',
        },
        'Kettlebell High Pull': {
            'equipment': '1 kettlebell',
            'muscles_targeted': 'Principales: glúteos, trapecio.\nSecundarios: hombros, core.',
            'setup_tips': 'Codo alto, muñeca neutra.\nImpulso de cadera.',
            'common_mistakes': 'Tirar con brazos.\nEncoger hombros en exceso.',
            'variations': 'High pull a una mano.\nHigh pull desde colgado.',
            'progressions': 'Progresión: más peso.\nRegresión: swing ruso.',
            'precautions': 'Evita dolor de hombro.\nControla la fase baja.',
        },
        'Kettlebell Thruster': {
            'equipment': '1 kettlebell',
            'muscles_targeted': 'Principales: piernas, hombros.\nSecundarios: core, tríceps.',
            'setup_tips': 'Talones firmes.\nUsa el impulso de piernas.',
            'common_mistakes': 'Presionar antes de extender.\nRodillas colapsan.',
            'variations': 'Thruster con dos kettlebells.\nThruster a una mano.',
            'progressions': 'Progresión: más peso.\nRegresión: goblet squat + press separado.',
            'precautions': 'Evita dolor de rodilla.\nControl lumbar.',
        },
        'Kettlebell Burpee': {
            'equipment': '2 kettlebells',
            'muscles_targeted': 'Principales: pecho, piernas, core.\nSecundarios: hombros, tríceps.',
            'setup_tips': 'Alinea muñecas sobre asas.\nSalta suave.',
            'common_mistakes': 'Dejar caer la cadera.\nPerder control en la flexión.',
            'variations': 'Burpee sin flexión.\nBurpee con swing.',
            'progressions': 'Progresión: más repeticiones.\nRegresión: step-back en vez de salto.',
            'precautions': 'Evita dolor de muñeca.\nMantén core activo.',
        },
        'Kettlebell Long Cycle': {
            'equipment': '2 kettlebells',
            'muscles_targeted': 'Principales: glúteos, espalda, hombros.\nSecundarios: core, piernas.',
            'setup_tips': 'Respira en rack.\nDip corto y explosivo.',
            'common_mistakes': 'Rack débil.\nPerder el timing del jerk.',
            'variations': 'Long cycle a una mano.\nClean + push press.',
            'progressions': 'Progresión: más tiempo continuo.\nRegresión: clean + press.',
            'precautions': 'Evita dolor de hombro.\nMantén muñeca neutra.',
        },
        'Kettlebell Jerk': {
            'equipment': '2 kettlebells',
            'muscles_targeted': 'Principales: piernas, hombros.\nSecundarios: core, tríceps.',
            'setup_tips': 'Dip vertical.\nRecibe con rodillas flexionadas.',
            'common_mistakes': 'Empujar con brazos.\nInclinar el torso.',
            'variations': 'Push jerk con una kettlebell.\nJerk desde rack.',
            'progressions': 'Progresión: más peso.\nRegresión: push press.',
            'precautions': 'Evita dolor de rodilla.\nControl lumbar.',
        },
        'Kettlebell Sumo Deadlift': {
            'equipment': '1 kettlebell',
            'muscles_targeted': 'Principales: glúteos, aductores.\nSecundarios: espalda baja, core.',
            'setup_tips': 'Pies abiertos, puntas afuera.\nRodillas siguen la línea de los pies.',
            'common_mistakes': 'Cadera muy baja.\nRodillas colapsan.',
            'variations': 'Sumo deadlift high pull.\nSumo con pausa.',
            'progressions': 'Progresión: más peso.\nRegresión: rango parcial.',
            'precautions': 'Evita dolor de aductores.\nColumna neutra.',
        },
        'Kettlebell Front Squat': {
            'equipment': '2 kettlebells',
            'muscles_targeted': 'Principales: cuádriceps, glúteos.\nSecundarios: core, espalda alta.',
            'setup_tips': 'Codos altos.\nRack estable.',
            'common_mistakes': 'Codos caen.\nTalones se levantan.',
            'variations': 'Front squat a una mano.\nFront squat con pausa.',
            'progressions': 'Progresión: más peso.\nRegresión: goblet squat.',
            'precautions': 'Evita dolor de rodilla.\nMantén torso vertical.',
        },
        'Kettlebell Clean and Press': {
            'equipment': '1 kettlebell',
            'muscles_targeted': 'Principales: glúteos, espalda, hombros.\nSecundarios: core, tríceps.',
            'setup_tips': 'Clean suave sin golpe.\nPress en línea recta.',
            'common_mistakes': 'Rack inestable.\nArco lumbar.',
            'variations': 'Clean + push press.\nClean + press alterno.',
            'progressions': 'Progresión: más peso.\nRegresión: movimientos separados.',
            'precautions': 'Evita dolor de hombro.\nControl de muñeca.',
        },
        'Kettlebell Renegade Row': {
            'equipment': '2 kettlebells',
            'muscles_targeted': 'Principales: core, dorsales.\nSecundarios: hombros, tríceps.',
            'setup_tips': 'Pies separados para estabilidad.\nCadera cuadrada.',
            'common_mistakes': 'Balancear la cadera.\nDejar caer el hombro.',
            'variations': 'Renegade row con rodillas apoyadas.\nRow sin kettlebell.',
            'progressions': 'Progresión: pies juntos.\nRegresión: apoyo en banco.',
            'precautions': 'Evita dolor de muñeca.\nMantén core firme.',
        },
        'Kettlebell Swing to Squat': {
            'equipment': '1 kettlebell',
            'muscles_targeted': 'Principales: glúteos, cuádriceps.\nSecundarios: core, espalda.',
            'setup_tips': 'Transición suave.\nAgarre seguro.',
            'common_mistakes': 'Perder control en el cambio.\nRodillas colapsan.',
            'variations': 'Swing + goblet squat con pausa.\nSwing a una mano.',
            'progressions': 'Progresión: más peso.\nRegresión: swing corto.',
            'precautions': 'Evita dolor lumbar.\nMantén técnica.',
        },
        'Kettlebell Complex: Clean, Squat, Press': {
            'equipment': '1 kettlebell',
            'muscles_targeted': 'Principales: piernas, hombros, core.\nSecundarios: espalda, glúteos.',
            'setup_tips': 'No sueltes la kettlebell.\nRespira entre fases.',
            'common_mistakes': 'Perder el rack.\nFatiga técnica.',
            'variations': 'Complejo con dos kettlebells.\nComplejo sin press.',
            'progressions': 'Progresión: más rondas.\nRegresión: separar movimientos.',
            'precautions': 'Evita fatiga excesiva.\nPrioriza técnica.',
        },
        'Kettlebell Man Maker': {
            'equipment': '2 kettlebells',
            'muscles_targeted': 'Principales: core, espalda, hombros.\nSecundarios: piernas, tríceps.',
            'setup_tips': 'Base estable en plancha.\nRemo controlado.',
            'common_mistakes': 'Cadera se balancea.\nPerder alineación en la flexión.',
            'variations': 'Man maker sin salto.\nMan maker con menos repeticiones.',
            'progressions': 'Progresión: más peso.\nRegresión: burpee sin remo.',
            'precautions': 'Evita dolor lumbar.\nMantén core activo.',
        },
        'Kettlebell Overhead Squat': {
            'equipment': '1 kettlebell',
            'muscles_targeted': 'Principales: hombros, core, cuádriceps.\nSecundarios: glúteos, espalda alta.',
            'setup_tips': 'Brazo bloqueado.\nPies estables.',
            'common_mistakes': 'Brazo se inclina.\nTalones se levantan.',
            'variations': 'Overhead squat con pausa.\nOverhead squat parcial.',
            'progressions': 'Progresión: más rango.\nRegresión: goblet squat.',
            'precautions': 'Evita dolor de hombro.\nMovilidad adecuada.',
        },
        'Kettlebell Cossack Squat': {
            'equipment': '1 kettlebell',
            'muscles_targeted': 'Principales: aductores, glúteos.\nSecundarios: cuádriceps, core.',
            'setup_tips': 'Pie de la pierna extendida con punta arriba.\nEspalda recta.',
            'common_mistakes': 'Rodilla colapsa.\nPerder equilibrio.',
            'variations': 'Cossack con soporte.\nCossack sin peso.',
            'progressions': 'Progresión: más profundidad.\nRegresión: rango corto.',
            'precautions': 'Evita dolor en aductores.\nNo forzar cadera.',
        },
        'Kettlebell Arm Bar': {
            'equipment': '1 kettlebell',
            'muscles_targeted': 'Principales: hombro estabilizador, core.\nSecundarios: espalda alta.',
            'setup_tips': 'Brazo vertical y firme.\nMovimiento lento.',
            'common_mistakes': 'Doblar el brazo.\nGirar rápido.',
            'variations': 'Arm bar sin peso.\nArm bar con pausa.',
            'progressions': 'Progresión: más peso.\nRegresión: sin kettlebell.',
            'precautions': 'Evita dolor de hombro.\nNo forzar rango.',
        },
    }
    
    created_count = 0
    for exercise_data in exercises_data:
        name = exercise_data.get('name')
        defaults = {k: v for k, v in exercise_data.items() if k != 'name'}
        details = details_by_name.get(name, {})
        defaults.update(details)

        image_path = catalog_image_for(name)
        if image_path:
            defaults['image'] = image_path

        exercise, created = Exercise.objects.update_or_create(
            name=name,
            defaults=defaults
        )

        # Ensure slug exists for new records
        if created and (not getattr(exercise, 'slug', None)):
            exercise.slug = slugify(exercise.name)
            exercise.save()

        if created:
            created_count += 1
            print(f"[OK] Creado: {exercise.name} ({exercise.get_category_display()} - {exercise.get_difficulty_display()})")
        else:
            print(f"[UPD] Actualizado: {exercise.name}")
    
    return created_count

def main():
    print("=" * 70)
    print("SCRIPT DE POBLACIÓN DE EJERCICIOS DE KETTLEBELL")
    print("=" * 70)
    print()
    
    # Preguntar si se desea limpiar la base de datos (solo en terminal interactiva;
    # en pipelines/Docker se omite y se hace upsert sobre lo existente).
    if sys.stdin is not None and sys.stdin.isatty():
        try:
            response = input("¿Deseas eliminar todos los ejercicios existentes antes de poblar? (s/n): ")
        except EOFError:
            response = 'n'
        if response.lower() in ['s', 'si', 'sí', 'yes', 'y']:
            clear_exercises()
            print()
    
    print("Poblando base de datos con ejercicios de kettlebell...")
    print()
    
    created_count = populate_exercises()
    
    print()
    print("=" * 70)
    print(f"[OK] COMPLETADO: {created_count} ejercicios nuevos creados/actualizados")
    print(f"[OK] Total de ejercicios en la base de datos: {Exercise.objects.count()}")
    print("=" * 70)
    print()
    print("Resumen por categoría:")
    for category_code, category_name in Exercise.CATEGORY_CHOICES:
        count = Exercise.objects.filter(category=category_code).count()
        print(f"  - {category_name}: {count} ejercicios")
    
    print()
    print("Resumen por dificultad:")
    for difficulty_code, difficulty_name in Exercise.DIFFICULTY_CHOICES:
        count = Exercise.objects.filter(difficulty=difficulty_code).count()
        print(f"  - {difficulty_name}: {count} ejercicios")
    
    print()

if __name__ == '__main__':
    main()
