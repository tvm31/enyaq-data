import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import numpy as np

# Page configuration
st.set_page_config(
    page_title="Enyaq Data Dashboard",
    page_icon="🚗",
    layout="wide"
)

# Load data functions
@st.cache_data
def load_data():
    try:
        df = pd.read_csv("processed_data.csv", index_col='timestampUtc', parse_dates=True)
        return df
    except FileNotFoundError:
        st.error("processed_data.csv not found. Please run process_data.py first.")
        return pd.DataFrame()

@st.cache_data
def load_notifications():
    try:
        df = pd.read_csv("notifications.csv", index_col='timestampUtc', parse_dates=True)
        return df
    except FileNotFoundError:
        return pd.DataFrame()

@st.cache_data
def load_trips():
    try:
        df = pd.read_csv("trips.csv", parse_dates=['Start Time', 'End Time'])
        return df
    except FileNotFoundError:
        return pd.DataFrame()

@st.cache_data
def load_charges():
    try:
        df = pd.read_csv("charges.csv", parse_dates=['Start Time', 'End Time'])
        return df
    except FileNotFoundError:
        return pd.DataFrame()

df = load_data()
df_notif = load_notifications()
df_trips = load_trips()
df_charges = load_charges()

if df.empty:
    st.stop()

# Sidebar
st.sidebar.title("Filters")
min_date = df.index.min().date()
max_date = df.index.max().date()

start_date = st.sidebar.date_input("Start Date", min_date)
end_date = st.sidebar.date_input("End Date", max_date)

if start_date <= end_date:
    # Convert dates to strings for slicing to handle timezone aware index
    mask_start = str(start_date)
    mask_end = str(end_date)
    df_filtered = df.loc[mask_start:mask_end]

    if not df_notif.empty:
        df_notif_filtered = df_notif.loc[mask_start:mask_end]
    else:
        df_notif_filtered = pd.DataFrame()

    # Filter Trips
    if not df_trips.empty:
         # Trips starting within range
         mask_trips = (df_trips['Start Time'].dt.date >= start_date) & (df_trips['Start Time'].dt.date <= end_date)
         df_trips_filtered = df_trips[mask_trips]
    else:
         df_trips_filtered = pd.DataFrame()

    # Filter Charges
    if not df_charges.empty:
         mask_charges = (df_charges['Start Time'].dt.date >= start_date) & (df_charges['Start Time'].dt.date <= end_date)
         df_charges_filtered = df_charges[mask_charges]
    else:
         df_charges_filtered = pd.DataFrame()

else:
    st.error("Error: Start date must be before end date.")
    df_filtered = df
    df_notif_filtered = df_notif
    df_trips_filtered = df_trips
    df_charges_filtered = df_charges

# Main Layout
st.title("🚗 Skoda Enyaq Data Dashboard")

# KPI Metrics
col1, col2, col3, col4 = st.columns(4)

current_mileage = df_filtered['mileage'].max()
total_km_driven = df_filtered['mileage'].max() - df_filtered['mileage'].min()
avg_temp = df_filtered['temperatureOutsideVehicle'].mean()

# Calculate total energy charged in period
if not df_charges_filtered.empty:
    total_charged_kwh = df_charges_filtered['Energy Added (kWh)'].sum()
else:
    total_charged_kwh = 0

# Service KPI
if 'inspectionDueDays' in df_filtered.columns:
    days_to_service = df_filtered['inspectionDueDays'].iloc[-1]
    service_label = f"{days_to_service:.0f} Days" if pd.notna(days_to_service) else "Unknown"
else:
    service_label = "N/A"

col1.metric("Current Mileage", f"{current_mileage:,.0f} km")
col2.metric("Distance Driven", f"{total_km_driven:,.0f} km")
col3.metric("Charged Energy", f"{total_charged_kwh:.1f} kWh")
col4.metric("Next Inspection", service_label)

# Tabs
tab1, tab2, tab3, tab4, tab5 = st.tabs(["Trips (Logbook)", "Charging Analysis", "Battery & Usage", "Efficiency & Temp", "Logs"])

with tab1:
    st.header("Logbook (Kniha Jízd)")
    if not df_trips_filtered.empty:
        st.dataframe(
            df_trips_filtered.style.format({
                "Distance (km)": "{:.1f}",
                "Start SOC (%)": "{:.0f}",
                "End SOC (%)": "{:.0f}",
                "Energy Used (kWh)": "{:.1f}",
                "Consumption (kWh/100km)": "{:.1f}",
                "Avg Temp (°C)": "{:.1f}"
            }),
            use_container_width=True
        )

        # Monthly Stats
        st.subheader("Monthly Stats")
        df_trips_filtered['Month'] = df_trips_filtered['Start Time'].dt.to_period('M')
        monthly_stats = df_trips_filtered.groupby('Month').agg({
            'Distance (km)': 'sum',
            'Energy Used (kWh)': 'sum',
            'Avg Temp (°C)': 'mean'
        }).reset_index()
        monthly_stats['Avg Consumption (kWh/100km)'] = (monthly_stats['Energy Used (kWh)'] / monthly_stats['Distance (km)']) * 100
        monthly_stats['Month'] = monthly_stats['Month'].astype(str)

        fig_monthly = px.bar(monthly_stats, x='Month', y='Distance (km)', title="Monthly Distance Driven")
        st.plotly_chart(fig_monthly, use_container_width=True)

    else:
        st.info("No trips found in this period.")

with tab2:
    st.header("Charging Analysis")
    if not df_charges_filtered.empty:
        col_c1, col_c2 = st.columns(2)
        with col_c1:
            st.dataframe(
                df_charges_filtered[['Start Time', 'Duration (h)', 'Start SOC (%)', 'End SOC (%)', 'Energy Added (kWh)', 'Avg Power (kW)']],
                use_container_width=True
            )
        with col_c2:
            fig_charge_energy = px.bar(df_charges_filtered, x='Start Time', y='Energy Added (kWh)', title="Energy Added per Session")
            st.plotly_chart(fig_charge_energy, use_container_width=True)

        fig_charge_scatter = px.scatter(
            df_charges_filtered,
            x='Avg Power (kW)',
            y='Energy Added (kWh)',
            size='Duration (h)',
            color='Start SOC (%)',
            title="Charging Session Overview (Size = Duration)"
        )
        st.plotly_chart(fig_charge_scatter, use_container_width=True)

    else:
         st.info("No charging sessions found in this period.")

with tab3:
    st.header("Battery & Usage")

    # SOC Line Chart
    fig_soc = px.line(df_filtered, x=df_filtered.index, y="currentSOCInPct", title="SOC (%) Over Time")
    fig_soc.update_traces(line_color='#00CC96')
    st.plotly_chart(fig_soc, use_container_width=True)

    # Battery Care Mode
    if 'batteryCareMode' in df_filtered.columns:
        st.subheader("Battery Care Mode Usage")
        care_counts = df_filtered['batteryCareMode'].value_counts()
        fig_care = px.bar(x=care_counts.index, y=care_counts.values, title="Battery Care Mode Status Count", labels={'x': 'Status', 'y': 'Count'})
        st.plotly_chart(fig_care, use_container_width=True)

with tab4:
    st.header("Temperature & Efficiency")

    col_temp1, col_temp2 = st.columns(2)

    with col_temp1:
        st.subheader("Outside Temperature")
        fig_temp = px.line(df_filtered, x=df_filtered.index, y="temperatureOutsideVehicle", title="Outside Temperature (°C)")
        fig_temp.update_traces(line_color='#EF553B')
        st.plotly_chart(fig_temp, use_container_width=True)

    with col_temp2:
        st.subheader("Range vs. SOC")
        # Scatter plot to show correlation
        # Filter out 0 values for cleaner plot
        scatter_df = df_filtered[(df_filtered['cruisingRangeElectricInKm'] > 0) & (df_filtered['currentSOCInPct'] > 0)]

        fig_scatter = px.scatter(
            scatter_df,
            x="currentSOCInPct",
            y="cruisingRangeElectricInKm",
            color="temperatureOutsideVehicle",
            title="Estimated Range vs. SOC (colored by Temp °C)",
            labels={"currentSOCInPct": "SOC (%)", "cruisingRangeElectricInKm": "Range (km)", "temperatureOutsideVehicle": "Temp (°C)"}
        )
        st.plotly_chart(fig_scatter, use_container_width=True)

    # Consumption vs Temp (from Trips)
    if not df_trips_filtered.empty:
        st.subheader("Consumption vs. Temperature")
        fig_eff = px.scatter(
            df_trips_filtered,
            x='Avg Temp (°C)',
            y='Consumption (kWh/100km)',
            size='Distance (km)',
            title='Consumption vs. Avg Trip Temperature'
        )
        st.plotly_chart(fig_eff, use_container_width=True)

with tab5:
    st.header("Vehicle Logs & Notifications")
    if not df_notif_filtered.empty:
        # Sort by time desc
        df_notif_display = df_notif_filtered.sort_index(ascending=False)
        st.dataframe(df_notif_display, use_container_width=True)
    else:
        st.info("No notifications found for this period.")

st.markdown("---")
st.caption("Generated by Jules for Skoda Enyaq Data Analysis")
