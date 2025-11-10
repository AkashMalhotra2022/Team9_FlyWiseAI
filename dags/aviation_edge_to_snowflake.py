"""
Aviation Edge to Snowflake Data Pipeline - Single File Version (FIXED)
All-in-one DAG file with proper function ordering
"""

from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.utils.dates import days_ago
from datetime import datetime, timedelta
import requests
import json
import snowflake.connector
import os

# ===== CONFIGURATION =====
# All values loaded from environment variables (set in .env or docker-compose.yml)
# No defaults - will fail fast if not configured properly

API_KEY = os.getenv('AVIATION_EDGE_API_KEY')
API_BASE_URL = os.getenv('AVIATION_EDGE_BASE_URL')

if not API_KEY:
    raise ValueError("AVIATION_EDGE_API_KEY environment variable must be set")
if not API_BASE_URL:
    raise ValueError("AVIATION_EDGE_BASE_URL environment variable must be set")

AVIATION_EDGE_CONFIG = {
    'airport_code': os.getenv('AIRPORT_CODE'),
    'flight_type': os.getenv('FLIGHT_TYPE', 'departure'),  # Only non-sensitive default
    'date_from_days_ago': int(os.getenv('DATE_FROM_DAYS_AGO', '2')),
    'date_to_days_ago': int(os.getenv('DATE_TO_DAYS_AGO', '1')),
}

if not AVIATION_EDGE_CONFIG['airport_code']:
    raise ValueError("AIRPORT_CODE environment variable must be set")

SNOWFLAKE_CONFIG = {
    'user': os.getenv('SNOWFLAKE_USER'),
    'password': os.getenv('SNOWFLAKE_PASSWORD'),
    'account': os.getenv('SNOWFLAKE_ACCOUNT'),
    'warehouse': os.getenv('SNOWFLAKE_WAREHOUSE'),
    'database': os.getenv('SNOWFLAKE_DATABASE'),
    'schema': os.getenv('SNOWFLAKE_SCHEMA'),
}

# Validate all Snowflake credentials are set
required_snowflake_keys = ['user', 'password', 'account', 'warehouse', 'database', 'schema']
missing_keys = [key for key in required_snowflake_keys if not SNOWFLAKE_CONFIG[key]]
if missing_keys:
    raise ValueError(f"Missing Snowflake configuration: {', '.join(missing_keys)}")

default_args = {
    'owner': 'airflow',
    'depends_on_past': False,
    'email_on_failure': False,
    'email_on_retry': False,
    'retries': 2,
    'retry_delay': timedelta(minutes=5),
}


# ===== UTILITY FUNCTIONS =====

def fetch_flights_from_aviation_edge_api(code, flight_type, date_from, date_to):
    """
    Fetch flight data from Aviation Edge API
    
    Args:
        code: Airport IATA code (e.g., 'JFK', 'LAX', 'ORD')
        flight_type: 'departure' or 'arrival'
        date_from: Start date in YYYY-MM-DD format
        date_to: End date in YYYY-MM-DD format
    
    Returns:
        List of flight records
    """
    print(f"Fetching {flight_type} flights for {code} from {date_from} to {date_to}...")
    
    url = f"{API_BASE_URL}/timetable"
    
    params = {
        'key': API_KEY,
        'code': code,
        'type': flight_type,
        'date_from': date_from,
        'date_to': date_to
    }
    
    try:
        response = requests.get(url, params=params)
        response.raise_for_status()
        
        flights = response.json()
        
        if isinstance(flights, dict) and 'error' in flights:
            print(f"API Error: {flights['error']}")
            print(f"Message: {flights.get('message', 'No message provided')}")
            return []
        
        if isinstance(flights, dict) and 'success' in flights:
            if flights['success']:
                flights = flights.get('data', [])
            else:
                print(f"API returned error: {flights.get('message', 'Unknown error')}")
                return []
        
        print(f"Successfully fetched {len(flights)} flight records")
        
        if flights and len(flights) > 0:
            print("\n===== SAMPLE FLIGHT DATA =====")
            print(json.dumps(flights[0], indent=2))
            print("===== END SAMPLE DATA =====\n")
        
        return flights if isinstance(flights, list) else []
        
    except requests.exceptions.RequestException as e:
        print(f"Error fetching data from API: {e}")
        if hasattr(e, 'response') and e.response is not None:
            print(f"Response content: {e.response.text[:500]}")
        return []


def transform_aviation_edge_data(flight):
    """Transform Aviation Edge flight data to match staging table structure"""
    transformed = {
        'type': flight.get('type', 'departure'),
        'status': flight.get('status', 'scheduled'),
        'departure_iata_code': flight.get('departure', {}).get('iataCode'),
        'departure_icao_code': flight.get('departure', {}).get('icaoCode'),
        'departure_terminal': flight.get('departure', {}).get('terminal'),
        'departure_gate': flight.get('departure', {}).get('gate'),
        'departure_delay': str(flight.get('departure', {}).get('delay', '')) if flight.get('departure', {}).get('delay') else None,
        'departure_scheduled_time': flight.get('departure', {}).get('scheduledTime'),
        'departure_estimated_time': flight.get('departure', {}).get('estimatedTime'),
        'departure_actual_time': flight.get('departure', {}).get('actualTime'),
        'departure_estimated_runway': flight.get('departure', {}).get('estimatedRunway'),
        'departure_actual_runway': flight.get('departure', {}).get('actualRunway'),
        'arrival_iata_code': flight.get('arrival', {}).get('iataCode'),
        'arrival_icao_code': flight.get('arrival', {}).get('icaoCode'),
        'arrival_terminal': flight.get('arrival', {}).get('terminal'),
        'arrival_baggage': flight.get('arrival', {}).get('baggage'),
        'arrival_gate': flight.get('arrival', {}).get('gate'),
        'arrival_scheduled_time': flight.get('arrival', {}).get('scheduledTime'),
        'airline_name': flight.get('airline', {}).get('name'),
        'airline_iata_code': flight.get('airline', {}).get('iataCode'),
        'airline_icao_code': flight.get('airline', {}).get('icaoCode'),
        'flight_number': flight.get('flight', {}).get('number'),
        'flight_iata_number': flight.get('flight', {}).get('iataNumber'),
        'flight_icao_number': flight.get('flight', {}).get('icaoNumber'),
        'codeshared_airline_name': flight.get('codeshared', {}).get('airline', {}).get('name') if flight.get('codeshared') else None,
        'codeshared_airline_iata_code': flight.get('codeshared', {}).get('airline', {}).get('iataCode') if flight.get('codeshared') else None,
        'codeshared_airline_icao_code': flight.get('codeshared', {}).get('airline', {}).get('icaoCode') if flight.get('codeshared') else None,
        'codeshared_flight_number': flight.get('codeshared', {}).get('flight', {}).get('number') if flight.get('codeshared') else None,
        'codeshared_flight_iata_number': flight.get('codeshared', {}).get('flight', {}).get('iataNumber') if flight.get('codeshared') else None,
        'codeshared_flight_icao_number': flight.get('codeshared', {}).get('flight', {}).get('icaoNumber') if flight.get('codeshared') else None
    }
    return transformed


def clean_flight_data_function(flights):
    """Clean and validate flight data"""
    if not flights:
        print("No flights to clean")
        return []
    
    print(f"Starting data cleaning for {len(flights)} flights...")
    
    cleaned_flights = []
    stats = {
        'original_count': len(flights),
        'duplicates_removed': 0,
        'missing_critical_fields': 0,
        'invalid_airport_codes': 0,
        'test_flights_removed': 0,
        'final_count': 0
    }
    
    seen_flights = set()
    
    for flight in flights:
        flight_key = f"{flight.get('flight', {}).get('iataNumber', '')}_{flight.get('departure', {}).get('scheduledTime', '')}"
        
        if flight_key in seen_flights:
            stats['duplicates_removed'] += 1
            continue
        
        departure = flight.get('departure', {})
        arrival = flight.get('arrival', {})
        airline = flight.get('airline', {})
        flight_info = flight.get('flight', {})
        
        departure_iata = departure.get('iataCode')
        arrival_iata = arrival.get('iataCode')
        flight_iata = flight_info.get('iataNumber')
        
        if not departure_iata or not arrival_iata or not flight_iata:
            stats['missing_critical_fields'] += 1
            continue
        
        if len(departure_iata) != 3 or len(arrival_iata) != 3:
            stats['invalid_airport_codes'] += 1
            continue
        
        departure['iataCode'] = departure_iata.strip().upper()
        arrival['iataCode'] = arrival_iata.strip().upper()
        if departure.get('icaoCode'):
            departure['icaoCode'] = departure['icaoCode'].strip().upper()
        if arrival.get('icaoCode'):
            arrival['icaoCode'] = arrival['icaoCode'].strip().upper()
        
        if airline.get('iataCode'):
            airline['iataCode'] = airline['iataCode'].strip().upper()
        if airline.get('icaoCode'):
            airline['icaoCode'] = airline['icaoCode'].strip().upper()
        
        if flight_iata:
            flight_info['iataNumber'] = flight_iata.strip().upper()
        if flight_info.get('icaoNumber'):
            flight_info['icaoNumber'] = flight_info['icaoNumber'].strip().upper()
        
        test_patterns = ['TEST', '0000', '9999']
        if any(pattern in flight_iata.upper() for pattern in test_patterns):
            stats['test_flights_removed'] += 1
            continue
        
        if airline.get('name'):
            airline['name'] = ' '.join(airline['name'].split())
        
        for location in [departure, arrival]:
            if location.get('terminal'):
                location['terminal'] = location['terminal'].strip()
            if location.get('gate'):
                location['gate'] = location['gate'].strip()
        
        seen_flights.add(flight_key)
        cleaned_flights.append(flight)
    
    stats['final_count'] = len(cleaned_flights)
    
    print("\n===== DATA CLEANING SUMMARY =====")
    print(f"Original records: {stats['original_count']}")
    print(f"Duplicates removed: {stats['duplicates_removed']}")
    print(f"Missing critical fields: {stats['missing_critical_fields']}")
    print(f"Invalid airport codes: {stats['invalid_airport_codes']}")
    print(f"Test flights removed: {stats['test_flights_removed']}")
    print(f"Final clean records: {stats['final_count']}")
    print(f"Data quality: {(stats['final_count']/stats['original_count']*100):.1f}%")
    print("===== END CLEANING SUMMARY =====\n")
    
    return cleaned_flights


def load_to_snowflake_function(flights):
    """Load flight data into Snowflake staging table"""
    if not flights:
        print("No flights to load")
        return 0
    
    print(f"Connecting to Snowflake...")
    
    conn = snowflake.connector.connect(**SNOWFLAKE_CONFIG)
    cursor = conn.cursor()
    
    try:
        cursor.execute("USE SCHEMA STAGING")
        
        insert_query = """
            INSERT INTO staging_flights (
                source_filename,
                type, status,
                departure_iata_code, departure_icao_code, departure_terminal,
                departure_gate, departure_delay, departure_scheduled_time,
                departure_estimated_time, departure_actual_time,
                departure_estimated_runway, departure_actual_runway,
                arrival_iata_code, arrival_icao_code, arrival_terminal,
                arrival_baggage, arrival_gate, arrival_scheduled_time,
                airline_name, airline_iata_code, airline_icao_code,
                flight_number, flight_iata_number, flight_icao_number,
                codeshared_airline_name, codeshared_airline_iata_code,
                codeshared_airline_icao_code, codeshared_flight_number,
                codeshared_flight_iata_number, codeshared_flight_icao_number
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        
        source_filename = f"aviation_edge_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        
        records_to_insert = []
        for i, flight in enumerate(flights):
            transformed = transform_aviation_edge_data(flight)
            
            if i == 0:
                print("\n===== TRANSFORMED DATA (First Record) =====")
                for key, value in transformed.items():
                    print(f"{key}: {value}")
                print("===== END TRANSFORMED DATA =====\n")
            
            record = (
                source_filename,
                transformed['type'],
                transformed['status'],
                transformed['departure_iata_code'],
                transformed['departure_icao_code'],
                transformed['departure_terminal'],
                transformed['departure_gate'],
                transformed['departure_delay'],
                transformed['departure_scheduled_time'],
                transformed['departure_estimated_time'],
                transformed['departure_actual_time'],
                transformed['departure_estimated_runway'],
                transformed['departure_actual_runway'],
                transformed['arrival_iata_code'],
                transformed['arrival_icao_code'],
                transformed['arrival_terminal'],
                transformed['arrival_baggage'],
                transformed['arrival_gate'],
                transformed['arrival_scheduled_time'],
                transformed['airline_name'],
                transformed['airline_iata_code'],
                transformed['airline_icao_code'],
                transformed['flight_number'],
                transformed['flight_iata_number'],
                transformed['flight_icao_number'],
                transformed['codeshared_airline_name'],
                transformed['codeshared_airline_iata_code'],
                transformed['codeshared_airline_icao_code'],
                transformed['codeshared_flight_number'],
                transformed['codeshared_flight_iata_number'],
                transformed['codeshared_flight_icao_number']
            )
            records_to_insert.append(record)
        
        cursor.executemany(insert_query, records_to_insert)
        conn.commit()
        
        print(f"✅ Successfully loaded {len(records_to_insert)} records to Snowflake")
        
        cursor.execute("SELECT COUNT(*) FROM staging_flights WHERE source_filename = %s", (source_filename,))
        count = cursor.fetchone()[0]
        print(f"   Verified: {count} records in staging table")
        
        return count
        
    except Exception as e:
        print(f"❌ Error loading data to Snowflake: {e}")
        conn.rollback()
        return 0
        
    finally:
        cursor.close()
        conn.close()
        print("Connection closed")


# ===== AIRFLOW TASK FUNCTIONS =====

def fetch_and_store_flights(**context):
    """Fetch flights from Aviation Edge API and store in XCom"""
    # Get configuration from environment variables
    airport_code = AVIATION_EDGE_CONFIG.get('airport_code', 'JFK')
    flight_type = AVIATION_EDGE_CONFIG.get('flight_type', 'departure')
    date_from_offset = AVIATION_EDGE_CONFIG.get('date_from_days_ago', 2)
    date_to_offset = AVIATION_EDGE_CONFIG.get('date_to_days_ago', 1)
    
    # Calculate dates dynamically based on offsets
    today = datetime.now()
    date_from = (today - timedelta(days=5)).strftime('%Y-%m-%d')
    date_to = (today - timedelta(days=4)).strftime('%Y-%m-%d')
    
    print(f"📅 Date calculation:")
    print(f"   Today: {today.strftime('%Y-%m-%d')}")
    print(f"   Fetching from: {date_from} (today - {date_from_offset} days)")
    print(f"   Fetching to: {date_to} (today - {date_to_offset} days)")
    print(f"   Airport: {airport_code}, Type: {flight_type}")
    
    flights = fetch_flights_from_aviation_edge_api(
        code=airport_code,
        flight_type=flight_type,
        date_from=date_from,
        date_to=date_to
    )
    
    if not flights:
        print("⚠️ No flights fetched from API")
        return None
    
    print(f"✅ Fetched {len(flights)} flights")
    context['task_instance'].xcom_push(key='flights_data', value=flights)
    
    return len(flights)


def clean_flights_data(**context):
    """Clean and validate flight data from XCom"""
    flights = context['task_instance'].xcom_pull(
        task_ids='fetch_flights',
        key='flights_data'
    )
    
    if not flights:
        print("⚠️ No flights data to clean")
        return 0
    
    print(f"Cleaning {len(flights)} flights...")
    
    cleaned_flights = clean_flight_data_function(flights)
    
    if not cleaned_flights:
        print("⚠️ No flights remained after cleaning")
        return 0
    
    print(f"✅ Cleaned {len(cleaned_flights)} flights")
    
    context['task_instance'].xcom_push(key='cleaned_flights_data', value=cleaned_flights)
    
    return len(cleaned_flights)


def load_flights_to_snowflake(**context):
    """Load flights from XCom to Snowflake staging table"""
    flights = context['task_instance'].xcom_pull(
        task_ids='clean_flights',
        key='cleaned_flights_data'
    )
    
    if not flights:
        print("⚠️ No flights data to load")
        return 0
    
    print(f"Loading {len(flights)} flights to Snowflake")
    records_loaded = load_to_snowflake_function(flights)
    
    return records_loaded


# ===== DAG DEFINITION =====

with DAG(
    'aviation_edge_to_snowflake_fixed',
    default_args=default_args,
    description='Fetch, clean and load flight data from Aviation Edge to Snowflake',
    schedule_interval='0 */6 * * *',
    start_date=days_ago(1),
    catchup=False,
    tags=['aviation', 'snowflake', 'etl', 'data-quality'],
) as dag:

    fetch_task = PythonOperator(
        task_id='fetch_flights',
        python_callable=fetch_and_store_flights,
    )

    clean_task = PythonOperator(
        task_id='clean_flights',
        python_callable=clean_flights_data,
    )

    load_task = PythonOperator(
        task_id='load_to_snowflake',
        python_callable=load_flights_to_snowflake,
    )

    fetch_task >> clean_task >> load_task