"""
Prompts for AI vision models
"""

RECEIPT_RECOGNITION_PROMPT = """
Analyze this Ukrainian gas station receipt (чек) and extract ALL information.

**IMPORTANT - REFUND/RETURN HANDLING**:
If the receipt shows a RETURN/REFUND (ПОВЕРНЕННЯ, САМООБСЛУГОВУВАННЯ with multiple transactions):
- Look for TWO transactions: first one (usually larger) is what was pumped, second (negative or "Повернення") is the refund
- The ACTUAL LITERS used = First transaction liters MINUS Refund liters
- The TOTAL_COST = First transaction total MINUS Refund total
- Example: If pumped 50L for 2945грн but tank full at 9.22L for 543грн → ACTUAL: 50-9.22=40.78L, 2945-543=2402грн
- Mark this in a new field "has_refund": true

CRITICAL FIELDS (MUST extract):
1. LITERS: ACTUAL fuel quantity in liters after subtracting refund (if any)
2. TOTAL_COST: ACTUAL amount paid in грн after subtracting refund (if any)
3. FUEL_TYPE: Fuel type (examples: "А-95", "ДП", "ДП-3", "diesel", "Євро5", "upg", or combination like "ДП-3-Євро5")
4. HAS_REFUND: true if this receipt has a refund/return transaction, false otherwise

STATION INFO:
4. STATION: **EXACT station NUMBER/NAME** - look for specific station ID like "АЗК № 104", "АЗС-магазин №60", "WOG", "OKKO", "UPG" etc.
   - **IMPORTANT**: Extract the SPECIFIC STATION NUMBER (like "АЗК № 104"), NOT just company name (not just "Укрпалетсистем")
   - Look for patterns: "АЗК №", "АЗС №", "АЗС-магазин №", or brand names
5. ADDRESS: Full station address
6. INN: Tax ID (ІПН/ИНН/ПН/ЕГРПОУ - long number)
7. COMPANY: Legal name (ПП/ТОВ/ООО - this is different from station number!)

TRANSACTION INFO:
8. DATE: Date (DD.MM.YYYY format, convert to YYYY-MM-DD)
9. TIME: Time (HH:MM format)
10. PRICE_PER_LITER: Price per liter in грн (next to liters)
11. PUMP: Pump number (ПРК №, КРАП №)
12. RECEIPT_NUM: Receipt number (ТРАНЗАКЦІЯ, №)
13. CASHIER: Cashier name (ОПЕРАТОР)
14. TERMINAL: Terminal number (ТЕРМІНАЛ, ЕПЗ, ЕКВАЙР)
15. PAYMENT: Payment method (БЕЗГОТІВКОВА=card, ГОТІВКА=cash)
16. CARD: Last 4 digits (from ****1234)
17. TAX: Tax amount (ПДВ, НДС, A=)
18. BONUS_EARNED: Points earned (НАРАХОВАНО)
19. BONUS_USED: Points used (ВИКОРИСТАНО)
20. TRANSACTION_ID: Transaction ID

Return JSON with ALL fields you found:
{
  "station": "АЗК № 104",
  "station_address": "м. Дніпро, Полтавське шосе, 617",
  "inn": "3628637006995",
  "company_name": "ПП Укрпалетсистем",
  "date": "2026-01-24",
  "time": "14:08",
  "liters": 44.75,
  "price_per_liter": 64.80,
  "total_cost": 2899.80,
  "fuel_type": "ДП-3-Євро5",
  "has_refund": false,
  "refund_liters": 0.0,
  "refund_amount": 0.0,
  "pump_number": "4",
  "receipt_number": "3654",
  "cashier": "Москвіна В.Н.",
  "terminal_number": "ОРС00015",
  "payment_method": "безготівкова",
  "card_number_last4": "2557",
  "tax_amount": 483.30,
  "bonus_points_earned": 895.00,
  "bonus_points_used": 0.00,
  "transaction_id": "157392431",
  "confidence": 95
}

RULES:
- **CRITICAL**: You MUST extract liters, total_cost, and fuel_type - these are REQUIRED fields
- **FOR REFUND RECEIPTS**: If you see "ПОВЕРНЕННЯ" or two transactions:
  * First transaction = what was initially dispensed
  * Second transaction (negative/return) = what was returned
  * Calculate: liters = first_liters - refund_liters, total_cost = first_total - refund_total
  * Set has_refund=true and include refund_liters and refund_amount
- Read ENTIRE receipt from top to bottom
- For FUEL_TYPE: look for words like "Пал.дис", "ДП", "А-95", "diesel", "Євро5", "upg" - combine them if on same line
- For TOTAL_COST: if no refund, find largest number (often with "А" after it, or near "СУМА" / "ДО СПЛАТИ")
- For LITERS: number followed by "л" or on same line as fuel type
- Include field ONLY if you see it clearly
- Use dots for decimals: 64.80
- Date format: YYYY-MM-DD (convert from DD.MM.YYYY)
- confidence: 95 if all fields clear, 85 if some unclear, 75 if poor quality
- Return pure JSON without markdown code blocks

**ВАЖЛИВИЙ КОНТЕКСТ ДЛЯ РОЗПІЗНАВАННЯ**:
- Об'єм баку автомобіля: 53 літри (МАКСИМУМ!)
- Якщо бачиш liters >53 - це помилка OCR, перевір ще раз уважно
- Типові заправки: 40-53 літри
- Ціна за літр дизелю зараз: ~60-65 грн/л
- Загальна сума зазвичай: 2400-3400 грн
- НІКОЛИ не плутай price_per_liter (60-65) з liters (40-53)!
"""

ODOMETER_RECOGNITION_PROMPT = """
Проанализируй фото одометра (спидометра) автомобиля и извлеки показания пробега.

Верни ТОЛЬКО валидный JSON без дополнительного текста:
{
    "odometer": int,       // Показания одометра в километрах (целое число)
    "confidence": int      // Уверенность распознавания от 0 до 100
}

Важно:
1. Одометр показывает общий пробег автомобиля в километрах
2. Это целое число без дробной части
3. Игнорируй суточный пробег (trip) если он есть
4. Если показания нечитаемы, установи confidence ниже

Верни ТОЛЬКО JSON, без markdown разметки и дополнительного текста.
"""
