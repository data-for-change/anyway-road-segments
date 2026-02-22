# 🛣️ Road Segments Report Generator

A Streamlit web app that downloads road safety data from Redash API and generates comprehensive reports on accidents and injuries by road segments and roads.

## Features

- **Automatic Data Download** - Fetches data from Redash API endpoints
- **Data Processing** - Extracts, merges, and calculates safety metrics
- **Real-time Reports** - Generates segment-level and road-level accident reports
- **Interactive Dashboard** - View statistics, data range, and last update
- **Data Preview** - Browse processed data with sortable tables
- **Download Reports** - Export all processed data as ZIP file with metadata in filename

## Generated Reports

- `all_segments.csv` - All road segments with safety metrics
- `all_segments_1_km_and_above.csv` - Segments ≥ 1 km
- `all_roads.csv` - Aggregated data by road
- `all_roads_1_km_and_above.csv` - Roads ≥ 1 km

## Metrics Included

- Total/Fatal/Severe/Light accident counts
- Injuries by severity level
- Safety rates (accidents per km)
- Segment coordinates and locations

## Prerequisites

- Python 3.8+
- pip or conda

## Installation & Setup

### 1. Install Dependencies

```bash
pip install streamlit requests pandas python-dotenv
```

### 2. Configure API Keys

Create a `.env` file (or set environment variables):

```bash
export ROAD_SEGMENTS_URL=""
export INFOGRAPHICS_URL=""
```

Or copy and edit `.env.example`:

```bash
cp .env.example .env
```

### 3. Run the App

```bash
streamlit run app.py
```

The app opens at `http://localhost:8501`

## Directory Structure

```
2026/
├── app.py                    # Main Streamlit app
├── README.md                 # This file
├── .env.example              # Environment variables template
└── data/
    ├── source_data/          # Downloaded raw data
    └── output_data/          # Generated reports
```

## Usage

1. **Start the app** - Streamlit runs automatically on every page load
2. **Download & Process** - Data downloads and processing happens automatically
3. **View Statistics** - See segment/road counts and data range at the top
4. **Download Reports** - Click download button to get all data as ZIP
5. **Browse Data** - Use tabs to view segments or roads with key metrics visible first

This downloads data and processes it without a web interface.

## API Endpoints

- Road segments data
- Infographics data (accident/injury statistics)

Both return JSON with structure: `query_result → data → rows`

## Data Flow

1. Download raw data from Redash API
2. Extract accident/injury metrics from JSON
3. Merge with road segment information
4. Calculate safety metrics (accidents per km, etc.)
5. Generate segment and road-level aggregations
6. Save to CSV files in `data/output_data/`
7. Display in interactive Streamlit dashboard

## Troubleshooting

**Missing environment variables:**
- Ensure `ROAD_SEGMENTS_URL` and `INFOGRAPHICS_URL` are set
- Check `.env` file is in the same directory as `app.py`

