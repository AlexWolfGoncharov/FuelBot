"""
EXIF data extraction from images
"""
import logging
from io import BytesIO
from typing import Optional, Tuple
from decimal import Decimal
from datetime import datetime

from PIL import Image
from PIL.ExifTags import TAGS, GPSTAGS
from pillow_heif import register_heif_opener

# Register HEIF opener to support HEIC files
register_heif_opener()

logger = logging.getLogger(__name__)


def _convert_to_degrees(value) -> Optional[float]:
    """
    Convert GPS coordinates to degrees in float format

    Args:
        value: GPS coordinate in various formats

    Returns:
        Coordinate in decimal degrees or None if conversion fails
    """
    try:
        # If already a float or int
        if isinstance(value, (int, float)):
            return float(value)
        # Try tuple format: ((degrees, 1), (minutes, 1), (seconds, 100))
        elif isinstance(value, (tuple, list)) and len(value) == 3:
            d = float(value[0][0]) / float(value[0][1]) if isinstance(value[0], (tuple, list)) else float(value[0])
            m = float(value[1][0]) / float(value[1][1]) if isinstance(value[1], (tuple, list)) else float(value[1])
            s = float(value[2][0]) / float(value[2][1]) if isinstance(value[2], (tuple, list)) else float(value[2])
            return d + (m / 60.0) + (s / 3600.0)
        return None
    except (TypeError, IndexError, ZeroDivisionError) as e:
        logger.debug(f"Could not convert GPS value to degrees: {e}")
        return None


def extract_gps_coordinates(image_bytes: bytes) -> Tuple[Optional[Decimal], Optional[Decimal]]:
    """
    Extract GPS coordinates from image EXIF data

    Args:
        image_bytes: Image file bytes

    Returns:
        Tuple of (latitude, longitude) or (None, None) if no GPS data found
    """
    try:
        image = Image.open(BytesIO(image_bytes))

        # Get EXIF data
        exif_data = image.getexif()
        if not exif_data:
            logger.debug("No EXIF data found in image")
            return None, None

        # Get GPS Info
        gps_info = {}
        for tag, value in exif_data.items():
            tag_name = TAGS.get(tag, tag)
            if tag_name == 'GPSInfo':
                for gps_tag in value:
                    gps_tag_name = GPSTAGS.get(gps_tag, gps_tag)
                    gps_info[gps_tag_name] = value[gps_tag]

        if not gps_info:
            logger.debug("No GPS info found in EXIF data")
            return None, None

        # Extract latitude
        lat = None
        if 'GPSLatitude' in gps_info and 'GPSLatitudeRef' in gps_info:
            lat = _convert_to_degrees(gps_info['GPSLatitude'])
            if gps_info['GPSLatitudeRef'] == 'S':
                lat = -lat

        # Extract longitude
        lon = None
        if 'GPSLongitude' in gps_info and 'GPSLongitudeRef' in gps_info:
            lon = _convert_to_degrees(gps_info['GPSLongitude'])
            if gps_info['GPSLongitudeRef'] == 'W':
                lon = -lon

        if lat is not None and lon is not None:
            logger.info(f"GPS coordinates extracted: {lat:.6f}, {lon:.6f}")
            return Decimal(str(round(lat, 7))), Decimal(str(round(lon, 7)))

        return None, None

    except Exception as e:
        logger.error(f"Error extracting GPS coordinates: {e}")
        return None, None


def extract_datetime_taken(image_bytes: bytes) -> Optional[datetime]:
    """
    Extract datetime when photo was taken from EXIF data

    Args:
        image_bytes: Image file bytes

    Returns:
        Datetime when photo was taken or None if not found
    """
    try:
        image = Image.open(BytesIO(image_bytes))

        exif_data = image.getexif()
        if not exif_data:
            return None

        # Look for DateTime tags
        for tag, value in exif_data.items():
            tag_name = TAGS.get(tag, tag)
            if tag_name in ['DateTime', 'DateTimeOriginal', 'DateTimeDigitized']:
                try:
                    # Format: "2024:01:15 14:30:00"
                    return datetime.strptime(value, "%Y:%m:%d %H:%M:%S")
                except ValueError:
                    logger.debug(f"Could not parse datetime: {value}")
                    continue

        return None

    except Exception as e:
        logger.error(f"Error extracting datetime from EXIF: {e}")
        return None
