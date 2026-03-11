from __future__ import annotations

import os
import random
from PIL import Image, ImageDraw, ImageFont
import hashlib

def create_placeholder_image(text: str = None, size: tuple[int, int] = (200, 200), bg_color: tuple[int, int, int] = None, text_color: tuple[int, int, int] = (255, 255, 255)) -> Image.Image:
    """
    Create a placeholder image with optional text
    
    Args:
        text: Text to display on the image (defaults to first letter of filename)
        size: Tuple of (width, height)
        bg_color: Background color (random if None)
        text_color: Text color
        
    Returns:
        PIL.Image object
    """
    # Generate a random background color if none provided
    if bg_color is None:
        # Generate pastel colors
        r = random.randint(100, 200)
        g = random.randint(100, 200)
        b = random.randint(100, 200)
        bg_color = (r, g, b)
    
    # Create image with background color
    image = Image.new('RGB', size, bg_color)
    draw = ImageDraw.Draw(image)
    
    # If text is provided, draw it centered on the image
    if text:
        # Use first letter if text is longer
        display_text = text[0].upper() if len(text) > 0 else "?"
        
        # Try to load font or use default
        try:
            font_size = min(size) // 2
            font = ImageFont.truetype("arial.ttf", font_size)
        except IOError:
            # Use default font if arial.ttf is not available
            font = ImageFont.load_default()
        
        # Get text size and position it centrally - handles Pillow API change
        try:
            # For newer Pillow versions
            bbox = draw.textbbox((0, 0), display_text, font=font)
            text_width = bbox[2] - bbox[0]
            text_height = bbox[3] - bbox[1]
        except AttributeError:
            # For older Pillow versions
            text_width, text_height = draw.textsize(display_text, font=font)
        
        position = ((size[0] - text_width) // 2, (size[1] - text_height) // 2)
        
        # Draw text
        draw.text(position, display_text, fill=text_color, font=font)
    
    return image

def ensure_image_exists(filepath: str, filename: str = None, size: tuple[int, int] = (200, 200), create_dir: bool = True) -> str:
    """
    Check if an image exists, and create a placeholder if it doesn't
    
    Args:
        filepath: Path to the image file
        filename: Name of the file (used for placeholder text)
        size: Tuple of (width, height) for the placeholder
        create_dir: Whether to create directory structure if it doesn't exist
        
    Returns:
        str: Path to the image (original or newly created)
    """
    # Check if file exists
    if os.path.exists(filepath):
        return filepath
    
    # Create directory if it doesn't exist
    if create_dir:
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
    
    # Generate placeholder text from filename
    if filename is None:
        filename = os.path.basename(filepath)
    
    # Generate a deterministic color based on the filename
    name_hash = hashlib.md5(filename.encode()).hexdigest()
    r = int(name_hash[0:2], 16) % 100 + 100  # 100-199
    g = int(name_hash[2:4], 16) % 100 + 100  # 100-199
    b = int(name_hash[4:6], 16) % 100 + 100  # 100-199
    bg_color = (r, g, b)
    
    # Create placeholder image
    img = create_placeholder_image(filename, size, bg_color)
    
    # Save image
    img.save(filepath)
    
    return filepath

def generate_default_avatar(name: str, filepath: str, size: tuple[int, int] = (200, 200)) -> str:
    """
    Generate a default avatar image for a user when no image is available
    
    Args:
        name: Name of the user
        filepath: Path to save the avatar
        size: Size of the avatar image
        
    Returns:
        str: Path to the avatar image
    """
    return ensure_image_exists(filepath, name, size) 
