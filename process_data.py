import json
import pandas as pd
import numpy as np
import os
import zipfile
import glob

def find_data_file():
    # First, look for a JSON file in src/
    json_files = glob.glob("src/*.json")
    if json_files:
        print(f"Found JSON file: {json_files[0]}")
        return json_files[0]

    # If no JSON, look for a ZIP file and unzip it
    zip_files = glob.glob("src/*.zip")
    if zip_files:
        print(f"Found ZIP file: {zip_files[0]}")
        with zipfile.ZipFile(zip_files[0], 'r') as zip_ref:
            # Look for JSON inside the zip
            json_in_zip = [f for f in zip_ref.namelist() if f.endswith('.json')]
            if json_in_zip:
                print(f"Extracting {json_in_zip[0]} from ZIP...")
                zip_ref.extract(json_in_zip[0], "src/")
                return os.path.join("src", json_in_zip[0])

    return None

def load_and_process_data(output_path):
    filepath = find_data_file()

    if not filepath:
        print("Error: No data file found in src/ (checked for .json and .zip)")
        return

    print(f"Loading data from {filepath}...")
    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)

    print("Converting to DataFrame...")
    df = pd.DataFrame(data['Data'])

    # Convert timestamp to datetime
    # Use format='mixed' to handle potential milliseconds or inconsistent formats
    # Use errors='coerce' to turn unparseable strings (like "N/A") into NaT
    df['timestampUtc'] = pd.to_datetime(df['timestampUtc'], format='mixed', errors='coerce')

    # Drop rows where timestamp could not be parsed
    initial_len = len(df)
    df = df.dropna(subset=['timestampUtc'])
    dropped_count = initial_len - len(df)
    if dropped_count > 0:
        print(f"Dropped {dropped_count} rows with invalid timestamps.")

    print("Pivoting data...")
    # Filter for interesting columns to keep the size manageable
    interesting_fields = [
        'currentSOCInPct',
        'chargePowerInKW',
        'chargeMode',
        'remainingChargingTimeToCompleteInMin',
        'mileage',
        'cruisingRangeElectricInKm',
        'temperatureOutsideVehicle',
        'climatisationState',
        'chargingState'
    ]

    df_filtered = df[df['dataFieldName'].isin(interesting_fields)]

    # Pivot: Index=timestamp, Columns=dataFieldName, Values=value
    # We use 'last' in case of duplicate timestamps for the same field
    df_pivot = df_filtered.pivot_table(index='timestampUtc', columns='dataFieldName', values='value', aggfunc='last')

    # Convert numeric columns
    numeric_cols = [
        'currentSOCInPct',
        'chargePowerInKW',
        'remainingChargingTimeToCompleteInMin',
        'mileage',
        'cruisingRangeElectricInKm',
        'temperatureOutsideVehicle'
    ]

    for col in numeric_cols:
        if col in df_pivot.columns:
            df_pivot[col] = pd.to_numeric(df_pivot[col], errors='coerce')

    # Sort by time
    df_pivot = df_pivot.sort_index()

    # Forward fill to create a continuous state
    df_filled = df_pivot.ffill()

    print(f"Processed data shape: {df_filled.shape}")
    print(df_filled.head())

    print(f"Saving to {output_path}...")
    df_filled.to_csv(output_path)
    print("Done.")

if __name__ == "__main__":
    load_and_process_data("processed_data.csv")
