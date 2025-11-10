# plugins/weather_etl.py
"""
Weather ETL Functions
Contains all the extraction, transformation, and loading logic
"""

import requests
import json
import snowflake.connector
from datetime import datetime
from config.snowflake_config import SNOWFLAKE_CONFIG
from config.api_config import WEATHER_API_KEY, WEATHER_API_URL


def fetch_weather_data(location):
    """
    Fetch weather data from Tomorrow.io API
    
    Args:
        location: Location string for weather data (e.g., "New York", "40.7128,-74.0060")
    
    Returns:
        tuple: (weather_data, location) or (None, None) if error
    """
    params = {
        "location": location,
        "apikey": WEATHER_API_KEY
    }
    
    headers = {
        "accept": "application/json",
        "accept-encoding": "deflate, gzip, br"
    }
    
    try:
        response = requests.get(WEATHER_API_URL, headers=headers, params=params)
        
        if response.status_code == 200:
            data = response.json()
            
            # Get the first minutely data point
            if "timelines" in data and "minutely" in data["timelines"]:
                if len(data["timelines"]["minutely"]) > 0:
                    return data["timelines"]["minutely"][0], location
            
            print(f"No minutely data available for {location}")
            return None, None
        else:
            print(f"API Error for {location}: {response.status_code}")
            print(response.text[:500])
            return None, None
            
    except Exception as e:
        print(f"Error fetching weather data for {location}: {e}")
        raise


def insert_weather_to_snowflake(weather_data, location):
    """
    Insert weather data into Snowflake table
    
    Args:
        weather_data: Weather data dictionary from API
        location: Location string
    """
    if not weather_data:
        print("No data to insert")
        return False
    
    print(f"Connecting to Snowflake...")
    
    # Connect to Snowflake
    conn = snowflake.connector.connect(**SNOWFLAKE_CONFIG)
    cursor = conn.cursor()
    
    try:
        # Use the staging schema
        cursor.execute("USE SCHEMA STAGING")
        
        # Prepare insert query - LOCATION is wrapped in quotes as it's a reserved word
        insert_query = """
            INSERT INTO weather_data (
                "LOCATION",
                observation_time,
                altimeter_setting,
                cloud_base,
                cloud_ceiling,
                cloud_cover,
                dew_point,
                evapotranspiration,
                freezing_rain_intensity,
                humidity,
                ice_accumulation,
                ice_accumulation_lwe,
                precipitation_probability,
                pressure_sea_level,
                pressure_surface_level,
                rain_accumulation,
                rain_intensity,
                sleet_accumulation,
                sleet_accumulation_lwe,
                sleet_intensity,
                snow_accumulation,
                snow_accumulation_lwe,
                snow_depth,
                snow_intensity,
                temperature,
                temperature_apparent,
                uv_health_concern,
                uv_index,
                visibility,
                weather_code,
                wind_direction,
                wind_gust,
                wind_speed
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
            )
        """
        
        # Extract values from the weather data
        values = weather_data.get('values', {})
        
        # Prepare data tuple for insertion
        record = (
            location,
            weather_data.get('time'),
            values.get('altimeterSetting'),
            values.get('cloudBase'),
            values.get('cloudCeiling'),
            values.get('cloudCover'),
            values.get('dewPoint'),
            values.get('evapotranspiration'),
            values.get('freezingRainIntensity'),
            values.get('humidity'),
            values.get('iceAccumulation'),
            values.get('iceAccumulationLwe'),
            values.get('precipitationProbability'),
            values.get('pressureSeaLevel'),
            values.get('pressureSurfaceLevel'),
            values.get('rainAccumulation'),
            values.get('rainIntensity'),
            values.get('sleetAccumulation'),
            values.get('sleetAccumulationLwe'),
            values.get('sleetIntensity'),
            values.get('snowAccumulation'),
            values.get('snowAccumulationLwe'),
            values.get('snowDepth'),
            values.get('snowIntensity'),
            values.get('temperature'),
            values.get('temperatureApparent'),
            values.get('uvHealthConcern'),
            values.get('uvIndex'),
            values.get('visibility'),
            values.get('weatherCode'),
            values.get('windDirection'),
            values.get('windGust'),
            values.get('windSpeed')
        )
        
        # Execute insert
        cursor.execute(insert_query, record)
        conn.commit()
        
        print(f"✅ Successfully loaded weather data for {location}")
        print(f"   Time: {weather_data.get('time')}")
        print(f"   Temperature: {values.get('temperature')}°C")
        print(f"   Humidity: {values.get('humidity')}%")
        print(f"   Wind Speed: {values.get('windSpeed')} m/s")
        
        # Verify the insertion
        cursor.execute('SELECT COUNT(*) FROM weather_data WHERE "LOCATION" = %s', (location,))
        count = cursor.fetchone()[0]
        print(f"   Total records for {location}: {count}")
        
        return True
        
    except Exception as e:
        print(f"❌ Error loading data to Snowflake: {e}")
        conn.rollback()
        raise
        
    finally:
        cursor.close()
        conn.close()
        print("Connection closed")


def test_snowflake_connection():
    """Test Snowflake connection and create table if needed"""
    print("Testing Snowflake connection...")
    
    try:
        conn = snowflake.connector.connect(**SNOWFLAKE_CONFIG)
        cursor = conn.cursor()
        cursor.execute("SELECT CURRENT_USER(), CURRENT_DATABASE(), CURRENT_SCHEMA()")
        result = cursor.fetchone()
        print(f"✅ Connected as: {result[0]}, Database: {result[1]}, Schema: {result[2]}")
        
        # Switch to STAGING schema
        cursor.execute("USE SCHEMA STAGING")
        
        # Try to check if table exists
        try:
            cursor.execute("SELECT COUNT(*) FROM weather_data")
            row_count = cursor.fetchone()[0]
            print(f"✅ Table 'weather_data' exists with {row_count} rows")
        except:
            print("⚠️  Table 'weather_data' does not exist yet. Creating it now...")
            
            # Create the table
            create_table_sql = """
            CREATE TABLE IF NOT EXISTS weather_data (
                id NUMBER AUTOINCREMENT PRIMARY KEY,
                "LOCATION" VARCHAR(255),
                load_timestamp TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
                observation_time TIMESTAMP_NTZ,
                altimeter_setting FLOAT,
                cloud_base FLOAT,
                cloud_ceiling FLOAT,
                cloud_cover INTEGER,
                dew_point FLOAT,
                evapotranspiration FLOAT,
                freezing_rain_intensity FLOAT,
                humidity INTEGER,
                ice_accumulation FLOAT,
                ice_accumulation_lwe FLOAT,
                precipitation_probability INTEGER,
                pressure_sea_level FLOAT,
                pressure_surface_level FLOAT,
                rain_accumulation FLOAT,
                rain_intensity FLOAT,
                sleet_accumulation FLOAT,
                sleet_accumulation_lwe FLOAT,
                sleet_intensity FLOAT,
                snow_accumulation FLOAT,
                snow_accumulation_lwe FLOAT,
                snow_depth FLOAT,
                snow_intensity FLOAT,
                temperature FLOAT,
                temperature_apparent FLOAT,
                uv_health_concern INTEGER,
                uv_index INTEGER,
                visibility FLOAT,
                weather_code INTEGER,
                wind_direction INTEGER,
                wind_gust FLOAT,
                wind_speed FLOAT
            )
            """
            
            cursor.execute(create_table_sql)
            print("✅ Table 'weather_data' created successfully")
        
        cursor.close()
        conn.close()
        return True
        
    except Exception as e:
        print(f"❌ Failed: {e}")
        raise


def fetch_and_load_weather(location):
    """
    Combined function to fetch and load weather data for a single location
    Used by Airflow tasks
    
    Args:
        location: Location string
    """
    print(f"\n{'='*50}")
    print(f"Processing: {location}")
    print('='*50)
    
    weather_data, loc = fetch_weather_data(location)
    
    if weather_data:
        insert_weather_to_snowflake(weather_data, loc)
        print(f"✅ Successfully processed {location}")
    else:
        print(f"❌ Failed to fetch data for {location}")
        raise Exception(f"No weather data available for {location}")


def generate_summary_report():
    """
    Generate a summary report of loaded weather data
    """
    print("\n" + "="*50)
    print("Generating Summary Report")
    print("="*50)
    
    try:
        conn = snowflake.connector.connect(**SNOWFLAKE_CONFIG)
        cursor = conn.cursor()
        cursor.execute("USE SCHEMA STAGING")
        
        # Get summary statistics
        query = """
        SELECT 
            "LOCATION",
            COUNT(*) as record_count,
            MAX(load_timestamp) as last_load,
            AVG(temperature) as avg_temp,
            AVG(humidity) as avg_humidity
        FROM weather_data
        GROUP BY "LOCATION"
        ORDER BY "LOCATION"
        """
        
        cursor.execute(query)
        results = cursor.fetchall()
        
        print("\nWeather Data Summary:")
        print("-" * 80)
        print(f"{'Location':<20} {'Records':<10} {'Last Load':<25} {'Avg Temp':<10} {'Avg Humidity'}")
        print("-" * 80)
        
        for row in results:
            location, count, last_load, avg_temp, avg_humidity = row
            print(f"{location:<20} {count:<10} {str(last_load):<25} {avg_temp:.1f}°C     {avg_humidity:.0f}%")
        
        print("-" * 80)
        print(f"✅ Summary report generated successfully")
        
        cursor.close()
        conn.close()
        
    except Exception as e:
        print(f"❌ Error generating summary report: {e}")
        raise
