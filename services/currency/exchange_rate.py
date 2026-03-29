"""
Exchange rate service for UAH to USD conversion
Uses PrivatBank API (free, no registration required)
"""
import logging
from decimal import Decimal
from datetime import datetime, timedelta
from typing import Optional
import httpx

logger = logging.getLogger(__name__)


class ExchangeRateService:
    """Service for getting UAH/USD exchange rate"""

    def __init__(self):
        self.privatbank_api = "https://api.privatbank.ua/p24api/pubinfo?exchange&coursid=5"
        self.nbu_api = "https://bank.gov.ua/NBUStatService/v1/statdirectory/exchange"
        self.cache = {}
        self.cache_expiry = {}

    async def get_usd_rate(self, date: Optional[datetime] = None) -> Optional[Decimal]:
        """
        Get UAH to USD exchange rate for a specific date (or current if date is None)

        Args:
            date: Date for which to get the rate. If None, gets current rate.

        Returns:
            Decimal: Rate (how many UAH for 1 USD) or None if failed
        """
        try:
            # Use current date if not specified
            target_date = date or datetime.now()
            date_str = target_date.strftime("%Y%m%d")

            # Check cache (valid for 24 hours for historical rates, 1 hour for current)
            cache_key = f"usd_rate_{date_str}"
            cache_duration = timedelta(hours=24 if date else 1)

            if cache_key in self.cache:
                if datetime.now() < self.cache_expiry.get(cache_key, datetime.now()):
                    logger.debug(f"Using cached USD rate for {date_str}: {self.cache[cache_key]}")
                    return self.cache[cache_key]

            # For current rate, use PrivatBank (faster)
            if not date or target_date.date() == datetime.now().date():
                async with httpx.AsyncClient(timeout=10.0) as client:
                    response = await client.get(self.privatbank_api)
                    response.raise_for_status()
                    data = response.json()

                for item in data:
                    if item.get('ccy') == 'USD' and item.get('base_ccy') == 'UAH':
                        rate = Decimal(str(item['sale']))

                        # Cache
                        self.cache[cache_key] = rate
                        self.cache_expiry[cache_key] = datetime.now() + cache_duration

                        logger.info(f"Fetched current USD rate: 1 USD = {rate} UAH")
                        return rate

            # For historical rates, use NBU API
            else:
                nbu_url = f"{self.nbu_api}?valcode=USD&date={date_str}&json"
                async with httpx.AsyncClient(timeout=10.0) as client:
                    response = await client.get(nbu_url)
                    response.raise_for_status()
                    data = response.json()

                if data and len(data) > 0:
                    rate = Decimal(str(data[0]['rate']))

                    # Cache
                    self.cache[cache_key] = rate
                    self.cache_expiry[cache_key] = datetime.now() + cache_duration

                    logger.info(f"Fetched historical USD rate for {date_str}: 1 USD = {rate} UAH")
                    return rate

            logger.error(f"USD rate not found for date {date_str}")
            return None

        except httpx.HTTPError as e:
            logger.error(f"HTTP error fetching exchange rate: {e}")
            return None
        except Exception as e:
            logger.error(f"Error fetching exchange rate for {date_str if 'date_str' in locals() else 'unknown date'}: {e}", exc_info=True)
            return None

    async def convert_uah_to_usd(self, amount_uah: Decimal) -> Optional[Decimal]:
        """
        Convert UAH amount to USD

        Args:
            amount_uah: Amount in UAH

        Returns:
            Amount in USD or None if conversion failed
        """
        rate = await self.get_usd_rate()
        if rate is None:
            return None

        try:
            amount_usd = amount_uah / rate
            logger.debug(f"Converted {amount_uah} UAH to {amount_usd:.2f} USD (rate: {rate})")
            return amount_usd
        except Exception as e:
            logger.error(f"Error converting currency: {e}")
            return None


# Global instance
_exchange_rate_service = None


def get_exchange_rate_service() -> ExchangeRateService:
    """Get or create exchange rate service instance"""
    global _exchange_rate_service
    if _exchange_rate_service is None:
        _exchange_rate_service = ExchangeRateService()
    return _exchange_rate_service
