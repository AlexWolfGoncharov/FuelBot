"""
Test detailed extraction with Gemini
"""
import asyncio
import json
from pathlib import Path

import google.generativeai as genai
from PIL import Image
from dotenv import load_dotenv
import os
from pillow_heif import register_heif_opener

register_heif_opener()
load_dotenv()

genai.configure(api_key=os.getenv('GEMINI_API_KEY'))

DETAILED_PROMPT = """
Analyze this gas station receipt image and extract information field by field.

Answer each question by looking at the receipt:

1. STATION NAME: What is the gas station name? (look at the top)
2. ADDRESS: What is the full address? (usually near top)
3. INN/TAX ID: What is the ІПН/ИНН/ПН number? (long number near top)
4. COMPANY: What is the legal company name? (ПП, ТОВ, ООО at top)
5. DATE: What date is shown? (format DD.MM.YYYY)
6. TIME: What time is shown? (format HH:MM)
7. LITERS: How many liters of fuel? (number with л)
8. PRICE PER LITER: What is the price per liter? (грн/л, price next to liters)
9. TOTAL COST: What is the total amount paid? (largest number, СУМА)
10. FUEL TYPE: What type of fuel? (А-95, diesel, ДП)
11. PUMP NUMBER: What pump/column number? (ПРК №, КРАП №, колонка)
12. RECEIPT NUMBER: What is receipt/transaction number? (ТРАНЗАКЦІЯ, чек №)
13. CASHIER: Who is the cashier/operator? (ОПЕРАТОР, name at bottom)
14. TERMINAL: What is terminal number? (ТЕРМІНАЛ, ЕПЗ)
15. PAYMENT METHOD: How was payment made? (БЕЗГОТІВКОВА/ГОТІВКА)
16. CARD DIGITS: What are last 4 digits of card? (****1234)
17. TAX AMOUNT: What is the tax/VAT amount? (ПДВ, НДС)
18. BONUS EARNED: How many bonus points earned? (НАРАХОВАНО)
19. BONUS USED: How many bonus points used? (ВИКОРИСТАНО)
20. TRANSACTION ID: What is transaction ID number?

Now return a JSON with ALL the information you found:
{
  "station": "...",
  "station_address": "...",
  "inn": "...",
  "company_name": "...",
  "date": "YYYY-MM-DD",
  "time": "HH:MM",
  "liters": 0.0,
  "price_per_liter": 0.0,
  "total_cost": 0.0,
  "fuel_type": "...",
  "pump_number": "...",
  "receipt_number": "...",
  "cashier": "...",
  "terminal_number": "...",
  "payment_method": "...",
  "card_number_last4": "...",
  "tax_amount": 0.0,
  "bonus_points_earned": 0.0,
  "bonus_points_used": 0.0,
  "transaction_id": "...",
  "confidence": 95
}

Return ONLY JSON without markdown.
"""

async def test_detailed():
    image_path = "tests/test_data/receipt_samples/IMG_0406.HEIC"
    image = Image.open(image_path)

    generation_config = {
        'temperature': 0.1,
        'top_p': 0.95,
    }
    model = genai.GenerativeModel('gemini-2.5-flash', generation_config=generation_config)

    print("Sending detailed extraction request...")
    response = await model.generate_content_async([DETAILED_PROMPT, image])

    text = response.text.strip()
    print("Raw response:")
    print(text)
    print("\n" + "="*60 + "\n")

    # Clean markdown
    if text.startswith('```'):
        lines = text.split('\n')
        text = '\n'.join(lines[1:-1]) if len(lines) > 2 else text
        if text.startswith('json'):
            text = text[4:].strip()

    # Parse JSON
    data = json.loads(text)
    print("Parsed JSON:")
    print(json.dumps(data, indent=2, ensure_ascii=False))

    # Count extracted fields
    extracted = {k: v for k, v in data.items() if v and v != "..."}
    print(f"\n✓ Extracted {len(extracted)} fields!")

if __name__ == '__main__':
    asyncio.run(test_detailed())
