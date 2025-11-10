"""
API Client for Aviation Edge
Handles all API interactions with Aviation Edge flight data service
"""

import requests
import json
from config.config import API_KEY, API_BASE_URL


def fetch_flights_from_aviation_edge(code="JFK", flight_type="departure", date_from="2025-09-24", date_to="2025-09-25"):
    """
    Fetch flight data from Aviation Edge API
    
    Args:
        code: Airport IATA code (e.g., 'JFK')
        flight_type: Type of flight - "departure" or "arrival"
        date_from: Start date (YYYY-MM-DD format)
        date_to: End date (YYYY-MM-DD format)
    
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
        
        # DEBUG: Print sample flight data to see structure
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