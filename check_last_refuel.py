"""Check last refuel in database"""
import asyncio
from models.database import async_session, Refuel
from sqlalchemy import select, desc

async def check_last():
    async with async_session() as session:
        result = await session.execute(
            select(Refuel)
            .where(Refuel.user_id == 1)  # User ID in database (not telegram_id)
            .order_by(desc(Refuel.date))
            .limit(3)
        )
        refuels = result.scalars().all()

        print(f"\n=== Last 3 refuels for user_id=1 ===")
        for refuel in refuels:
            print(f"ID: {refuel.id}")
            print(f"Date: {refuel.date}")
            print(f"Station: {refuel.station_name}")
            print(f"Liters: {refuel.liters}")
            print(f"Odometer: {refuel.odometer}")
            print(f"Receipt file: {refuel.receipt_file_id}")
            print("-" * 50)

if __name__ == "__main__":
    asyncio.run(check_last())
