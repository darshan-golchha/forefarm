import random
import string

def generate_random_id():
    # Generate 2 characters 'gj' at the beginning
    prefix = 'gj-'
    
    # Generate 6 random lowercase letters
    letters_part = ''.join(random.choices(string.ascii_lowercase, k=6))
    
    # Generate 5 random digits
    digits_part = ''.join(random.choices(string.digits, k=5))
    
    # Generate 6 random lowercase letters again
    suffix_part = ''.join(random.choices(string.ascii_lowercase, k=6))
    
    # Combine all parts to create the ID
    random_id = f"{prefix}{letters_part}{digits_part}{suffix_part}"
    return random_id