"""
EXIF data extraction from images
"""
import logging
from io import BytesIO
from typing import Optional, Tuple
from decimal import Decimal
from datetime import datetime

from PIL import Image
from PIL import ExifTags
from PIL.ExifTags import TAGS, GPSTAGS

# EXIF tag ids (numeric) — DateTimeOriginal / Digitized live in Exif IFD, not always on top-level getexif()
_EXIF_DATETIME_ORIGINAL = 36867
_EXIF_DATETIME_DIGITIZED = 36868
_EXIF_DATETIME = 306  # File change / 0th IFD
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


def _parse_exif_datetime(value) -> Optional[datetime]:
    """Parse common EXIF datetime string formats."""
    if value is None or not isinstance(value, str):
        return None
    value = value.strip()
    for fmt in ("%Y:%m:%d %H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    logger.debug(f"Could not parse EXIF datetime: {value!r}")
    return None


def extract_datetime_taken(image_bytes: bytes) -> Optional[datetime]:
    """
    Extract datetime when photo was taken from EXIF data

    Reads DateTimeOriginal / DateTimeDigitized from the Exif IFD (nested),
    not only the top-level IFD — many phones/cameras store capture time there only.

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

        # 1) Preferred: Exif sub-IFD (DateTimeOriginal, DateTimeDigitized)
        try:
            exif_ifd = exif_data.get_ifd(ExifTags.IFD.Exif)
            for tag_id in (_EXIF_DATETIME_ORIGINAL, _EXIF_DATETIME_DIGITIZED):
                dt = _parse_exif_datetime(exif_ifd.get(tag_id))
                if dt:
                    logger.info(f"EXIF capture time from Exif IFD tag {tag_id}: {dt}")
                    return dt
        except Exception as e:
            logger.debug(f"No usable Exif IFD datetime: {e}")

        # 2) Top-level tags (some files expose DateTime / DateTimeOriginal here)
        for tag, value in exif_data.items():
            tag_name = TAGS.get(tag, tag)
            if tag_name in ("DateTime", "DateTimeOriginal", "DateTimeDigitized"):
                dt = _parse_exif_datetime(value)
                if dt:
                    logger.info(f"EXIF datetime from top-level {tag_name}: {dt}")
                    return dt

        # 3) Direct numeric tag 306 on root (file modification time)
        dt = _parse_exif_datetime(exif_data.get(_EXIF_DATETIME))
        if dt:
            logger.info(f"EXIF datetime from tag {_EXIF_DATETIME}: {dt}")
            return dt

        return None

    except Exception as e:
        logger.error(f"Error extracting datetime from EXIF: {e}")
        return None
