import json
import pandas as pd
from collections import defaultdict
import os
import zipfile
import glob

def find_data_file():
    json_files = glob.glob("src/*.json")
    if json_files:
        return json_files[0]

    zip_files = glob.glob("src/*.zip")
    if zip_files:
        with zipfile.ZipFile(zip_files[0], 'r') as zip_ref:
            json_in_zip = [f for f in zip_ref.namelist() if f.endswith('.json')]
            if json_in_zip:
                zip_ref.extract(json_in_zip[0], "src/")
                return os.path.join("src", json_in_zip[0])
    return None

def analyze_all_fields():
    filepath = find_data_file()
    if not filepath:
        print("No data file found.")
        return

    print(f"Analyzing {filepath}...")
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except UnicodeDecodeError:
        # Fallback for Windows if needed
        with open(filepath, 'r', encoding='cp1252') as f:
            data = json.load(f)

    field_stats = defaultdict(lambda: {'count': 0, 'samples': set(), 'is_numeric': True, 'min': float('inf'), 'max': float('-inf')})

    for item in data['Data']:
        field = item.get('dataFieldName', 'UNKNOWN')
        value = item.get('value')

        stats = field_stats[field]
        stats['count'] += 1

        # Check if numeric
        try:
            float_val = float(value)
            if float_val < stats['min']: stats['min'] = float_val
            if float_val > stats['max']: stats['max'] = float_val
        except (ValueError, TypeError):
            stats['is_numeric'] = False
            stats['min'] = None
            stats['max'] = None

        # Store samples (up to 5 unique)
        if len(stats['samples']) < 5:
            stats['samples'].add(str(value))

    # Output results
    print(f"{'Field Name':<50} | {'Count':<8} | {'Type':<10} | {'Min':<10} | {'Max':<10} | {'Samples'}")
    print("-" * 120)

    # Sort by count descending
    sorted_fields = sorted(field_stats.items(), key=lambda x: x[1]['count'], reverse=True)

    for field, stats in sorted_fields:
        type_str = "Numeric" if stats['is_numeric'] else "String"
        min_str = f"{stats['min']:.2f}" if stats['is_numeric'] and stats['min'] != float('inf') else "-"
        max_str = f"{stats['max']:.2f}" if stats['is_numeric'] and stats['max'] != float('-inf') else "-"
        samples = ", ".join(list(stats['samples'])[:3])

        print(f"{field:<50} | {stats['count']:<8} | {type_str:<10} | {min_str:<10} | {max_str:<10} | {samples}")

if __name__ == "__main__":
    analyze_all_fields()
