"""
Snowflake Data Loader
Handles data transformation and loading to Snowflake staging tables
"""

import snowflake.connector
from datetime import datetime
from config.config import SNOWFLAKE_CONFIG


def transform_aviation_edge_data(flight):
    """
    Transform Aviation Edge flight data to match staging table structure
    
    Args:
        flight: Raw flight record from Aviation Edge
    
    Returns:
        Transformed record matching staging table columns
    """
    transformed = {
        'type': flight.get('type', 'departure'),
        'status': flight.get('status', 'scheduled'),
        
        # Departure information
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
        
        # Arrival information
        'arrival_iata_code': flight.get('arrival', {}).get('iataCode'),
        'arrival_icao_code': flight.get('arrival', {}).get('icaoCode'),
        'arrival_terminal': flight.get('arrival', {}).get('terminal'),
        'arrival_baggage': flight.get('arrival', {}).get('baggage'),
        'arrival_gate': flight.get('arrival', {}).get('gate'),
        'arrival_scheduled_time': flight.get('arrival', {}).get('scheduledTime'),
        
        # Airline information
        'airline_name': flight.get('airline', {}).get('name'),
        'airline_iata_code': flight.get('airline', {}).get('iataCode'),
        'airline_icao_code': flight.get('airline', {}).get('icaoCode'),
        
        # Flight information
        'flight_number': flight.get('flight', {}).get('number'),
        'flight_iata_number': flight.get('flight', {}).get('iataNumber'),
        'flight_icao_number': flight.get('flight', {}).get('icaoNumber'),
        
        # Codeshared information (if exists)
        'codeshared_airline_name': flight.get('codeshared', {}).get('airline', {}).get('name') if flight.get('codeshared') else None,
        'codeshared_airline_iata_code': flight.get('codeshared', {}).get('airline', {}).get('iataCode') if flight.get('codeshared') else None,
        'codeshared_airline_icao_code': flight.get('codeshared', {}).get('airline', {}).get('icaoCode') if flight.get('codeshared') else None,
        'codeshared_flight_number': flight.get('codeshared', {}).get('flight', {}).get('number') if flight.get('codeshared') else None,
        'codeshared_flight_iata_number': flight.get('codeshared', {}).get('flight', {}).get('iataNumber') if flight.get('codeshared') else None,
        'codeshared_flight_icao_number': flight.get('codeshared', {}).get('flight', {}).get('icaoNumber') if flight.get('codeshared') else None
    }
    return transformed


def load_to_snowflake(flights):
    """
    Load flight data into Snowflake staging table
    
    Args:
        flights: List of flight records from API
    
    Returns:
        Number of records loaded
    """
    if not flights:
        print("No flights to load")
        return 0
    
    print(f"Connecting to Snowflake...")
    
    # Connect to Snowflake
    conn = snowflake.connector.connect(**SNOWFLAKE_CONFIG)
    cursor = conn.cursor()
    
    try:
        # Use the staging schema
        cursor.execute("USE SCHEMA STAGING")
        
        # Prepare insert query - 31 columns, 31 values
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
        
        # Generate source filename
        source_filename = f"aviation_edge_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        
        # Transform and prepare data for insertion
        records_to_insert = []
        for i, flight in enumerate(flights):
            transformed = transform_aviation_edge_data(flight)
            
            # DEBUG: Print first transformed record to check data
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
        
        # Insert data in batches
        cursor.executemany(insert_query, records_to_insert)
        conn.commit()
        
        print(f"✅ Successfully loaded {len(records_to_insert)} records to Snowflake")
        
        # Verify the load
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