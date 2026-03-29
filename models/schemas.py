"""
Pydantic schemas for data validation
"""
from datetime import datetime
from decimal import Decimal
from typing import Optional
from pydantic import BaseModel, Field, validator


class ReceiptData(BaseModel):
    """Schema for receipt recognition data"""
    # Required fields
    liters: float = Field(..., gt=0, description="Liters of fuel")
    total_cost: float = Field(..., gt=0, description="Total cost")
    station: str = Field(..., min_length=1, description="Gas station name")
    fuel_type: str = Field(..., min_length=1, description="Type of fuel (e.g., AI-95, Diesel)")
    date: Optional[str] = Field(None, description="Date in YYYY-MM-DD format")
    time: Optional[str] = Field(None, description="Time in HH:MM format")
    confidence: int = Field(..., ge=0, le=100, description="AI confidence score (0-100)")

    # Optional fields - can be extracted if available
    price_per_liter: Optional[float] = Field(None, gt=0, description="Price per liter")
    receipt_number: Optional[str] = Field(None, description="Receipt/check number")
    terminal_number: Optional[str] = Field(None, description="Terminal/POS number")
    cashier: Optional[str] = Field(None, description="Cashier name or ID")
    pump_number: Optional[str] = Field(None, description="Pump/column number")
    payment_method: Optional[str] = Field(None, description="Payment method (card, cash, etc.)")
    card_number_last4: Optional[str] = Field(None, description="Last 4 digits of card number")
    station_address: Optional[str] = Field(None, description="Gas station address")
    station_phone: Optional[str] = Field(None, description="Gas station phone number")
    tax_amount: Optional[float] = Field(None, description="Tax amount (VAT/NDS)")
    discount_amount: Optional[float] = Field(None, description="Discount amount if any")
    bonus_points_earned: Optional[float] = Field(None, description="Bonus/loyalty points earned")
    bonus_points_used: Optional[float] = Field(None, description="Bonus/loyalty points used")
    company_name: Optional[str] = Field(None, description="Company legal name")
    inn: Optional[str] = Field(None, description="INN (tax identification number)")
    transaction_id: Optional[str] = Field(None, description="Transaction ID")

    # Refund/return fields
    has_refund: Optional[bool] = Field(False, description="True if receipt has refund/return transaction")
    refund_liters: Optional[float] = Field(None, description="Refunded fuel quantity in liters")
    refund_amount: Optional[float] = Field(None, description="Refunded amount in currency")

    @validator('total_cost')
    def validate_total_cost(cls, v, values):
        """Validate that total_cost ≈ liters × price_per_liter if price is available"""
        if 'liters' in values and 'price_per_liter' in values and values.get('price_per_liter'):
            expected = values['liters'] * values['price_per_liter']
            if abs(v - expected) > 10:  # Allow 10 ruble tolerance
                raise ValueError(f"Total cost {v} doesn't match liters × price ({expected})")
        return v

    class Config:
        json_schema_extra = {
            "example": {
                "liters": 45.5,
                "price_per_liter": 55.90,
                "total_cost": 2543.45,
                "station": "ЛУКОЙЛ",
                "fuel_type": "АИ-95",
                "date": "2024-01-15",
                "time": "14:30",
                "confidence": 95,
                "receipt_number": "1234567",
                "pump_number": "5",
                "payment_method": "card"
            }
        }


class OdometerData(BaseModel):
    """Schema for odometer recognition data"""
    odometer: int = Field(..., gt=0, description="Odometer reading in kilometers")
    confidence: int = Field(..., ge=0, le=100, description="AI confidence score (0-100)")

    class Config:
        json_schema_extra = {
            "example": {
                "odometer": 125430,
                "confidence": 92
            }
        }


class ExifData(BaseModel):
    """Schema for EXIF data extracted from images"""
    latitude: Optional[Decimal] = Field(None, description="GPS latitude")
    longitude: Optional[Decimal] = Field(None, description="GPS longitude")
    datetime_taken: Optional[datetime] = Field(None, description="Photo capture datetime")

    class Config:
        json_schema_extra = {
            "example": {
                "latitude": 55.751244,
                "longitude": 37.618423,
                "datetime_taken": "2024-01-15T14:30:00"
            }
        }


class RefuelCreate(BaseModel):
    """Schema for creating a new refuel record"""
    user_id: int
    date: datetime
    station_name: str
    fuel_type: str
    liters: Decimal
    price_per_liter: Decimal
    total_cost: Decimal
    usd_rate: Optional[Decimal] = None
    total_cost_usd: Optional[Decimal] = None
    price_per_liter_usd: Optional[Decimal] = None
    odometer: int
    distance_from_last: Optional[int] = None
    consumption: Optional[Decimal] = None
    full_tank: bool = True
    latitude: Optional[Decimal] = None
    longitude: Optional[Decimal] = None
    receipt_file_id: str
    odometer_file_id: Optional[str] = None
    ai_confidence: int = 0


class RefuelResponse(BaseModel):
    """Schema for refuel record response"""
    id: int
    user_id: int
    date: datetime
    station_name: str
    fuel_type: str
    liters: Decimal
    price_per_liter: Decimal
    total_cost: Decimal
    odometer: int
    distance_from_last: Optional[int]
    consumption: Optional[Decimal]
    created_at: datetime

    class Config:
        from_attributes = True
