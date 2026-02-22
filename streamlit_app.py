#!/usr/bin/env python3
"""
Streamlit app for Road Segments Data Processing Pipeline.
Downloads data from Redash API and processes it to generate reports.
"""

import streamlit as st
import requests
import json
import pandas as pd
import os
import shutil
import zipfile
import io
from pathlib import Path
from datetime import datetime

# Page configuration
st.set_page_config(
    page_title="Road Segments Report",
    page_icon="🛣️",
    layout="wide"
)

# Get URLs from environment variables
ROAD_SEGMENTS_URL = os.getenv("ROAD_SEGMENTS_URL", "")
INFOGRAPHICS_URL = os.getenv("INFOGRAPHICS_URL", "")

# Directory configuration
SCRIPT_DIR = Path(__file__).parent
DATA_DIR = SCRIPT_DIR / "data"
SOURCE_DATA_DIR = DATA_DIR / "source_data"
OUTPUT_DATA_DIR = DATA_DIR / "output_data"

# Create directories if they don't exist
SOURCE_DATA_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DATA_DIR.mkdir(parents=True, exist_ok=True)

ROAD_SEGMENTS_CSV = SOURCE_DATA_DIR / "road_segments.csv"
INFOGRAPHICS_CSV = SOURCE_DATA_DIR / "infographics_data_cache_5_years.csv"


def custom_parser(data):
    """Parse JSON string data."""
    return json.loads(data)


def download_and_save_csv(url, output_file, api_name, progress_bar=None):
    """Download JSON from Redash API and save as CSV."""
    metadata = {}
    
    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        data = response.json()
        
        # Extract data from query_result -> data -> rows
        if 'query_result' in data and 'data' in data['query_result'] and 'rows' in data['query_result']['data']:
            rows = data['query_result']['data']['rows']
            
            # For infographics, extract metadata from first row before saving
            if 'infographics' in str(output_file).lower():
                metadata = json.loads(rows[0]['data']).get('meta')
            
            # Save only the rows without preserving nested JSON
            df = pd.DataFrame(rows)
            df.to_csv(output_file, index=False)
            
            if progress_bar:
                progress_bar.progress(50)
            
            return True, f"✓ {api_name}: {len(df)} rows, {len(df.columns)} columns", metadata
        else:
            return False, f"✗ Unexpected response structure", metadata
            
    except requests.exceptions.RequestException as e:
        return False, f"✗ Network error: {e}", metadata
    except Exception as e:
        return False, f"✗ Error: {e}", metadata


def process_data(progress_container, metadata):
    """Process the downloaded data and generate reports."""
    try:
        # Read data
        with progress_container.status("Processing data...", expanded=True) as status:
            status.write("Reading infographics data...")
            df = pd.read_csv(INFOGRAPHICS_CSV, converters={'data': custom_parser}, header=0)
            
            # Use passed metadata
            dates_comment = metadata.get('dates_comment', {})
            date_range = dates_comment.get('date_range', [])
            last_update = dates_comment.get('last_update', '')
            
            # Format last_update for display
            formatted_last_update = last_update
            if last_update:
                try:
                    date_obj = datetime.fromisoformat(last_update.replace('Z', '+00:00'))
                    formatted_last_update = date_obj.strftime('%d-%m-%Y')
                except:
                    pass
            
            status.write(f"✓ Meta info: date_range={date_range[0]}-{date_range[-1] if date_range else 'N/A'}, last_update={formatted_last_update}")
            
            status.write("Reading road segments...")
            road_segments = pd.read_csv(ROAD_SEGMENTS_CSV)
            
            # Extract segment data from JSON
            status.write("Extracting segment data...")
            all_list = []
            for i, row in df.iterrows():
                j = {
                    'road_segment_id': df["data"][i]['meta']['location_info']['road_segment_id'],
                    'road_segment_name': df["data"][i]['meta']['location_info']['road_segment_name']
                } | dict([w['data']['items'] for w in df["data"][i]['widgets'] 
                    if w['name'] == 'accident_count_by_severity'][0]) | dict([w['data']['items'] 
                    for w in df["data"][i]['widgets'] if w['name'] == 'injured_count_by_severity'][0])
                all_list.append(j)
            
            # Create DataFrame and merge
            status.write("Creating segments DataFrame...")
            df_total = pd.DataFrame(all_list)
            
            status.write("Merging with road segments data...")
            df_total = pd.merge(
                left=df_total,
                right=road_segments[['segment_id', 'road', 'from_km', 'from_name', 'to_km', 'to_name']],
                left_on='road_segment_id',
                right_on='segment_id'
            )
            
            # Calculate metrics
            status.write("Calculating metrics...")
            df_total['total_km'] = df_total['to_km'] - df_total['from_km']
            df_total['fatal_severe_accidents'] = df_total['severity_fatal_count'] + df_total['severity_severe_count']
            df_total['fatal_severe_accidents_per_km'] = df_total['fatal_severe_accidents'] / df_total['total_km']
            df_total['fatal_accidents_per_km'] = df_total['severity_fatal_count'] / df_total['total_km']
            
            # Sort and select columns
            df_total.sort_values('fatal_severe_accidents_per_km', inplace=True, ascending=False)
            
            segment_columns = [
                'road_segment_id', 'road', 'road_segment_name', 'from_km', 'from_name', 'to_km', 'to_name',
                'total_km', 'severity_fatal_count', 'severity_severe_count', 'severity_light_count', 
                'start_year', 'end_year', 'total_accidents_count', 'killed_count', 'severe_injured_count', 
                'light_injured_count', 'total_injured_count', 'segment_id', 'fatal_severe_accidents', 
                'fatal_severe_accidents_per_km', 'fatal_accidents_per_km'
            ]
            df_total = df_total[[col for col in segment_columns if col in df_total.columns]]
            
            # Save segment files
            status.write("Saving segment reports...")
            df_total.to_csv(OUTPUT_DATA_DIR / 'all_segments.csv', index=False)
            
            df_total_over_km = df_total.loc[df_total['total_km'] >= 1]
            df_total_over_km.to_csv(OUTPUT_DATA_DIR / 'all_segments_1_km_and_above.csv', index=False)
            
            # Generate road-level report
            status.write("Generating road-level report...")
            agg_columns = [
                'total_km', 'severity_fatal_count', 'severity_severe_count', 'severity_light_count',
                'total_accidents_count', 'killed_count', 'severe_injured_count', 'light_injured_count',
                'total_injured_count'
            ]
            agg_columns = [col for col in agg_columns if col in df_total.columns]
            
            df_roads = df_total.groupby(['road']).sum()[agg_columns]
            
            first_junction = df_total.sort_values('from_km').groupby(['road'])['from_name'].first().to_frame()
            last_junction = df_total.sort_values('to_km').groupby(['road'])['to_name'].last().to_frame()
            
            df_roads = pd.merge(df_roads, first_junction, left_index=True, right_index=True)
            df_roads = pd.merge(df_roads, last_junction, left_index=True, right_index=True)
            
            df_roads['fatal_severe_accidents'] = df_roads['severity_fatal_count'] + df_roads['severity_severe_count']
            df_roads['fatal_severe_accidents_per_km'] = df_roads['fatal_severe_accidents'] / df_roads['total_km']
            df_roads['fatal_accidents_per_km'] = df_roads['severity_fatal_count'] / df_roads['total_km']
            
            df_roads.sort_values('fatal_severe_accidents_per_km', inplace=True, ascending=False)
            df_roads.reset_index(inplace=True)
            
            # Save road files
            status.write("Saving road reports...")
            df_roads.to_csv(OUTPUT_DATA_DIR / 'all_roads.csv', index=False)
            
            df_roads_over_km = df_roads.loc[df_roads['total_km'] >= 1]
            df_roads_over_km.to_csv(OUTPUT_DATA_DIR / 'all_roads_1_km_and_above.csv', index=False)
            
            status.write(f"✓ Processing complete! Total segments: {len(df_total)}, Total roads: {len(df_roads)}")
            status.update(label="✓ Processing complete!", state="complete")
        
        return True, len(df_total), len(df_total_over_km), len(df_roads), len(df_roads_over_km), date_range, last_update
        
    except Exception as e:
        return False, str(e), None, None, None, None, None


def create_download_zip():
    """Create a zip file of the data directory."""
    import io
    zip_buffer = io.BytesIO()
    
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, dirs, files in os.walk(DATA_DIR):
            for file in files:
                file_path = Path(root) / file
                arcname = file_path.relative_to(SCRIPT_DIR)
                zipf.write(file_path, arcname)
    
    zip_buffer.seek(0)
    return zip_buffer


# Main UI
st.title("🛣️ Road Segments Report Generator")

st.markdown("""
This app processes road safety data from Redash API and generates comprehensive reports
on accidents and injuries by road segments and roads.
""")

# Check environment variables
if not ROAD_SEGMENTS_URL or not INFOGRAPHICS_URL:
    st.error("❌ Missing environment variables!")
    st.info("""
    Please set the following environment variables:
    - `ROAD_SEGMENTS_URL`
    - `INFOGRAPHICS_URL`
    
    Example:
    ```bash
    export ROAD_SEGMENTS_URL="https://..."
    export INFOGRAPHICS_URL="https://..."
    streamlit run app.py
    ```
    """)
    st.stop()

# Auto-run processing on every page load
with st.spinner("⏳ Downloading and processing data..."):
    progress_container = st.container()
    
    # Download files
    with progress_container.status("Downloading data from Redash...", expanded=True) as status:
        status.write("Downloading road segments...")
        success1, msg1, _ = download_and_save_csv(ROAD_SEGMENTS_URL, ROAD_SEGMENTS_CSV, "road_segments.csv")
        st.write(msg1)
        
        status.write("Downloading infographics data...")
        success2, msg2, metadata = download_and_save_csv(INFOGRAPHICS_URL, INFOGRAPHICS_CSV, "infographics_data_cache_5_years.csv")
        st.write(msg2)
        
        if success1 and success2:
            status.update(label="✓ Download complete!", state="complete")
        else:
            status.update(label="✗ Download failed!", state="error")
            st.stop()
    
    # Process data
    progress_container2 = st.container()
    success, segments, segments_1km, roads, roads_1km, date_range, last_update = process_data(progress_container2, metadata)
    
    if success:
        # Show statistics
        st.success("✓ Processing completed successfully!")
        
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Total Segments", segments)
        with col2:
            st.metric("Segments ≥ 1 km", segments_1km)
        with col3:
            st.metric("Total Roads", roads)
        with col4:
            st.metric("Roads ≥ 1 km", roads_1km)
        
        # Download button at the top
        st.divider()
        col1, col2, col3 = st.columns([1, 2, 1])
        with col1:
            # Format filename with data range and last update
            filename_suffix = ""
            if date_range and len(date_range) >= 2:
                filename_suffix += f"_{date_range[0]}-{date_range[-1]}"
            if last_update:
                try:
                    date_obj = datetime.fromisoformat(last_update.replace('Z', '+00:00'))
                    formatted_date = date_obj.strftime('%d-%m-%Y')
                    filename_suffix += f"_{formatted_date}"
                except:
                    pass
            
            zip_buffer = create_download_zip()
            st.download_button(
                label="📥 Download Data ZIP",
                data=zip_buffer,
                file_name=f"road_segments_data{filename_suffix}.zip",
                mime="application/zip",
                use_container_width=True
            )
        
        # Display meta information
        st.divider()
        meta_col1, meta_col2 = st.columns(2)
        with meta_col1:
            if date_range and isinstance(date_range, list) and len(date_range) >= 2:
                st.info(f"📅 **Data Range:** {date_range[0]} - {date_range[-1]}")
            else:
                st.warning("📅 Data Range: Not available")
        with meta_col2:
            if last_update:
                try:
                    date_obj = datetime.fromisoformat(last_update.replace('Z', '+00:00'))
                    formatted_date = date_obj.strftime('%d-%m-%Y')
                    st.info(f"🔄 **Last Updated:** {formatted_date}")
                except Exception as e:
                    st.warning(f"🔄 Last Updated: {last_update}")
            else:
                st.warning("🔄 Last Updated: Not available")
    else:
        st.error(f"✗ Processing failed: {segments}")
        st.stop()

# Show available files
st.divider()
st.subheader("📂 Available Files")

col1, col2 = st.columns(2)

with col1:
    st.write("**Source Data** (data/source_data/)")
    if SOURCE_DATA_DIR.exists():
        source_files = list(SOURCE_DATA_DIR.glob("*.csv"))
        if source_files:
            for f in source_files:
                st.write(f"- {f.name}")
        else:
            st.write("*No files yet*")

with col2:
    st.write("**Output Data** (data/output_data/)")
    if OUTPUT_DATA_DIR.exists():
        output_files = list(OUTPUT_DATA_DIR.glob("*.csv"))
        if output_files:
            for f in output_files:
                size_mb = f.stat().st_size / (1024 * 1024)
                st.write(f"- {f.name} ({size_mb:.2f} MB)")
        else:
            st.write("*No files yet*")

# Preview output
if (OUTPUT_DATA_DIR / 'all_segments.csv').exists():
    st.divider()
    st.subheader("📊 Data Preview")
    
    tab1, tab2 = st.tabs(["Segments", "Roads"])
    
    with tab1:
        try:
            df_segments = pd.read_csv(OUTPUT_DATA_DIR / 'all_segments.csv')
            df_segments = df_segments.sort_values('fatal_severe_accidents_per_km', ascending=False).reset_index(drop=True)
            st.write(f"**All Segments** ({len(df_segments)} rows)")
            
            # Reorder columns to put key info first
            key_cols = ['road', 'road_segment_name', 'total_km', 'fatal_severe_accidents_per_km', 'fatal_accidents_per_km']
            other_cols = [col for col in df_segments.columns if col not in key_cols]
            df_display = df_segments[key_cols + other_cols]
            
            st.dataframe(df_display, use_container_width=True, hide_index=False)
        except Exception as e:
            st.error(f"Error loading segments: {e}")
    
    with tab2:
        try:
            df_roads = pd.read_csv(OUTPUT_DATA_DIR / 'all_roads.csv')
            df_roads = df_roads.sort_values('fatal_severe_accidents_per_km', ascending=False).reset_index(drop=True)
            st.write(f"**All Roads** ({len(df_roads)} rows)")
            
            # Reorder columns to put key info first
            key_cols = ['road', 'from_name', 'to_name', 'total_km', 'fatal_severe_accidents_per_km', 'fatal_accidents_per_km']
            other_cols = [col for col in df_roads.columns if col not in key_cols]
            df_display = df_roads[key_cols + other_cols]
            
            st.dataframe(df_display, use_container_width=True, hide_index=False)
        except Exception as e:
            st.error(f"Error loading roads: {e}")
