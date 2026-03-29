#!/usr/bin/env python3
"""
Create full import JSON from the data you provided
Paste your full JSON data here and run this script
"""
import json

# PASTE YOUR FULL JSON DATA HERE (the one you sent me with all records)
data = {
    "result": "success",
    "list": []  # << REPLACE THIS WITH YOUR FULL LIST
}

# Write to file
with open('import_data_full.json', 'w', encoding='utf-8') as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

print(f"✅ Created import_data_full.json with {len(data['list'])} records")
