"""
Fix mojibake (Ã¡, Ã©, etc.) in Exercise text fields.

Run:
  python fix_exercise_text_encoding.py
"""

import os

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "kettelbell.settings")
django.setup()

from exercises.models import Exercise

FIELDS = [
    "name",
    "description",
    "instructions",
    "benefits",
    "muscles_targeted",
    "common_mistakes",
    "equipment",
    "variations",
    "setup_tips",
    "progressions",
    "precautions",
]

WEIRD_MARKERS = ("Ã", "Â", "â", "�")


def score_mojibake(text: str) -> int:
    return sum(text.count(mark) for mark in WEIRD_MARKERS)


def fix_mojibake(value):
    if value is None or not isinstance(value, str):
        return value, False
    if not any(mark in value for mark in WEIRD_MARKERS):
        return value, False

    try:
        candidate = value.encode("latin1").decode("utf-8")
    except UnicodeError:
        return value, False

    if candidate == value:
        return value, False

    if score_mojibake(candidate) <= score_mojibake(value):
        return candidate, True

    return value, False


def main():
    total_exercises = Exercise.objects.count()
    changed_exercises = 0
    changed_fields = 0

    for exercise in Exercise.objects.all():
        updates = {}
        for field in FIELDS:
            value = getattr(exercise, field)
            fixed, changed = fix_mojibake(value)
            if changed:
                updates[field] = fixed

        if updates:
            for field, value in updates.items():
                setattr(exercise, field, value)
            exercise.save(update_fields=list(updates.keys()))
            changed_exercises += 1
            changed_fields += len(updates)

    print("Total ejercicios:", total_exercises)
    print("Ejercicios actualizados:", changed_exercises)
    print("Campos corregidos:", changed_fields)


if __name__ == "__main__":
    main()
