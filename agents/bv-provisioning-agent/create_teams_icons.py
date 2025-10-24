#!/usr/bin/env python3
"""
Create Teams App Icons from BroadVoice Logo

Generates the required icon files for Teams app package:
- color.png (192x192) - Color logo on white background
- outline.png (32x32) - Simple white outline on transparent background

Usage:
    python create_teams_icons.py <path_to_logo_image>

Example:
    python create_teams_icons.py /path/to/broadvoice_logo.png
"""

import sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageOps

def create_color_icon(logo_path: Path, output_path: Path, size: int = 192):
    """
    Create color icon (192x192) with logo centered on white background

    Args:
        logo_path: Path to source logo image
        output_path: Path to save color.png
        size: Output size (default 192)
    """
    print(f"Creating color icon ({size}x{size})...")

    # Load the logo
    logo = Image.open(logo_path)

    # Convert to RGBA if needed
    if logo.mode != 'RGBA':
        logo = logo.convert('RGBA')

    # Create white background
    background = Image.new('RGBA', (size, size), (255, 255, 255, 255))

    # Calculate size to fit logo (with padding)
    padding = size // 10  # 10% padding
    max_logo_size = size - (padding * 2)

    # Resize logo to fit while maintaining aspect ratio
    logo.thumbnail((max_logo_size, max_logo_size), Image.Resampling.LANCZOS)

    # Calculate position to center logo
    x = (size - logo.width) // 2
    y = (size - logo.height) // 2

    # Paste logo onto background
    background.paste(logo, (x, y), logo)

    # Convert to RGB for PNG (Teams requires RGB, not RGBA for color icon)
    final = background.convert('RGB')

    # Save
    final.save(output_path, 'PNG')
    print(f"✓ Saved color icon to: {output_path}")


def create_outline_icon(logo_path: Path, output_path: Path, size: int = 32):
    """
    Create outline icon (32x32) - simple white outline on transparent background

    For simplicity, we'll create a white "BV" monogram or use a simplified logo

    Args:
        logo_path: Path to source logo image (for reference)
        output_path: Path to save outline.png
        size: Output size (default 32)
    """
    print(f"Creating outline icon ({size}x{size})...")

    # Create transparent background
    image = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    # Option 1: Create a simple "BV" monogram
    # Draw a circle with "BV" text

    # Draw circle outline
    margin = 2
    circle_bbox = [margin, margin, size - margin - 1, size - margin - 1]
    draw.ellipse(circle_bbox, outline=(255, 255, 255, 255), width=2)

    # Add "BV" text in center
    try:
        # Try to use a nice font if available
        font_size = size // 3
        # Try common system fonts
        font_paths = [
            "/System/Library/Fonts/Helvetica.ttc",
            "/System/Library/Fonts/SFNS.ttf",
            "C:\\Windows\\Fonts\\arial.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
        ]

        font = None
        for font_path in font_paths:
            if Path(font_path).exists():
                font = ImageFont.truetype(font_path, font_size)
                break

        if font is None:
            # Fallback to default font
            font = ImageFont.load_default()
    except:
        font = ImageFont.load_default()

    # Draw "BV" text centered
    text = "BV"

    # For newer Pillow versions
    try:
        bbox = draw.textbbox((0, 0), text, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
    except:
        # Fallback for older Pillow versions
        text_width, text_height = draw.textsize(text, font=font)

    text_x = (size - text_width) // 2
    text_y = (size - text_height) // 2 - 1  # Slight adjustment for visual centering

    draw.text((text_x, text_y), text, fill=(255, 255, 255, 255), font=font)

    # Save
    image.save(output_path, 'PNG')
    print(f"✓ Saved outline icon to: {output_path}")


def create_outline_from_logo(logo_path: Path, output_path: Path, size: int = 32):
    """
    Alternative: Create outline icon from logo (white silhouette)

    Args:
        logo_path: Path to source logo image
        output_path: Path to save outline.png
        size: Output size (default 32)
    """
    print(f"Creating outline icon from logo ({size}x{size})...")

    # Load and resize logo
    logo = Image.open(logo_path)

    # Convert to RGBA
    if logo.mode != 'RGBA':
        logo = logo.convert('RGBA')

    # Resize to fit
    padding = 4
    max_size = size - (padding * 2)
    logo.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)

    # Create transparent background
    background = Image.new('RGBA', (size, size), (0, 0, 0, 0))

    # Convert logo to white silhouette
    # Get alpha channel
    alpha = logo.split()[3]

    # Create white version
    white_logo = Image.new('RGBA', logo.size, (255, 255, 255, 255))
    white_logo.putalpha(alpha)

    # Calculate position to center
    x = (size - logo.width) // 2
    y = (size - logo.height) // 2

    # Paste white logo
    background.paste(white_logo, (x, y), white_logo)

    # Save
    background.save(output_path, 'PNG')
    print(f"✓ Saved outline icon (from logo) to: {output_path}")


def main():
    """Main function"""
    if len(sys.argv) < 2:
        print("Usage: python create_teams_icons.py <path_to_logo_image>")
        print("\nExample:")
        print("  python create_teams_icons.py broadvoice_logo.png")
        sys.exit(1)

    logo_path = Path(sys.argv[1])

    if not logo_path.exists():
        print(f"Error: Logo file not found: {logo_path}")
        sys.exit(1)

    # Output directory
    output_dir = Path(__file__).parent / "teams_app"
    output_dir.mkdir(exist_ok=True)

    print("=" * 70)
    print("Creating Teams App Icons")
    print("=" * 70)
    print(f"Source logo: {logo_path}")
    print(f"Output directory: {output_dir}\n")

    # Create color icon
    color_output = output_dir / "color.png"
    create_color_icon(logo_path, color_output, size=192)

    # Create outline icon
    outline_output = output_dir / "outline.png"

    # Prompt user for outline style
    print("\nOutline icon options:")
    print("  1. Simple 'BV' monogram (recommended for clarity)")
    print("  2. White silhouette of logo")

    choice = input("\nChoose option (1 or 2, default=1): ").strip()

    if choice == "2":
        create_outline_from_logo(logo_path, outline_output, size=32)
    else:
        create_outline_icon(logo_path, outline_output, size=32)

    print("\n" + "=" * 70)
    print("✅ Icons created successfully!")
    print("=" * 70)
    print(f"\nFiles created:")
    print(f"  - {color_output}")
    print(f"  - {outline_output}")
    print(f"\nNext steps:")
    print(f"  1. Review the generated icons")
    print(f"  2. Update teams_app/manifest.json with your App ID")
    print(f"  3. Create the app package: cd teams_app && zip BVProvisioningAgent.zip manifest.json color.png outline.png")
    print(f"  4. Upload to Microsoft Teams")


if __name__ == "__main__":
    # Check if PIL is installed
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        print("Error: Pillow library not installed")
        print("\nInstall with: pip install Pillow")
        sys.exit(1)

    main()
