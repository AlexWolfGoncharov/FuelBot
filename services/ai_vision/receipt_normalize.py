"""
Normalize OCR output before Pydantic validation (time formats, whitespace).
"""
import re
from typing import Any, Dict


def normalize_receipt_fields(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    - time: HH:MM:SS or H:M -> HH:MM (schema expects HH:MM)
    - date: strip; optional fix DD.MM.YYYY string mistaken as single field
    """
    if not isinstance(data, dict):
        return data
    out = dict(data)

    t = out.get("time")
    if isinstance(t, str) and t.strip():
        raw = t.strip()
        parts = raw.replace(".", ":").split(":")
        if len(parts) >= 2:
            try:
                h = int(parts[0])
                m = int(parts[1])
                if 0 <= h <= 23 and 0 <= m <= 59:
                    out["time"] = f"{h:02d}:{m:02d}"
            except ValueError:
                pass

    d = out.get("date")
    if isinstance(d, str) and d.strip():
        s = d.strip()
        # Якщо модель повернула DD.MM.YYYY у полі date — конвертуємо
        m = re.match(r"^(\d{1,2})\.(\d{1,2})\.(\d{4})$", s)
        if m:
            day, month, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
            if 1 <= month <= 12 and 1 <= day <= 31:
                out["date"] = f"{year:04d}-{month:02d}-{day:02d}"
        else:
            out["date"] = s

    return out
