"""
Test GPS extraction from receipt image
"""
from pathlib import Path
from services.image import extract_gps_coordinates, extract_datetime_taken

def test_gps():
    image_path = Path("tests/test_data/receipt_samples/IMG_0406.HEIC")

    if not image_path.exists():
        print(f"❌ Image not found: {image_path}")
        return

    with open(image_path, 'rb') as f:
        image_bytes = f.read()

    print("Testing GPS extraction...")
    print(f"Image: {image_path}")
    print(f"Size: {len(image_bytes)} bytes")
    print()

    # Extract GPS
    lat, lon = extract_gps_coordinates(image_bytes)

    if lat and lon:
        print(f"✅ GPS coordinates found!")
        print(f"📍 Latitude: {lat}")
        print(f"📍 Longitude: {lon}")
        print(f"🗺️  Google Maps: https://www.google.com/maps?q={lat},{lon}")
    else:
        print("❌ No GPS coordinates found in image EXIF data")
        print("📝 Note: GPS coordinates are only available if:")
        print("   1. Location services were enabled when taking the photo")
        print("   2. The app had permission to access location")
        print("   3. EXIF data wasn't stripped from the image")

    print()

    # Extract datetime
    dt = extract_datetime_taken(image_bytes)
    if dt:
        print(f"📅 Photo taken: {dt}")
    else:
        print("❌ No datetime found in EXIF data")

if __name__ == '__main__':
    test_gps()
