import sys
import os
from PIL import Image, ImageDraw, ImageFont

def main():
    if not len(sys.argv) == 3:
        print("Usage: output_visualizer.py <submission_output> <feedback_dir>")
        sys.exit(15)
    
    with open (sys.argv[1], 'r') as f:
        submission_output = f.read()
    feedback_dir = sys.argv[2]

    # Create an image with a white background
    width, height = 400, 200
    image = Image.new('RGB', (width, height), color=(255, 255, 255))
    draw = ImageDraw.Draw(image)
    
    # Use default font
    font = ImageFont.load_default()
    
    # Construct text to display (limit length for simplicity)
    text = f"Output:\n{submission_output[:100]}"
    
    # Draw the text onto the image
    draw.multiline_text((10, 10), text, fill=(0, 0, 0), font=font)
    
    # Save the image to feedback directory
    outfile = os.path.join(feedback_dir, "visualizer_output.png")
    image.save(outfile)
    print(f"Image saved to {outfile}")
    sys.exit(0)

if __name__ == '__main__':
    main()