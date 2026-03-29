"""
Google Sheets integration for storing fuel records
"""
import logging
from datetime import datetime
from decimal import Decimal
from typing import List, Optional

import gspread
from oauth2client.service_account import ServiceAccountCredentials

from config.settings import settings
from models.database import Refuel

logger = logging.getLogger(__name__)


class GoogleSheetsService:
    """Service for working with Google Sheets"""

    def __init__(self):
        """Initialize Google Sheets service"""
        self.client = None
        self.sheet = None
        self._connect()

    def _connect(self):
        """Connect to Google Sheets"""
        try:
            # Define the scope
            scope = [
                'https://spreadsheets.google.com/feeds',
                'https://www.googleapis.com/auth/drive'
            ]

            # Add credentials
            creds = ServiceAccountCredentials.from_json_keyfile_name(
                settings.google_sheets_credentials_file,
                scope
            )

            # Authorize client
            self.client = gspread.authorize(creds)

            # Open the sheet
            self.sheet = self.client.open_by_key(settings.google_sheet_id).sheet1

            logger.info("Successfully connected to Google Sheets")

        except Exception as e:
            logger.error(f"Failed to connect to Google Sheets: {e}", exc_info=True)
            raise

    def ensure_header(self):
        """Ensure the header row exists"""
        try:
            # Check if first row is empty
            first_row = self.sheet.row_values(1)

            if not first_row or first_row[0] == '':
                # Add header
                header = [
                    'Дата',
                    'АЗС',
                    'Топливо',
                    'Литры',
                    'Цена/л',
                    'Сумма',
                    'Пробег',
                    'Пробег с пред.',
                    'Расход л/100км',
                    'Координаты',
                    'AI Confidence'
                ]
                self.sheet.insert_row(header, 1)
                logger.info("Header row created")

        except Exception as e:
            logger.error(f"Error ensuring header: {e}", exc_info=True)

    def add_refuel(self, refuel: Refuel) -> bool:
        """
        Add refuel record to Google Sheets

        Args:
            refuel: Refuel model instance

        Returns:
            bool: True if successful
        """
        try:
            # Ensure header exists
            self.ensure_header()

            # Format data
            date_str = refuel.date.strftime("%d.%m.%Y %H:%M")
            coordinates = ""
            if refuel.latitude and refuel.longitude:
                coordinates = f"{refuel.latitude}, {refuel.longitude}"

            row_data = [
                date_str,
                refuel.station_name,
                refuel.fuel_type,
                float(refuel.liters),
                float(refuel.price_per_liter),
                float(refuel.total_cost),
                refuel.odometer,
                refuel.distance_from_last if refuel.distance_from_last else "",
                float(refuel.consumption) if refuel.consumption else "",
                coordinates,
                refuel.ai_confidence
            ]

            # Append row
            self.sheet.append_row(row_data)

            logger.info(f"Refuel record added to Google Sheets: {refuel.id}")
            return True

        except Exception as e:
            logger.error(f"Error adding refuel to Google Sheets: {e}", exc_info=True)
            return False

    def get_recent_refuels(self, limit: int = 10) -> List[List]:
        """
        Get recent refuel records

        Args:
            limit: Number of records to get

        Returns:
            List of rows
        """
        try:
            all_rows = self.sheet.get_all_values()

            # Skip header and get last N rows
            data_rows = all_rows[1:]  # Skip header
            recent = data_rows[-limit:] if len(data_rows) > limit else data_rows
            recent.reverse()  # Most recent first

            return recent

        except Exception as e:
            logger.error(f"Error getting recent refuels: {e}", exc_info=True)
            return []

    def get_stats(self, start_date: Optional[datetime] = None, end_date: Optional[datetime] = None):
        """
        Get statistics for a period

        Args:
            start_date: Start date (optional)
            end_date: End date (optional)

        Returns:
            Dictionary with statistics
        """
        try:
            all_rows = self.sheet.get_all_values()
            data_rows = all_rows[1:]  # Skip header

            # Filter by date if provided
            if start_date or end_date:
                filtered_rows = []
                for row in data_rows:
                    if not row[0]:  # Skip empty rows
                        continue

                    try:
                        row_date = datetime.strptime(row[0], "%d.%m.%Y %H:%M")

                        if start_date and row_date < start_date:
                            continue
                        if end_date and row_date > end_date:
                            continue

                        filtered_rows.append(row)
                    except ValueError:
                        continue

                data_rows = filtered_rows

            # Calculate statistics
            total_liters = 0
            total_cost = 0
            count = 0

            for row in data_rows:
                try:
                    if len(row) >= 6 and row[3] and row[5]:
                        total_liters += float(row[3])
                        total_cost += float(row[5])
                        count += 1
                except (ValueError, IndexError):
                    continue

            avg_price = total_cost / total_liters if total_liters > 0 else 0

            return {
                'count': count,
                'total_liters': total_liters,
                'total_cost': total_cost,
                'avg_price': avg_price
            }

        except Exception as e:
            logger.error(f"Error getting stats: {e}", exc_info=True)
            return None


# Global instance
sheets_service = None


def get_sheets_service() -> GoogleSheetsService:
    """Get or create Google Sheets service instance"""
    global sheets_service

    if sheets_service is None:
        try:
            sheets_service = GoogleSheetsService()
        except Exception as e:
            logger.error(f"Failed to initialize Google Sheets service: {e}")
            return None

    return sheets_service
