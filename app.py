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
        return pd.DataFrame() # Return empty if not found

df = load_data()
df_notif = load_notifications()

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
else:
    st.error("Error: Start date must be before end date.")
    df_filtered = df
    df_notif_filtered = df_notif

# Main Layout
st.title("🚗 Skoda Enyaq Data Dashboard")

# KPI Metrics
col1, col2, col3, col4 = st.columns(4)

current_mileage = df_filtered['mileage'].max()
total_km_driven = df_filtered['mileage'].max() - df_filtered['mileage'].min()
avg_temp = df_filtered['temperatureOutsideVehicle'].mean()
avg_soc = df_filtered['currentSOCInPct'].mean()

# Service KPI
if 'inspectionDueDays' in df_filtered.columns:
    days_to_service = df_filtered['inspectionDueDays'].iloc[-1]
    service_label = f"{days_to_service:.0f} Days" if pd.notna(days_to_service) else "Unknown"
else:
    service_label = "N/A"

col1.metric("Current Mileage", f"{current_mileage:,.0f} km")
col2.metric("Distance Driven (Period)", f"{total_km_driven:,.0f} km")
col3.metric("Avg Outside Temp", f"{avg_temp:.1f} °C")
col4.metric("Next Inspection In", service_label)

# Tabs for different analyses
tab1, tab2, tab3, tab4 = st.tabs(["Battery & Charging", "Driving & Usage", "Efficiency & Temperature", "Logs & Notifications"])

with tab1:
    st.header("Battery State of Charge (SOC)")

    # SOC Line Chart
    fig_soc = px.line(df_filtered, x=df_filtered.index, y="currentSOCInPct", title="SOC (%) Over Time")
    fig_soc.update_traces(line_color='#00CC96')
    st.plotly_chart(fig_soc, use_container_width=True)

    col_charge1, col_charge2 = st.columns(2)

    with col_charge1:
        st.subheader("Charging Power Distribution")
        # Filter where charging power is > 0
        charging_df = df_filtered[df_filtered['chargePowerInKW'] > 0]
        if not charging_df.empty:
            fig_power = px.histogram(charging_df, x="chargePowerInKW", nbins=50, title="Charging Power (kW)", color_discrete_sequence=['#636EFA'])
            st.plotly_chart(fig_power, use_container_width=True)
        else:
            st.info("No charging data available for this period.")

    with col_charge2:
         st.subheader("Charging Mode")
         if 'chargeMode' in df_filtered.columns:
             mode_counts = df_filtered['chargeMode'].value_counts()
             fig_mode = px.pie(names=mode_counts.index, values=mode_counts.values, title="Charging Modes")
             st.plotly_chart(fig_mode, use_container_width=True)

    # Battery Care Mode
    if 'batteryCareMode' in df_filtered.columns:
        st.subheader("Battery Care Mode Usage")
        care_counts = df_filtered['batteryCareMode'].value_counts()
        fig_care = px.bar(x=care_counts.index, y=care_counts.values, title="Battery Care Mode Status Count", labels={'x': 'Status', 'y': 'Count'})
        st.plotly_chart(fig_care, use_container_width=True)

with tab2:
    st.header("Mileage Analysis")

    # Calculate daily mileage on the FULL dataset to ensure the first day of the range has a diff
    full_daily_mileage = df['mileage'].resample('D').max().diff().fillna(0)

    # Filter for the selected date range
    daily_mileage = full_daily_mileage.loc[str(start_date):str(end_date)]

    # Filter out days with 0 or negative mileage (if any glitches)
    daily_mileage = daily_mileage[daily_mileage > 0]

    fig_daily = px.bar(daily_mileage, x=daily_mileage.index, y=daily_mileage.values, title="Daily Distance Driven (km)")
    fig_daily.update_layout(xaxis_title="Date", yaxis_title="Distance (km)")
    st.plotly_chart(fig_daily, use_container_width=True)

    st.subheader("Mileage Accumulation")
    fig_accum = px.area(df_filtered, x=df_filtered.index, y="mileage", title="Total Mileage Over Time")
    st.plotly_chart(fig_accum, use_container_width=True)

with tab3:
    st.header("Temperature & Efficiency")

    col_temp1, col_temp2 = st.columns(2)

    with col_temp1:
        st.subheader("Outside Temperature")
        # Temperature is now converted to Celsius in processed_data.csv
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

with tab4:
    st.header("Vehicle Logs & Notifications")
    if not df_notif_filtered.empty:
        # Sort by time desc
        df_notif_display = df_notif_filtered.sort_index(ascending=False)
        st.dataframe(df_notif_display, use_container_width=True)
    else:
        st.info("No notifications found for this period.")

st.markdown("---")
st.caption("Generated by Jules for Skoda Enyaq Data Analysis")
