"""
Test script for Gemini Vision API
"""
import asyncio
import json
import os
from io import BytesIO
from pathlib import Path

import google.generativeai as genai
from PIL import Image
from dotenv import load_dotenv
from pillow_heif import register_heif_opener

# Register HEIF opener to support HEIC files
register_heif_opener()

# Load environment variables
load_dotenv()

# Configure Gemini API
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
if not GEMINI_API_KEY:
    raise ValueError("GEMINI_API_KEY not found in environment variables")

genai.configure(api_key=GEMINI_API_KEY)

RECEIPT_RECOGNITION_PROMPT = """
Analyze this fuel receipt image and extract the following information in JSON format:

{
  "station": "Gas station name",
  "date": "Date in YYYY-MM-DD format",
  "time": "Time in HH:MM format",
  "liters": float (amount of fuel in liters),
  "price_per_liter": float (price per liter),
  "total_cost": float (total cost),
  "fuel_type": "Type of fuel (95, 98, diesel, etc.)",
  "confidence": int (confidence level 0-100)
}

Important:
- Return ONLY valid JSON, no additional text
- Use null for fields that cannot be determined
- Confidence should reflect how certain you are about the extracted data
"""


async def test_list_models():
    """List available Gemini models"""
    print("=== Available Gemini Models ===")
    try:
        for model in genai.list_models():
            if 'generateContent' in model.supported_generation_methods:
                print(f"- {model.name}")
                print(f"  Display name: {model.display_name}")
                print(f"  Description: {model.description}")
                print()
    except Exception as e:
        print(f"Error listing models: {e}")
        print()


async def test_simple_text():
    """Test simple text generation"""
    print("=== Testing Simple Text Generation ===")
    try:
        # Try different model names
        model_names = [
            'gemini-2.5-flash',
            'gemini-2.0-flash',
            'gemini-flash-latest',
        ]

        for model_name in model_names:
            try:
                print(f"Testing model: {model_name}")
                model = genai.GenerativeModel(model_name)
                response = await model.generate_content_async("Say hello in one word")
                print(f"✓ Success! Response: {response.text}")
                print()
                return model_name  # Return the working model name
            except Exception as e:
                print(f"✗ Failed: {e}")
                print()

        return None
    except Exception as e:
        print(f"Error: {e}")
        return None


async def test_receipt_recognition(image_path: str, model_name: str):
    """Test receipt recognition"""
    print("=== Testing Receipt Recognition ===")
    try:
        # Check if image exists
        if not Path(image_path).exists():
            print(f"Error: Image not found at {image_path}")
            print("Please provide a path to a receipt image")
            return

        # Load image
        image = Image.open(image_path)
        print(f"Image loaded: {image.size}")
        print(f"Image format: {image.format}")
        print()

        # Initialize model with config
        print(f"Using model: {model_name}")
        generation_config = {
            'temperature': 0.2,
            'top_p': 0.95,
            'top_k': 40,
        }
        model = genai.GenerativeModel(model_name, generation_config=generation_config)

        # Generate content
        print("Sending request to Gemini...")
        response = await model.generate_content_async([RECEIPT_RECOGNITION_PROMPT, image])

        # Parse response
        text = response.text.strip()
        print(f"Raw response:\n{text}")
        print()

        # Clean markdown formatting if present
        if text.startswith('```'):
            lines = text.split('\n')
            text = '\n'.join(lines[1:-1]) if len(lines) > 2 else text
            if text.startswith('json'):
                text = text[4:].strip()

        # Parse JSON
        data = json.loads(text)
        print("Parsed JSON:")
        print(json.dumps(data, indent=2, ensure_ascii=False))
        print()
        print("✓ Receipt recognition successful!")

    except json.JSONDecodeError as e:
        print(f"✗ JSON parsing error: {e}")
        print(f"Response text: {text if 'text' in locals() else 'N/A'}")
    except Exception as e:
        print(f"✗ Error: {e}")


async def main():
    print("=" * 60)
    print("Gemini Vision API Test")
    print("=" * 60)
    print()

    # Test 1: List available models
    await test_list_models()

    # Test 2: Simple text generation
    working_model = await test_simple_text()

    if not working_model:
        print("No working model found. Please check your API key and connection.")
        return

    # Test 3: Receipt recognition (if image path provided)
    print("To test receipt recognition, provide image path:")
    print("Example: python test_gemini.py /path/to/receipt.jpg")
    print()

    import sys
    if len(sys.argv) > 1:
        image_path = sys.argv[1]
        await test_receipt_recognition(image_path, working_model)
    else:
        print("No image provided, skipping receipt recognition test")


if __name__ == '__main__':
    asyncio.run(main())
