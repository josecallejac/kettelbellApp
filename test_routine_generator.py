import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'kettelbell.settings')
django.setup()

from django.contrib.auth.models import User
from exercises.models import Exercise, Workout
from exercises.utils import RoutineGenerator

def test_generation():
    print("Testing Routine Generator...")
    
    # Get or create a dummy user
    user, _ = User.objects.get_or_create(username='test_user')
    
    # Test cases
    configs = [
        {'duration': 15, 'difficulty': 'beginner', 'focus': 'cardio'},
        {'duration': 45, 'difficulty': 'advanced', 'focus': 'strength'},
        {'duration': 30, 'difficulty': 'intermediate', 'focus': 'mix'},
    ]
    
    for config in configs:
        print(f"\nGenerating: {config}")
        try:
            generator = RoutineGenerator(
                user=user,
                duration_minutes=config['duration'],
                difficulty=config['difficulty'],
                focus=config['focus']
            )
            workout = generator.generate()
            
            print(f"✓ Workout Created: {workout.title}")
            print(f"  - Duration: {workout.estimated_duration} mins")
            print(f"  - Exercises: {workout.exercises.count()}")
            
            for we in workout.exercises.all():
                print(f"    {we.order}. {we.exercise.name} ({we.sets} sets x {we.reps})")
                
            # Cleanup
            print("  - Workout Saved successfully")
            
        except Exception as e:
            print(f"❌ Error: {e}")

if __name__ == '__main__':
    test_generation()
