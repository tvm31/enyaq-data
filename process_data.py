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

def calculate_consumption_and_charges(df):
    """
    Calculates estimated consumption and charging sessions.
    Assumption: Enyaq 80 has ~77 kWh net capacity. Enyaq 60 ~58 kWh.
    We'll use 77 kWh as a default but allow adjustment.
    """
    BATTERY_CAPACITY_KWH = 77.0

    # Ensure necessary columns exist
    required_cols = ['currentSOCInPct', 'mileage', 'chargePowerInKW', 'temperatureOutsideVehicle']
    for col in required_cols:
        if col not in df.columns:
            print(f"Warning: Missing column {col} for detailed analysis.")
            return None, None

    # Identify Trips
    # A trip starts when mileage increases and stops when there's a significant time gap (>15min) or charging starts
    # We can detect 'driving' state by mileage changes

    # Calculate deltas
    df['delta_mileage'] = df['mileage'].diff().fillna(0)
    df['delta_soc'] = df['currentSOCInPct'].diff().fillna(0)
    df['time_diff_min'] = df.index.to_series().diff().dt.total_seconds().div(60).fillna(0)

    # Define "Driving" vs "Charging" vs "Idle"
    # Charging: chargePowerInKW > 0 (or some small threshold)
    is_charging = df['chargePowerInKW'] > 0.5

    # Driving: Mileage increased
    is_driving = df['delta_mileage'] > 0

    # Detect Trip Sessions
    # We'll create a session ID that increments when:
    # 1. State changes from Driving to Not Driving (or vice versa)
    # 2. Time gap > 30 mins

    # Simple logic: New trip if mileage changed and time gap > 30 min OR previous state was charging
    # This is complex on raw time series. Let's iterate or use groupers.

    # Approach 2: Filter for driving events, then group by time gaps
    driving_data = df[is_driving].copy()

    trips = []

    if not driving_data.empty:
        # If time gap > 30 mins, it's a new trip
        driving_data['new_trip'] = driving_data['time_diff_min'] > 30
        driving_data['trip_id'] = driving_data['new_trip'].cumsum()

        # Aggregate trips
        # Note: driving_data only contains rows where mileage CHANGED.
        # So start_time might be slightly off (it's the time of the first mileage update).
        # We can look back at the full DF to find true start, but for now this is a good approximation.

        for trip_id, group in driving_data.groupby('trip_id'):
            start_time = group.index.min()
            end_time = group.index.max()

            # Get full data range for this trip (including surrounding points for better SOC estimation)
            # We want the SOC at start_time and SOC at end_time
            # Using the full DF to get values at these timestamps

            # Start: Just before the first movement?
            # End: The last movement

            distance = group['delta_mileage'].sum()

            # SOC consumption: SOC_start - SOC_end
            # We need the SOC *before* the trip started vs *after* it ended.
            # Using the values from the group is risky if SOC updates happen less frequently than mileage.
            # Let's take the first and last SOC in the group.
            start_soc = group['currentSOCInPct'].iloc[0]
            end_soc = group['currentSOCInPct'].iloc[-1]
            soc_diff = start_soc - end_soc

            # Energy consumed (kWh) = Delta SOC% * Capacity
            # Only count if SOC decreased
            energy_consumed_kwh = (soc_diff / 100.0) * BATTERY_CAPACITY_KWH if soc_diff > 0 else 0

            # Consumption (kWh/100km)
            consumption = (energy_consumed_kwh / distance * 100) if distance > 0 else 0

            avg_temp = group['temperatureOutsideVehicle'].mean()

            trips.append({
                'Start Time': start_time,
                'End Time': end_time,
                'Distance (km)': round(distance, 1),
                'Start SOC (%)': start_soc,
                'End SOC (%)': end_soc,
                'Energy Used (kWh)': round(energy_consumed_kwh, 2),
                'Consumption (kWh/100km)': round(consumption, 2),
                'Avg Temp (°C)': round(avg_temp, 1)
            })

    df_trips = pd.DataFrame(trips)

    # Detect Charging Sessions
    charging_data = df[is_charging].copy()
    charges = []

    if not charging_data.empty:
        # New charge session if time gap > 15 mins
        charging_data['new_charge'] = charging_data['time_diff_min'] > 15
        charging_data['charge_id'] = charging_data['new_charge'].cumsum()

        for charge_id, group in charging_data.groupby('charge_id'):
            start_time = group.index.min()
            end_time = group.index.max()

            start_soc = group['currentSOCInPct'].iloc[0]
            end_soc = group['currentSOCInPct'].iloc[-1]
            soc_added = end_soc - start_soc

            # Energy added (approx based on SOC)
            energy_added_soc = (soc_added / 100.0) * BATTERY_CAPACITY_KWH if soc_added > 0 else 0

            # Avg Power
            avg_power = group['chargePowerInKW'].mean()
            max_power = group['chargePowerInKW'].max()

            # Duration (hours)
            duration_h = (end_time - start_time).total_seconds() / 3600.0

            charges.append({
                'Start Time': start_time,
                'End Time': end_time,
                'Duration (h)': round(duration_h, 2),
                'Start SOC (%)': start_soc,
                'End SOC (%)': end_soc,
                'Energy Added (kWh)': round(energy_added_soc, 2),
                'Avg Power (kW)': round(avg_power, 1),
                'Max Power (kW)': round(max_power, 1)
            })

    df_charges = pd.DataFrame(charges)

    return df_trips, df_charges


def load_and_process_data(output_path, notifications_output_path, trips_output_path, charges_output_path):
    filepath = find_data_file()

    if not filepath:
        print("Error: No data file found in src/ (checked for .json and .zip)")
        return

    print(f"Loading data from {filepath}...")
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except UnicodeDecodeError:
        print("Falling back to CP1252 encoding...")
        with open(filepath, 'r', encoding='cp1252') as f:
            data = json.load(f)

    print("Converting to DataFrame...")
    df = pd.DataFrame(data['Data'])

    # Convert timestamp to datetime
    # Use format='mixed' to handle potential milliseconds or inconsistent formats
    # Use errors='coerce' to turn unparseable strings (like "N/A") into NaT
    # Use utc=True to handle mixed timezones by normalizing to UTC
    df['timestampUtc'] = pd.to_datetime(df['timestampUtc'], format='mixed', errors='coerce', utc=True)

    # Drop rows where timestamp could not be parsed
    initial_len = len(df)
    df = df.dropna(subset=['timestampUtc'])
    dropped_count = initial_len - len(df)
    if dropped_count > 0:
        print(f"Dropped {dropped_count} rows with invalid timestamps.")

    print("Extracting Notifications...")
    # Extract notifications separately (text, priority, category)
    notification_fields = ['text', 'priority', 'category', 'iconColor']
    df_notifications = df[df['dataFieldName'].isin(notification_fields)].copy()

    if not df_notifications.empty:
        # Pivot notifications so each timestamp has text/priority/category
        # We don't forward fill notifications because they are point-in-time events
        df_notes_pivot = df_notifications.pivot_table(
            index='timestampUtc',
            columns='dataFieldName',
            values='value',
            aggfunc='first' # Take the first if duplicates exist
        )
        print(f"Saving notifications to {notifications_output_path}...")
        try:
            df_notes_pivot.to_csv(notifications_output_path)
        except PermissionError:
            print(f"Error: Could not write to {notifications_output_path}. Is it open?")

    print("Pivoting main data...")
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
        'chargingState',
        'inspectionDueDays',
        'batteryCareMode',
        'plugConnectionState',
        'externalPower'
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
        'temperatureOutsideVehicle',
        'inspectionDueDays'
    ]

    for col in numeric_cols:
        if col in df_pivot.columns:
            df_pivot[col] = pd.to_numeric(df_pivot[col], errors='coerce')

    # Fix Temperature (Kelvin to Celsius)
    if 'temperatureOutsideVehicle' in df_pivot.columns:
        # Check if values look like Kelvin (> 200)
        # Using 200 as a safe threshold (200K = -73C, unlikely on Earth in a car)
        if df_pivot['temperatureOutsideVehicle'].mean() > 200:
            print("Converting Temperature from Kelvin to Celsius...")
            df_pivot['temperatureOutsideVehicle'] = df_pivot['temperatureOutsideVehicle'] - 273.15

    # Sort by time
    df_pivot = df_pivot.sort_index()

    # Forward fill to create a continuous state
    df_filled = df_pivot.ffill()

    # --- Detailed Analysis (Trips & Charges) ---
    print("Analyzing Trips and Charging Sessions...")
    df_trips, df_charges = calculate_consumption_and_charges(df_filled)

    if df_trips is not None and not df_trips.empty:
        print(f"Found {len(df_trips)} trips. Saving to {trips_output_path}...")
        try:
            df_trips.to_csv(trips_output_path, index=False)
        except PermissionError:
             print(f"Error: Could not write to {trips_output_path}. Is it open?")

    if df_charges is not None and not df_charges.empty:
        print(f"Found {len(df_charges)} charging sessions. Saving to {charges_output_path}...")
        try:
            df_charges.to_csv(charges_output_path, index=False)
        except PermissionError:
             print(f"Error: Could not write to {charges_output_path}. Is it open?")


    print(f"Saving processed data to {output_path}...")
    try:
        df_filled.to_csv(output_path)
        print("Done.")
    except PermissionError:
        print(f"Error: Permission denied when writing to '{output_path}'.")
        print("Please close any applications (like Excel or the running Streamlit dashboard) that might have this file open.")

if __name__ == "__main__":
    load_and_process_data("processed_data.csv", "notifications.csv", "trips.csv", "charges.csv")
