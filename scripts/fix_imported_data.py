#!/usr/bin/env python3
"""
Fix imported data:
1. Add USD conversion for records that don't have it
2. Remove duplicate records
"""
import asyncio
import sys
from datetime import datetime
from decimal import Decimal
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from models.database import Refuel, async_session, init_db
from services.currency.exchange_rate import get_exchange_rate_service
from sqlalchemy import select, delete


async def add_usd_conversion(user_id: int):
    """Add USD conversion for refuels that don't have it"""
    print("💱 Adding USD conversion for imported refuels...")

    exchange_service = get_exchange_rate_service()
    updated = 0
    failed = 0

    async with async_session() as session:
        # Get all refuels without USD data
        result = await session.execute(
            select(Refuel)
            .where(Refuel.user_id == user_id)
            .where(Refuel.usd_rate.is_(None))
            .order_by(Refuel.date.asc())
        )
        refuels = result.scalars().all()

        print(f"📊 Found {len(refuels)} refuels without USD conversion")

        for refuel in refuels:
            try:
                # Get USD rate for the refuel date
                usd_rate = await exchange_service.get_usd_rate(refuel.date)

                if usd_rate:
                    # Convert amounts
                    total_cost_usd = refuel.total_cost / usd_rate
                    price_per_liter_usd = refuel.price_per_liter / usd_rate

                    # Update record
                    refuel.usd_rate = usd_rate
                    refuel.total_cost_usd = total_cost_usd
                    refuel.price_per_liter_usd = price_per_liter_usd

                    updated += 1

                    if updated % 50 == 0:
                        print(f"⏳ Updated {updated} refuels...")
                        await session.commit()  # Commit in batches
                else:
                    date_str = refuel.date.strftime("%Y-%m-%d")
                    print(f"⚠️  Could not get rate for {date_str}, skipping refuel #{refuel.id}")
                    failed += 1

            except Exception as e:
                print(f"❌ Error updating refuel #{refuel.id}: {e}")
                failed += 1
                continue

        # Final commit
        await session.commit()

    print(f"✅ USD conversion completed!")
    print(f"   Updated: {updated}")
    print(f"   Failed: {failed}")


async def remove_duplicates(user_id: int):
    """Remove duplicate refuel records"""
    print("\n🔍 Checking for duplicate refuel records...")

    async with async_session() as session:
        # Get all refuels sorted by date and odometer
        result = await session.execute(
            select(Refuel)
            .where(Refuel.user_id == user_id)
            .order_by(Refuel.date.asc(), Refuel.odometer.asc(), Refuel.id.asc())
        )
        refuels = result.scalars().all()

        # Find duplicates (same date, station, liters, total_cost, odometer)
        duplicates_to_remove = []
        seen = {}

        for refuel in refuels:
            # Create key for comparison
            key = (
                refuel.date.strftime("%Y-%m-%d %H:%M"),
                refuel.station_name,
                float(refuel.liters),
                float(refuel.total_cost),
                refuel.odometer
            )

            if key in seen:
                # This is a duplicate - keep the first one, mark this for deletion
                duplicates_to_remove.append(refuel.id)
                print(f"🔴 Duplicate found: #{refuel.id} (same as #{seen[key]})")
            else:
                seen[key] = refuel.id

        if duplicates_to_remove:
            # Delete duplicates
            await session.execute(
                delete(Refuel).where(Refuel.id.in_(duplicates_to_remove))
            )
            await session.commit()
            print(f"✅ Removed {len(duplicates_to_remove)} duplicate records")
        else:
            print("✅ No duplicates found")


async def main():
    """Main function"""
    if len(sys.argv) < 2:
        print("Usage: python fix_imported_data.py <telegram_user_id>")
        print("Example: python fix_imported_data.py 125791364")
        sys.exit(1)

    user_id = int(sys.argv[1])

    print(f"👤 User ID: {user_id}")
    print()

    # Initialize database
    await init_db()

    # Step 1: Remove duplicates first
    await remove_duplicates(user_id)

    # Step 2: Add USD conversion
    await add_usd_conversion(user_id)

    print("\n🎉 All fixes completed!")


if __name__ == "__main__":
    asyncio.run(main())
