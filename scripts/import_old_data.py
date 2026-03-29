#!/usr/bin/env python3
"""
Import old refuel data from JSON export
"""
import asyncio
import json
import sys
from datetime import datetime
from decimal import Decimal
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from models.database import Refuel, async_session, init_db


# Mapping fuel subtypes to fuel names
FUEL_TYPE_MAP = {
    "3": "А-95",
    "4": "А-95",
    "5": "А-95+",
    "7": "ДП",
    "8": "А-98",
    "12": "А-95 (ЄС)",
    "20": "А-95",
    "21": "ДП-3"
}

# Station ID to name mapping (можна розширити)
STATION_MAP = {
    26470: "АЗК № 104",
    10325: "WOG",
    12137: "ОККО",
    9395: "UPG",
    9547: "Shell",
    9551: "БРСМ",
    16891: "Socar",
    19360: "ANP",
    20275: "KLO",
    22800: "Авіас",
    29946: "Укрнафта"
}


async def import_refuels(json_file: str, user_id: int):
    """
    Import refuels from JSON file

    Args:
        json_file: Path to JSON file with refuel data
        user_id: Telegram user ID to assign refuels to
    """
    # Read JSON file
    with open(json_file, 'r', encoding='utf-8') as f:
        data = json.load(f)

    if data.get("result") != "success":
        print("❌ Invalid JSON format")
        return

    refuels_list = data.get("list", [])
    print(f"📊 Found {len(refuels_list)} refuels to import")

    # Filter only petrol refuels
    petrol_refuels = [r for r in refuels_list if r.get("type") == "petrol"]
    print(f"⛽ Filtering: {len(petrol_refuels)} petrol refuels")

    # Initialize database
    await init_db()

    imported = 0
    skipped = 0
    errors = 0

    async with async_session() as session:
        for old_refuel in petrol_refuels:
            try:
                # Parse date
                date_str = old_refuel.get("date", "")
                try:
                    date = datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S")
                except ValueError:
                    try:
                        date = datetime.strptime(date_str, "%Y-%m-%d")
                    except ValueError:
                        print(f"⚠️  Skipping: invalid date format '{date_str}'")
                        skipped += 1
                        continue

                # Get fuel type
                subtype = old_refuel.get("subtype", "")
                fuel_type = FUEL_TYPE_MAP.get(str(subtype), f"Тип {subtype}")

                # Get station name
                station_id = old_refuel.get("station_id", 0)
                station_name = STATION_MAP.get(station_id, f"АЗС #{station_id}" if station_id else "Невідома АЗС")

                # Get amounts
                liters = Decimal(str(old_refuel.get("amount", 0)))
                price_per_liter = Decimal(str(old_refuel.get("price", 0)))
                total_cost = Decimal(str(old_refuel.get("total", 0)))
                odometer = int(old_refuel.get("probeg", 0))
                full_tank = bool(old_refuel.get("fulltank", 1))

                # Skip invalid data
                if liters <= 0 or total_cost <= 0 or odometer <= 0:
                    print(f"⚠️  Skipping: invalid amounts (liters={liters}, cost={total_cost}, odo={odometer})")
                    skipped += 1
                    continue

                # Create refuel record
                refuel = Refuel(
                    user_id=user_id,
                    date=date,
                    station_name=station_name,
                    fuel_type=fuel_type,
                    liters=liters,
                    price_per_liter=price_per_liter,
                    total_cost=total_cost,
                    odometer=odometer,
                    full_tank=full_tank,
                    receipt_file_id="imported",  # Placeholder
                    ai_confidence=100  # Imported data assumed correct
                )

                session.add(refuel)
                imported += 1

                if imported % 50 == 0:
                    print(f"⏳ Imported {imported} refuels...")

            except Exception as e:
                print(f"❌ Error importing refuel: {e}")
                print(f"   Data: {old_refuel}")
                errors += 1
                continue

        # Commit all
        await session.commit()

    print(f"\n✅ Import completed!")
    print(f"   Imported: {imported}")
    print(f"   Skipped: {skipped}")
    print(f"   Errors: {errors}")

    # Now recalculate distances and consumption
    print(f"\n🔄 Recalculating distances and consumption...")
    await recalculate_all(user_id)


async def recalculate_all(user_id: int):
    """Recalculate distance and consumption for all refuels"""
    from sqlalchemy import select

    async with async_session() as session:
        # Get all refuels sorted by odometer
        result = await session.execute(
            select(Refuel)
            .where(Refuel.user_id == user_id)
            .order_by(Refuel.odometer.asc())
        )
        refuels = result.scalars().all()

        print(f"📊 Found {len(refuels)} refuels to recalculate")

        prev_odometer = None
        prev_liters = None

        for refuel in refuels:
            if prev_odometer is not None:
                # Calculate distance
                distance = refuel.odometer - prev_odometer

                if distance > 0:
                    refuel.distance_from_last = distance

                    # Calculate consumption (л/100км)
                    if prev_liters and prev_liters > 0 and refuel.full_tank:
                        consumption = (float(prev_liters) / distance) * 100
                        refuel.consumption = Decimal(str(round(consumption, 2)))

            prev_odometer = refuel.odometer
            prev_liters = refuel.liters if refuel.full_tank else None

        await session.commit()
        print("✅ Recalculation completed!")


async def main():
    """Main function"""
    if len(sys.argv) < 3:
        print("Usage: python import_old_data.py <json_file> <telegram_user_id>")
        print("Example: python import_old_data.py import_data.json 125791364")
        sys.exit(1)

    json_file = sys.argv[1]
    user_id = int(sys.argv[2])

    if not Path(json_file).exists():
        print(f"❌ File not found: {json_file}")
        sys.exit(1)

    print(f"📥 Importing data from: {json_file}")
    print(f"👤 User ID: {user_id}")
    print()

    await import_refuels(json_file, user_id)


if __name__ == "__main__":
    asyncio.run(main())
