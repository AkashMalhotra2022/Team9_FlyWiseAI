# Stable code running till 11-12-2025  4:30 pm - 1904 lines


# ===== Flywise - Complete Application with Kiwi.com Integration =====
import streamlit as st
import pandas as pd
from datetime import datetime, date, timedelta
from snowflake.snowpark.context import get_active_session
import hashlib
import json
import requests
import math

st.set_page_config(
    page_title="Flywise",
    page_icon="✈️",
    layout="wide",
    initial_sidebar_state="expanded"
)

session = get_active_session()

# =====================================================================
#                       KIWI.COM API KEY CONFIGURATION
# =====================================================================
# PASTE YOUR KIWI.COM API KEY HERE (from the screenshot you just shared)
KIWI_API_KEY = ""  # ← PASTE YOUR API KEY HERE

# =====================================================================
#                       SIMPLE NEAR-ROUTE HEURISTIC
# =====================================================================

NEAR_CITY_PAIRS = {
    ("Boston", "New York"),
    ("New York", "Boston"),
    ("San Francisco", "Los Angeles"),
    ("Los Angeles", "San Francisco"),
    ("Seattle", "Portland"),
    ("Portland", "Seattle"),
}


def route_is_near(departure_city: str, arrival_city: str) -> bool:
    return (departure_city, arrival_city) in NEAR_CITY_PAIRS


# =====================================================================
#                     KIWI.COM API INTEGRATION
# =====================================================================

def search_kiwi_flights(dep_airport: str, arr_airport: str, departure_date_str: str, max_results: int = 5):
    """
    Search for flights using Kiwi.com Tequila API
    Returns real prices from 100+ booking platforms
    
    Args:
        dep_airport: IATA code (e.g., 'LAX')
        arr_airport: IATA code (e.g., 'DEN')
        departure_date_str: ISO format '2025-12-11' or timestamp
        max_results: Number of results to return
    
    Returns:
        List of flight dicts with real prices and direct booking links
    """
    
    if KIWI_API_KEY == "YOUR_API_KEY_HERE":
        return []
    
    try:
        # Parse date to DD/MM/YYYY format required by Kiwi
        if 'T' in departure_date_str:
            date_obj = datetime.fromisoformat(departure_date_str.split('T')[0])
        elif ' ' in departure_date_str:
            date_obj = datetime.strptime(departure_date_str.split(' ')[0], '%Y-%m-%d')
        else:
            date_obj = datetime.strptime(departure_date_str, '%Y-%m-%d')
        
        kiwi_date = date_obj.strftime('%d/%m/%Y')
        
        # Kiwi.com Search API endpoint
        url = "https://api.tequila.kiwi.com/v2/search"
        
        headers = {
            "apikey": KIWI_API_KEY,
            "accept": "application/json"
        }
        
        params = {
            "fly_from": dep_airport,
            "fly_to": arr_airport,
            "date_from": kiwi_date,
            "date_to": kiwi_date,
            "adults": 1,
            "limit": max_results,
            "curr": "USD",
            "sort": "price",
            "max_stopovers": 2,
            "flight_type": "oneway"
        }
        
        response = requests.get(url, headers=headers, params=params, timeout=15)
        
        if response.status_code == 401:
            st.error("❌ Invalid Kiwi.com API key. Please check your configuration.")
            return []
        elif response.status_code != 200:
            return []
        
        data = response.json()
        flights = []
        
        if not data.get('data'):
            return []
        
        for flight in data['data']:
            route = flight['route'][0]
            
            airlines = list(set(flight.get('airlines', [])))
            airline_name = airlines[0] if airlines else 'Multiple Airlines'
            
            dep_time = datetime.fromtimestamp(route['dTimeUTC']).isoformat()
            arr_time = datetime.fromtimestamp(route['aTimeUTC']).isoformat()
            
            duration_sec = route['aTimeUTC'] - route['dTimeUTC']
            duration_min = int(duration_sec / 60)
            
            price = flight.get('price', 0)
            deep_link = flight.get('deep_link', '')
            
            stops = len(flight['route']) - 1
            
            flights.append({
                'airline': airline_name,
                'flight_numbers': ', '.join(airlines),
                'departure_time': dep_time,
                'arrival_time': arr_time,
                'duration': duration_min,
                'stops': stops,
                'price': price,
                'booking_url': deep_link,
                'source': 'Kiwi.com'
            })
        
        return flights
    
    except Exception as e:
        return []


def search_alternate_flights_serp(flight_context, max_results=5):
    """
    Call the Snowflake Python UDF search_alternate_flights(...)
    which talks to SerpAPI via EXTERNAL_ACCESS_INTEGRATIONS.
    """
    try:
        dep_city = (flight_context.get("departure_airport") or "").replace("'", "''")
        arr_city = (flight_context.get("arrival_airport") or "").replace("'", "''")
        sched = str(flight_context.get("scheduled_departure") or "").replace("'", "''")
 
        sql = f"""
            SELECT FLYWISE_AI_DB.GOLD.search_alternate_flights(
                '{dep_city}',
                '{arr_city}',
                '{sched}',
                {max_results}
            ) AS ALT_FLIGHTS
        """
 
        df = session.sql(sql).to_pandas()
        if df.empty:
            return []
 
        alt = df.loc[0, "ALT_FLIGHTS"]
        
        if isinstance(alt, str):
            import json
            try:
                alt = json.loads(alt)
            except json.JSONDecodeError:
                return []
 
        if not alt:
            return []
 
        if isinstance(alt, list) and alt and isinstance(alt[0], dict) and "error" in alt[0]:
            return []
        
        for flight in alt:
            flight['source'] = 'SerpAPI'
 
        return alt
 
    except Exception as e:
        return []


def get_airport_amenities(departure_airport: str, departure_city: str):
    """
    Call Snowflake Python UDF GOLD.GET_AIRPORT_AMENITIES(airport_code, city)
    """
    try:
        code_safe = (departure_airport or "").replace("'", "''")
        city_safe = (departure_city or "").replace("'", "''")

        sql = f"""
            SELECT FLYWISE_AI_DB.GOLD.GET_AIRPORT_AMENITIES(
                '{code_safe}',
                '{city_safe}'
            ) AS AMENITIES
        """

        df = session.sql(sql).to_pandas()
        if df.empty:
            return {}

        amenities = df.loc[0, "AMENITIES"]
        if amenities is None:
            return {}

        if isinstance(amenities, dict):
            return amenities
        return dict(amenities)
    except Exception as e:
        print("Airport amenities error:", e)
        return {}


# =====================================================================
#                     MISTRAL (SNOWFLAKE CORTEX) HELPERS
# =====================================================================

def call_mistral(prompt: str, model: str = "mistral-large"):
    safe_prompt = prompt.replace("'", "''")
    sql = f"""
        SELECT snowflake.cortex.complete('{model}', '{safe_prompt}') AS RESPONSE
    """
    try:
        result = session.sql(sql).collect()
        if result:
            return result[0]["RESPONSE"]
        return "I'm having trouble reaching the AI model right now."
    except Exception as e:
        return f"I'm having trouble reaching the AI model right now: {e}"


def build_initial_delay_message_llm(
    flight: dict, user_profile: dict, is_near_route: bool
) -> str:
    system_instructions = """
You are Flywise Recovery Agent, a helpful travel assistant.
You are talking to a traveller whose monitored flight is delayed.

Your job for THIS FIRST MESSAGE ONLY:
- Greet the user by name.
- Clearly mention the delayed flight number, airline, route, and delay minutes.
- Briefly show empathy and reassurance.
- Offer what you CAN help with:
    * alternate flights,
    * hotels,
    * restaurants / where to eat,
    * local attractions / things to do,
    * what they can do at the departure airport during the delay (lounges, food, shops),
    * and, for short routes, possible bus/car options.
- DO NOT list specific hotels, restaurants, attractions, or amenities yet.
- Keep it concise: 4–6 sentences maximum.
Use a friendly but professional tone.
"""

    context = {
        "user_name": user_profile.get("FULL_NAME"),
        "flight": flight,
        "is_near_route": is_near_route,
        "user_preferences": {
            "spending_preference": user_profile.get("SPENDING_PREFERENCE"),
            "personality_type": user_profile.get("PERSONALITY_TYPE"),
            "cuisine_preferences": user_profile.get("CUISINE_PREFERENCES"),
            "attraction_preferences": user_profile.get("ATTRACTION_PREFERENCES"),
        },
    }

    prompt = (
        system_instructions
        + "\n\nHere is the structured context as JSON:\n"
        + json.dumps(context, default=str)
        + "\n\nNow write the assistant message."
    )

    return call_mistral(prompt)


def build_delay_chat_reply_llm(
    user_message: str,
    flight: dict,
    user_profile: dict,
    options: dict,
    chat_history: list,
    is_near_route: bool,
) -> str:
    system_instructions = """
You are Flywise Recovery Agent, a travel disruption assistant for a *single delayed flight*.

CRITICAL RULES (DO NOT BREAK THESE):
1. You are **NOT** a general-purpose chatbot.
2. You must **ONLY** answer questions directly related to:
   - the current delayed flight,
   - alternate flights or rebooking options,
   - hotels / stay options,
   - restaurants / food options,
   - local attractions / things to do,
   - what to do at the departure airport during the delay (lounges, shops, food, etc.),
   - transport related to this trip (airport → city, bus, car, etc.),
   - creating hourly itineraries for the user's trip.
3. If the user asks ANYTHING outside travel / this trip, reply with:
   "I'm only able to help with your current trip and flight disruption.
    Please ask me about flights, hotels, food, attractions, airport options, itineraries, or other travel help."

4. You only know what is in the JSON context below.

Your job WHEN THE QUESTION **IS** ABOUT TRAVEL / THIS TRIP:
- Read the user's latest message and the previous conversation.
- Decide what they are asking for: flights, hotels, food, attractions, airport activities, itinerary, or a mix.
- Use the structured options to recommend 3–5 of the BEST items for each requested category.

=== HOURLY ITINERARY GENERATION ===
When the user asks for an "itinerary", "plan my day", "schedule", "hourly plan", or similar:

1. **Ask clarifying questions if needed:**
   - How many days/hours do they have?
   - What time does their flight depart?
   - Any must-see places or priorities?

2. **Generate an HOURLY itinerary** using this format:

   📅 **Day 1 Itinerary - [City Name]**
   
   🌅 **Morning**
   - **8:00 AM** - Breakfast at [Restaurant Name] (Rating: X.X)
     📍 [Address] | 💰 [Price Level] | ⏱️ ~45 min
   
   - **9:00 AM** - Visit [Attraction Name] (Rating: X.X)
     📍 [Address] | ⏱️ ~2 hours
     💡 *Why: [Brief reason based on user preferences]*
   
   ☀️ **Afternoon**
   - **12:00 PM** - Lunch at [Restaurant Name] (Rating: X.X)
     📍 [Address] | 🍽️ [Cuisine Type] | ⏱️ ~1 hour
   
   - **1:30 PM** - Explore [Attraction Name] (Rating: X.X)
     📍 [Address] | ⏱️ ~2 hours
   
   🌙 **Evening**
   - **6:00 PM** - Dinner at [Restaurant Name] (Rating: X.X)
     📍 [Address] | 🍽️ [Cuisine Type] | ⏱️ ~1.5 hours
   
   - **8:00 PM** - [Evening activity or return to hotel]
   
   🏨 **Accommodation:** [Hotel Name] (Rating: X.X)
   📍 [Address] | 💰 [Price Category]

3. **Itinerary Rules:**
   - ALWAYS use actual data from the options JSON (hotels, restaurants, attractions)
   - Match activities to user's personality (introvert = quieter spots, extrovert = lively areas)
   - Match restaurants to user's cuisine preferences
   - Match spending level (budget/moderate/luxury) across all recommendations
   - Include realistic travel time between locations (assume 15-30 min between spots)
   - For delays: Start the itinerary from the NEW departure time, working backwards
   - Include a buffer of 2-3 hours before flight for airport arrival
   - If delay is short (<3 hours), suggest airport amenities instead of city exploration

4. **For flight delays specifically:**
   - Calculate available free time = (New Departure Time) - (Current Time) - (2 hour airport buffer)
   - If < 2 hours free: Recommend staying at airport (lounges, restaurants, shops)
   - If 2-4 hours free: Suggest ONE nearby attraction + meal
   - If 4+ hours free: Create a mini-itinerary with 2-3 activities

=== END ITINERARY SECTION ===

When the user asks about flights:
    1. Check if alternate_flights has data (not empty).
    2. If YES: You MUST list EVERY SINGLE flight in the alternate_flights array.
    3. Format each flight like this:

   **Option 1: [airline]** Flight [flight_numbers]
   - Departure: [departure_time] → Arrival: [arrival_time]  
   - Duration: [duration] minutes | Stops: [stops]
   - Price: $[price]

    4. If alternate_flights is empty: Say "I couldn't retrieve live flight options. Please try again."
    5. NEVER skip flights, NEVER say "here are some options" without listing them ALL.
    6. Do NOT invent or hallucinate flights.

- Tailor choices to the user's spending preference, cuisine preferences, and personality.
- Present results in a clean, readable bullet-list style.
- Do NOT dump raw JSON.
"""

    history_text = ""
    for role, msg in chat_history:
        history_text += f"{role.upper()}: {msg}\n"

    context = {
        "flight": flight,
        "user_preferences": {
            "spending_preference": user_profile.get("SPENDING_PREFERENCE"),
            "personality_type": user_profile.get("PERSONALITY_TYPE"),
            "cuisine_preferences": user_profile.get("CUISINE_PREFERENCES"),
            "attraction_preferences": user_profile.get("ATTRACTION_PREFERENCES"),
        },
        "options": options,
        "is_near_route": is_near_route,
    }

    prompt = f"""{system_instructions}

Conversation so far:
{history_text}

Structured context (JSON):
{json.dumps(context, default=str)}

User: {user_message}
Assistant:"""

    return call_mistral(prompt)


# =====================================================================
#                EMBEDDING HELPERS (for RESTAURANTS & ATTRACTIONS)
# =====================================================================

def get_text_embedding(text: str):
    safe_text = text.replace("'", "''")
    sql = f"""
        SELECT SNOWFLAKE.CORTEX.EMBED_TEXT_768(
            'snowflake-arctic-embed-m',
            '{safe_text}'
        ) AS EMB
    """
    try:
        df = session.sql(sql).to_pandas()
        if df.empty:
            return None
        return df.loc[0, "EMB"]
    except Exception as e:
        print("Embedding error:", e)
        return None


def cosine_similarity(vec1, vec2):
    if vec1 is None or vec2 is None:
        return -1.0
    try:
        if len(vec1) != len(vec2):
            return -1.0
        dot = 0.0
        norm1 = 0.0
        norm2 = 0.0
        for a, b in zip(vec1, vec2):
            dot += a * b
            norm1 += a * a
            norm2 += b * b
        if norm1 == 0 or norm2 == 0:
            return -1.0
        return dot / (math.sqrt(norm1) * math.sqrt(norm2))
    except Exception:
        return -1.0


# =====================================================================
#     HYBRID PROFILE + EMBEDDINGS RECOMMENDER (CITY-AWARE)
# =====================================================================

def get_personalized_delay_options(user_profile: dict, arrival_city: str, user_query: str):
    """
    - Hotels: from GOLD.HOTELS_GOLD (filtered by arrival city).
    - Restaurants: from GOLD.GOLD_RESTAURANTS_ANALYTICS (filtered by arrival city).
    - Attractions: from GOLD.ATTRACTIONS_GOLD (filtered by arrival city).
    """

    spending = (user_profile.get("SPENDING_PREFERENCE") or "").lower()

    cuisines_pref = user_profile.get("CUISINE_PREFERENCES") or []
    if isinstance(cuisines_pref, str):
        try:
            cuisines_pref = json.loads(cuisines_pref)
        except Exception:
            cuisines_pref = [cuisines_pref]
    cuisines_pref_lower = [c.lower() for c in cuisines_pref]

    attractions_pref = user_profile.get("ATTRACTION_PREFERENCES") or []
    if isinstance(attractions_pref, str):
        try:
            attractions_pref = json.loads(attractions_pref)
        except Exception:
            attractions_pref = [attractions_pref]
    attractions_pref_lower = [a.lower() for a in attractions_pref]

    raw_city = (arrival_city or "").strip()
    city_token = raw_city.split(",")[0].strip()
    city_safe = city_token.replace("'", "''")
    city_like = f"%{city_token}%" if city_token else "%"

    rich_query_text = (
        f"User query: {user_query}. "
        f"Destination city: {raw_city}. "
        f"User spending preference: {spending}. "
        f"User likes cuisines: {', '.join(cuisines_pref_lower)}. "
        f"User likes attractions: {', '.join(attractions_pref_lower)}."
    )

    query_emb = get_text_embedding(rich_query_text)

    # HOTELS
    def hotel_price_match_score(price_cat: str, spending_pref: str) -> int:
        if not price_cat:
            return 0
        pc = price_cat.strip()

        if spending_pref == "budget":
            preferred = {"$", "$$"}
        elif spending_pref == "moderate":
            preferred = {"$$", "$$$"}
        elif spending_pref == "luxury":
            preferred = {"$$$", "$$$$"}
        else:
            preferred = set()

        if not preferred:
            return 1
        return 2 if pc in preferred else 1

    hotels = []
    try:
        hotels_sql = f"""
            SELECT
                DISPLAY_NAME,
                FORMATTED_ADDRESS,
                PRICE_CATEGORY,
                RATING,
                EDITORIAL_SUMMARY
            FROM GOLD.HOTELS_GOLD
            WHERE
                UPPER(CITY) = UPPER('{city_safe}')
                OR FORMATTED_ADDRESS ILIKE '{city_like}'
        """
        hotels_df = session.sql(hotels_sql).to_pandas()

        if hotels_df.empty:
            hotels_sql_fallback = """
                SELECT
                    DISPLAY_NAME,
                    FORMATTED_ADDRESS,
                    PRICE_CATEGORY,
                    RATING,
                    EDITORIAL_SUMMARY
                FROM GOLD.HOTELS_GOLD
                ORDER BY RATING DESC
                LIMIT 50
            """
            hotels_df = session.sql(hotels_sql_fallback).to_pandas()

        scored_hotels = []
        for _, row in hotels_df.iterrows():
            rating = float(row.get("RATING") or 0.0)
            price_cat = row.get("PRICE_CATEGORY")
            match_score = hotel_price_match_score(price_cat, spending)
            final_score = match_score * 10.0 + rating

            scored_hotels.append({
                "DISPLAY_NAME": row.get("DISPLAY_NAME"),
                "FORMATTED_ADDRESS": row.get("FORMATTED_ADDRESS"),
                "PRICE_CATEGORY": price_cat,
                "RATING": rating,
                "EDITORIAL_SUMMARY": row.get("EDITORIAL_SUMMARY"),
                "_SCORE": final_score,
            })

        scored_hotels.sort(key=lambda x: x["_SCORE"], reverse=True)
        hotels = scored_hotels[:5]
        for h in hotels:
            h.pop("_SCORE", None)
    except Exception as e:
        print("Hotel search error:", e)
        hotels = []

    # RESTAURANTS
    restaurants = []
    try:
        try:
            rest_sql_city = f"""
                SELECT
                    DISPLAY_NAME,
                    SPLIT_PART(TYPES::STRING, ',', 1) AS PRIMARY_TYPE,
                    FORMATTED_ADDRESS,
                    RATING
                FROM GOLD.GOLD_RESTAURANTS_ANALYTICS
                WHERE
                    UPPER(CITY) = UPPER('{city_safe}')
                    OR FORMATTED_ADDRESS ILIKE '{city_like}'
            """
            rest_df = session.sql(rest_sql_city).to_pandas()
        except Exception as e:
            print("Restaurant CITY/address filter error:", e)
            rest_df = pd.DataFrame()

        if rest_df.empty:
            rest_sql_fallback = """
                SELECT
                    DISPLAY_NAME,
                    SPLIT_PART(TYPES::STRING, ',', 1) AS PRIMARY_TYPE,
                    FORMATTED_ADDRESS,
                    RATING
                FROM GOLD.GOLD_RESTAURANTS_ANALYTICS
                ORDER BY RATING DESC
                LIMIT 50
            """
            try:
                rest_df = session.sql(rest_sql_fallback).to_pandas()
            except Exception as e:
                print("Restaurant complete fallback error:", e)
                rest_df = pd.DataFrame()

        if not rest_df.empty:
            scored_restaurants = []
            for _, row in rest_df.iterrows():
                primary_type = (row.get("PRIMARY_TYPE") or "").lower()
                rating = float(row.get("RATING") or 0.0)

                cuisine_match = any(c in primary_type for c in cuisines_pref_lower)
                match_score = 2 if cuisine_match else 1
                final_score = match_score * 10.0 + rating

                scored_restaurants.append({
                    "DISPLAY_NAME": row.get("DISPLAY_NAME"),
                    "PRIMARY_TYPE": row.get("PRIMARY_TYPE"),
                    "FORMATTED_ADDRESS": row.get("FORMATTED_ADDRESS"),
                    "RATING": rating,
                    "_SCORE": final_score,
                })

            scored_restaurants.sort(key=lambda x: x["_SCORE"], reverse=True)
            restaurants = scored_restaurants[:5]
            for r in restaurants:
                r.pop("_SCORE", None)
        else:
            restaurants = []

    except Exception as e:
        print("Restaurant search error:", e)
        restaurants = []

    # ATTRACTIONS
    attractions = []
    try:
        attr_sql = f"""
            SELECT
                NAME,
                DESCRIPTION AS TYPE_OF_ATTRACTION,
                FORMATTED_ADDRESS,
                RATING,
                ALL_EMB AS EMBEDDING_VECTOR
            FROM GOLD.ATTRACTIONS_GOLD
            WHERE
                UPPER(LOCATION) = UPPER('{city_safe}')
                OR LOCATION ILIKE '{city_like}'
                OR FORMATTED_ADDRESS ILIKE '{city_like}'
        """
        attr_df = session.sql(attr_sql).to_pandas()

        if attr_df.empty:
            attr_sql_fallback = """
                SELECT
                    NAME,
                    DESCRIPTION AS TYPE_OF_ATTRACTION,
                    FORMATTED_ADDRESS,
                    RATING,
                    ALL_EMB AS EMBEDDING_VECTOR
                FROM GOLD.ATTRACTIONS_GOLD
                ORDER BY RATING DESC
                LIMIT 50
            """
            attr_df = session.sql(attr_sql_fallback).to_pandas()

        if query_emb is None:
            scored_attractions = []
            for _, row in attr_df.iterrows():
                desc = (row.get("TYPE_OF_ATTRACTION") or "").lower()
                rating = float(row.get("RATING") or 0.0)

                pref_match = any(p in desc for p in attractions_pref_lower)
                match_score = 2 if pref_match else 1
                final_score = match_score * 10.0 + rating

                scored_attractions.append({
                    "NAME": row.get("NAME"),
                    "TYPE_OF_ATTRACTION": row.get("TYPE_OF_ATTRACTION"),
                    "FORMATTED_ADDRESS": row.get("FORMATTED_ADDRESS"),
                    "RATING": rating,
                    "_SCORE": final_score,
                })

            scored_attractions.sort(key=lambda x: x["_SCORE"], reverse=True)
            attractions = scored_attractions[:5]
            for a in attractions:
                a.pop("_SCORE", None)
        else:
            scored_attractions = []
            for _, row in attr_df.iterrows():
                emb = row.get("EMBEDDING_VECTOR")
                sim = cosine_similarity(query_emb, emb)
                scored_attractions.append({
                    "NAME": row.get("NAME"),
                    "TYPE_OF_ATTRACTION": row.get("TYPE_OF_ATTRACTION"),
                    "FORMATTED_ADDRESS": row.get("FORMATTED_ADDRESS"),
                    "RATING": float(row.get("RATING") or 0.0),
                    "_SIM": sim,
                })

            scored_attractions.sort(key=lambda x: x["_SIM"], reverse=True)
            attractions = scored_attractions[:5]
            for a in attractions:
                a.pop("_SIM", None)

    except Exception as e:
        print("Attraction embedding search error:", e)
        attractions = []

    return {
        "hotels": hotels,
        "restaurants": restaurants,
        "attractions": attractions,
    }

# =====================================================================
#                     INTENT DETECTION & SELECTIVE FETCH
# =====================================================================

# def detect_user_intent(message: str) -> set:
#     """Keyword-based intent detection - returns set of intents"""
#     msg = message.lower()
#     intents = set()
    
#     if any(w in msg for w in ["flight", "rebook", "alternate", "reschedule", "flying", "plane"]):
#         intents.add("flights")
#     if any(w in msg for w in ["hotel", "stay", "accommodation", "sleep", "room", "lodge", "where to stay"]):
#         intents.add("hotels")
#     if any(w in msg for w in ["restaurant", "food", "eat", "dining", "dinner", "lunch", "breakfast", "hungry", "cuisine"]):
#         intents.add("restaurants")
#     if any(w in msg for w in ["attraction", "visit", "see", "sightseeing", "tour", "museum", "things to do", "places to visit", "what to do"]):
#         intents.add("attractions")
#     if any(w in msg for w in ["airport", "lounge", "terminal", "wait", "gate", "amenities at"]):
#         intents.add("airport")
#     if any(w in msg for w in ["itinerary", "plan my", "trip plan", "schedule my", "full plan"]):
#         intents.add("itinerary")
    
#     return intents

def detect_user_intent(message: str) -> set:
    """Keyword-based intent detection - returns set of intents"""
    msg = message.lower()
    intents = set()
    
    if any(w in msg for w in ["flight", "rebook", "alternate", "reschedule", "flying", "plane"]):
        intents.add("flights")
    if any(w in msg for w in ["hotel", "stay", "accommodation", "sleep", "room", "lodge", "where to stay"]):
        intents.add("hotels")
    if any(w in msg for w in ["restaurant", "food", "eat", "dining", "dinner", "lunch", "breakfast", "hungry", "cuisine"]):
        intents.add("restaurants")
    if any(w in msg for w in ["attraction", "visit", "see", "sightseeing", "tour", "museum", "things to do", "places to visit", "what to do"]):
        intents.add("attractions")
    if any(w in msg for w in ["airport", "lounge", "terminal", "wait", "gate", "amenities at"]):
        intents.add("airport")
    # Enhanced itinerary detection
    if any(w in msg for w in ["itinerary", "plan my", "trip plan", "schedule my", "full plan", "hourly", "day plan", "plan for", "what should i do", "how should i spend", "schedule for"]):
        intents.add("itinerary")
    
    return intents


def fetch_hotels_only(city: str, user_profile: dict) -> list:
    """Fetch hotels for a city"""
    city_token = (city or "").split(",")[0].strip()
    city_safe = city_token.replace("'", "''")
    city_like = f"%{city_token}%"
    spending = (user_profile.get("SPENDING_PREFERENCE") or "moderate").lower()
    
    try:
        sql = f"""
            SELECT DISPLAY_NAME, FORMATTED_ADDRESS, PRICE_CATEGORY, RATING, EDITORIAL_SUMMARY
            FROM GOLD.HOTELS_GOLD
            WHERE UPPER(CITY) = UPPER('{city_safe}') OR FORMATTED_ADDRESS ILIKE '{city_like}'
            ORDER BY RATING DESC
            LIMIT 10
        """
        df = session.sql(sql).to_pandas()
        if df.empty:
            return []
        
        hotels = df.to_dict('records')
        
        # Score by spending preference
        def price_score(price_cat):
            if not price_cat:
                return 1
            pc = price_cat.strip()
            if spending == "budget":
                return 2 if pc in {"$", "$$"} else 1
            elif spending == "moderate":
                return 2 if pc in {"$$", "$$$"} else 1
            elif spending == "luxury":
                return 2 if pc in {"$$$", "$$$$"} else 1
            return 1
        
        for h in hotels:
            h["_score"] = price_score(h.get("PRICE_CATEGORY")) * 10 + float(h.get("RATING") or 0)
        
        hotels.sort(key=lambda x: x["_score"], reverse=True)
        for h in hotels:
            h.pop("_score", None)
        
        return hotels[:5]
    except Exception as e:
        print(f"Hotel fetch error: {e}")
        return []


def fetch_restaurants_only(city: str, user_profile: dict) -> list:
    """Fetch restaurants for a city"""
    city_token = (city or "").split(",")[0].strip()
    city_safe = city_token.replace("'", "''")
    city_like = f"%{city_token}%"
    
    cuisines_pref = user_profile.get("CUISINE_PREFERENCES") or []
    if isinstance(cuisines_pref, str):
        try:
            cuisines_pref = json.loads(cuisines_pref)
        except:
            cuisines_pref = [cuisines_pref] if cuisines_pref else []
    cuisines_lower = [c.lower() for c in cuisines_pref]
    
    try:
        sql = f"""
            SELECT DISPLAY_NAME, SPLIT_PART(TYPES::STRING, ',', 1) AS PRIMARY_TYPE, FORMATTED_ADDRESS, RATING
            FROM GOLD.GOLD_RESTAURANTS_ANALYTICS
            WHERE UPPER(CITY) = UPPER('{city_safe}') OR FORMATTED_ADDRESS ILIKE '{city_like}'
            ORDER BY RATING DESC
            LIMIT 15
        """
        df = session.sql(sql).to_pandas()
        if df.empty:
            return []
        
        restaurants = df.to_dict('records')
        
        # Score by cuisine preference
        for r in restaurants:
            primary_type = (r.get("PRIMARY_TYPE") or "").lower()
            match = any(c in primary_type for c in cuisines_lower)
            r["_score"] = (2 if match else 1) * 10 + float(r.get("RATING") or 0)
        
        restaurants.sort(key=lambda x: x["_score"], reverse=True)
        for r in restaurants:
            r.pop("_score", None)
        
        return restaurants[:5]
    except Exception as e:
        print(f"Restaurant fetch error: {e}")
        return []


def fetch_attractions_only(city: str, user_profile: dict) -> list:
    """Fetch attractions for a city"""
    city_token = (city or "").split(",")[0].strip()
    city_safe = city_token.replace("'", "''")
    city_like = f"%{city_token}%"
    
    attractions_pref = user_profile.get("ATTRACTION_PREFERENCES") or []
    if isinstance(attractions_pref, str):
        try:
            attractions_pref = json.loads(attractions_pref)
        except:
            attractions_pref = [attractions_pref] if attractions_pref else []
    prefs_lower = [a.lower() for a in attractions_pref]
    
    try:
        sql = f"""
            SELECT NAME, DESCRIPTION AS TYPE_OF_ATTRACTION, FORMATTED_ADDRESS, RATING
            FROM GOLD.ATTRACTIONS_GOLD
            WHERE UPPER(LOCATION) = UPPER('{city_safe}') OR LOCATION ILIKE '{city_like}' OR FORMATTED_ADDRESS ILIKE '{city_like}'
            ORDER BY RATING DESC
            LIMIT 15
        """
        df = session.sql(sql).to_pandas()
        if df.empty:
            return []
        
        attractions = df.to_dict('records')
        
        # Score by preference match
        for a in attractions:
            desc = (a.get("TYPE_OF_ATTRACTION") or "").lower()
            match = any(p in desc for p in prefs_lower)
            a["_score"] = (2 if match else 1) * 10 + float(a.get("RATING") or 0)
        
        attractions.sort(key=lambda x: x["_score"], reverse=True)
        for a in attractions:
            a.pop("_score", None)
        
        return attractions[:5]
    except Exception as e:
        print(f"Attraction fetch error: {e}")
        return []


def get_options_for_intents(intents: set, user_profile: dict, flight_context: dict) -> dict:
    """Fetch ONLY what's needed based on detected intents"""
    options = {}
    city = flight_context.get("arrival_city", "")
    
    # Itinerary = hotels + restaurants + attractions
    if "itinerary" in intents:
        intents.update({"hotels", "restaurants", "attractions"})
    
    if "flights" in intents:
        options["alternate_flights"] = search_alternate_flights_serp(flight_context)
    
    if "hotels" in intents:
        options["hotels"] = fetch_hotels_only(city, user_profile)
    
    if "restaurants" in intents:
        options["restaurants"] = fetch_restaurants_only(city, user_profile)
    
    if "attractions" in intents:
        options["attractions"] = fetch_attractions_only(city, user_profile)
    
    if "airport" in intents:
        options["airport_amenities"] = get_airport_amenities(
            flight_context.get("departure_airport"),
            flight_context.get("departure_city")
        )
    
    return options

# =====================================================================
#                     BOOKING LINK GENERATORS
# =====================================================================

def get_airline_official_website(airline_name: str) -> dict:
    """Map airline names to their official booking URLs"""
    airline_urls = {
        "AMERICAN": {"name": "American Airlines", "url": "https://www.aa.com"},
        "DELTA": {"name": "Delta Air Lines", "url": "https://www.delta.com"},
        "UNITED": {"name": "United Airlines", "url": "https://www.united.com"},
        "SOUTHWEST": {"name": "Southwest Airlines", "url": "https://www.southwest.com"},
        "JETBLUE": {"name": "JetBlue Airways", "url": "https://www.jetblue.com"},
        "ALASKA": {"name": "Alaska Airlines", "url": "https://www.alaskaair.com"},
        "SPIRIT": {"name": "Spirit Airlines", "url": "https://www.spirit.com"},
        "FRONTIER": {"name": "Frontier Airlines", "url": "https://www.flyfrontier.com"},
        "LUFTHANSA": {"name": "Lufthansa", "url": "https://www.lufthansa.com"},
        "BRITISH AIRWAYS": {"name": "British Airways", "url": "https://www.britishairways.com"},
        "AIR FRANCE": {"name": "Air France", "url": "https://www.airfrance.com"},
        "KLM": {"name": "KLM", "url": "https://www.klm.com"},
        "EMIRATES": {"name": "Emirates", "url": "https://www.emirates.com"},
        "QATAR": {"name": "Qatar Airways", "url": "https://www.qatarairways.com"},
        "SINGAPORE": {"name": "Singapore Airlines", "url": "https://www.singaporeair.com"},
        "CATHAY": {"name": "Cathay Pacific", "url": "https://www.cathaypacific.com"},
        "AIR CANADA": {"name": "Air Canada", "url": "https://www.aircanada.com"},
        "QANTAS": {"name": "Qantas", "url": "https://www.qantas.com"},
        "ETIHAD": {"name": "Etihad Airways", "url": "https://www.etihad.com"},
        "TURKISH": {"name": "Turkish Airlines", "url": "https://www.turkishairlines.com"},
        "ANA": {"name": "All Nippon Airways", "url": "https://www.ana.co.jp/en/us/"},
        "JAL": {"name": "Japan Airlines", "url": "https://www.jal.co.jp/en/"},
        "KOREAN AIR": {"name": "Korean Air", "url": "https://www.koreanair.com"},
        "AIR INDIA": {"name": "Air India", "url": "https://www.airindia.com"},
        "VIRGIN ATLANTIC": {"name": "Virgin Atlantic", "url": "https://www.virginatlantic.com"},
        "IBERIA": {"name": "Iberia", "url": "https://www.iberia.com"},
        "ALITALIA": {"name": "ITA Airways", "url": "https://www.ita-airways.com"},
    }
    
    airline_upper = airline_name.upper().strip()
    for key, value in airline_urls.items():
        if key in airline_upper:
            return value
    return {"name": airline_name, "url": "https://www.google.com/flights"}


def generate_kayak_url(dep_airport: str, arr_airport: str, date_str: str) -> str:
    """Generate Kayak search URL"""
    try:
        if 'T' in date_str or ' ' in date_str:
            date_obj = datetime.fromisoformat(date_str.replace('Z', '+00:00').split('T')[0])
        else:
            date_obj = datetime.strptime(date_str, '%Y-%m-%d')
        formatted_date = date_obj.strftime('%Y-%m-%d')
        return f"https://www.kayak.com/flights/{dep_airport}-{arr_airport}/{formatted_date}?sort=price_a"
    except:
        return f"https://www.kayak.com/flights/{dep_airport}-{arr_airport}"


def generate_skyscanner_url(dep_airport: str, arr_airport: str, date_str: str) -> str:
    """Generate Skyscanner search URL"""
    try:
        if 'T' in date_str or ' ' in date_str:
            date_obj = datetime.fromisoformat(date_str.replace('Z', '+00:00').split('T')[0])
        else:
            date_obj = datetime.strptime(date_str, '%Y-%m-%d')
        formatted_date = date_obj.strftime('%y%m%d')
        return f"https://www.skyscanner.com/transport/flights/{dep_airport}/{arr_airport}/{formatted_date}/"
    except:
        return f"https://www.skyscanner.com/transport/flights/{dep_airport}/{arr_airport}"


def get_all_booking_links(flight_data: dict, dep_airport: str, arr_airport: str) -> list:
    """Generate all booking links for a flight - includes Kiwi deep link if available"""
    booking_links = []
    
    departure_time = flight_data.get('departure_time', '')
    date_str = departure_time.split('T')[0] if 'T' in departure_time else departure_time.split(' ')[0]
    airline_name = flight_data.get('airline', '')
    price = flight_data.get('price', '')
    
    # Priority 1: Kiwi deep link (direct booking with real price)
    kiwi_link = flight_data.get('booking_url', '')
    if kiwi_link:
        booking_links.append({
            'platform': 'Kiwi.com',
            'url': kiwi_link,
            'is_primary': True,
            'display_name': f"🔥 Book Now - ${price} (Kiwi.com)"
        })
    
    # Priority 2: Official airline
    official = get_airline_official_website(airline_name)
    booking_links.append({
        'platform': official['name'],
        'url': official['url'],
        'is_primary': False,
        'display_name': f"✈️ {official['name']}"
    })
    
    # Priority 3: Aggregators
    booking_links.append({
        'platform': 'Kayak',
        'url': generate_kayak_url(dep_airport, arr_airport, date_str),
        'is_primary': False,
        'display_name': '🛫 Kayak'
    })
    
    booking_links.append({
        'platform': 'Skyscanner',
        'url': generate_skyscanner_url(dep_airport, arr_airport, date_str),
        'is_primary': False,
        'display_name': '✈️ Skyscanner'
    })
    
    return booking_links


# =====================================================================
#                  PRICE PARSING & FLIGHT DISPLAY
# =====================================================================

def parse_price(price_str) -> float:
    """
    Safely parse price string to float.
    Handles: "$245", "245", "1,245", "245 USD", None, etc.
    """
    if price_str is None:
        return 999999.0
    
    if isinstance(price_str, (int, float)):
        return float(price_str)
    
    try:
        clean_price = str(price_str).replace('$', '').replace(',', '').replace('USD', '').replace('EUR', '').strip()
        if not clean_price:
            return 999999.0
        return float(clean_price)
    except (ValueError, AttributeError):
        return 999999.0


def display_flight_with_booking_links(flight_data: dict, dep_airport: str, 
                                       arr_airport: str, index: int, is_cheapest: bool = False):
    """Display a single flight card with booking links using Streamlit native components"""
    airline = flight_data.get('airline', 'Unknown')
    flight_numbers = flight_data.get('flight_numbers', 'N/A')
    departure_time = flight_data.get('departure_time', 'N/A')
    arrival_time = flight_data.get('arrival_time', 'N/A')
    duration = flight_data.get('duration', 'N/A')
    stops = flight_data.get('stops', 'N/A')
    price_raw = flight_data.get('price', 'N/A')
    source = flight_data.get('source', 'Unknown')
    
    # Format price safely
    if price_raw == 'N/A':
        price_display = 'N/A'
    else:
        price_clean = str(price_raw).replace('$', '').replace(',', '').strip()
        try:
            price_num = float(price_clean)
            price_display = f"${price_num:.0f}"
        except (ValueError, AttributeError):
            price_display = str(price_raw)
    
    # Format times
    try:
        dep_time_display = departure_time.split('T')[1][:5] if 'T' in str(departure_time) else str(departure_time)
        arr_time_display = arrival_time.split('T')[1][:5] if 'T' in str(arrival_time) else str(arrival_time)
    except:
        dep_time_display = str(departure_time)
        arr_time_display = str(arrival_time)
    
    # Create container with colored highlight for cheapest
    if is_cheapest:
        st.success("🏆 CHEAPEST OPTION")
    
    with st.container():
        # Flight header with airline and price
        col1, col2 = st.columns([3, 1])
        with col1:
            st.markdown(f"### ✈️ {airline}")
            st.caption(f"Flight {flight_numbers} • Source: {source}")
        with col2:
            st.markdown(f"### {price_display}")
            st.caption("per person")
        
        # Flight details - times and route
        col_left, col_mid, col_right = st.columns([2, 3, 2])
        with col_left:
            st.markdown(f"**{dep_time_display}**")
            st.caption(dep_airport)
        with col_mid:
            st.markdown(f"**{duration} min** • {stops} stops")
        with col_right:
            st.markdown(f"**{arr_time_display}**")
            st.caption(arr_airport)
        
        st.divider()
        
        # Booking links
        booking_links = get_all_booking_links(flight_data, dep_airport, arr_airport)
        
        # Show primary booking link (Kiwi deep link or official airline)
        primary_link = next((link for link in booking_links if link.get('is_primary')), booking_links[0])
        st.markdown("**📍 Book this flight:**")
        st.link_button(
            primary_link['display_name'], 
            primary_link['url'], 
            type="primary", 
            use_container_width=True
        )
        
        # Show comparison links
        st.markdown("**🔎 Compare prices on:**")
        other_links = [link for link in booking_links if not link.get('is_primary')]
        cols = st.columns(min(3, len(other_links)))
        for idx, link in enumerate(other_links[:3]):
            with cols[idx]:
                st.link_button(link['display_name'], link['url'], use_container_width=True)
    
    st.markdown("---")


def display_all_alternate_flights(alternate_flights: list, dep_airport: str, arr_airport: str):
    """Display all alternate flights sorted by price with booking links"""
    if not alternate_flights:
        st.info("No alternate flights available at the moment.")
        return
    
    # Sort by price using safe price parser
    sorted_flights = sorted(alternate_flights, key=lambda x: parse_price(x.get('price', 999999)))
    
    st.markdown("### 🛫 Available Alternate Flights")
    st.markdown(f"Found **{len(sorted_flights)}** alternate flight options, sorted by price")
    
    # Show data sources
    sources = list(set([f.get('source', 'Unknown') for f in sorted_flights]))
    st.caption(f"📊 Data sources: {', '.join(sources)}")
    st.markdown("---")
    
    # Display each flight
    for idx, flight in enumerate(sorted_flights):
        is_cheapest = (idx == 0)
        display_flight_with_booking_links(flight, dep_airport, arr_airport, idx + 1, is_cheapest)


# =====================================================================
#                          AUTH FUNCTIONS
# =====================================================================

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()


def verify_user(email, password):
    try:
        password_hash = hash_password(password)
        query = f"""
        SELECT USER_ID, EMAIL, FULL_NAME,
               SPENDING_PREFERENCE, PERSONALITY_TYPE, 
               ATTRACTION_PREFERENCES, CUISINE_PREFERENCES,
               DIETARY_RESTRICTIONS, PREFERRED_TRAVEL_CLASS
        FROM GOLD.USER_PROFILES
        WHERE EMAIL = '{email}' 
        AND PASSWORD_HASH = '{password_hash}'
        AND IS_ACTIVE = TRUE
        """
        result = session.sql(query).collect()

        if result:
            user_data = result[0].as_dict()
            session.sql(
                f"UPDATE GOLD.USER_PROFILES "
                f"SET LAST_LOGIN = CURRENT_TIMESTAMP() "
                f"WHERE USER_ID = {user_data['USER_ID']}"
            ).collect()
            return user_data
        return None
    except Exception as e:
        st.error(f"Error: {str(e)}")
        return None


def create_user(email, password, full_name, phone, preferences):
    try:
        check_query = (
            f"SELECT COUNT(*) as count FROM GOLD.USER_PROFILES WHERE EMAIL = '{email}'"
        )
        exists = session.sql(check_query).collect()[0]["COUNT"]

        if exists > 0:
            return False, "Email already registered"

        password_hash = hash_password(password)

        attractions_str = ", ".join(
            [f"'{item}'" for item in preferences["attraction_preferences"]]
        )
        cuisines_str = ", ".join(
            [f"'{item}'" for item in preferences["cuisine_preferences"]]
        )
        dietary_str = (
            ", ".join([f"'{item}'" for item in preferences["dietary_restrictions"]])
            if preferences["dietary_restrictions"]
            else "'None'"
        )

        insert_query = f"""
        INSERT INTO GOLD.USER_PROFILES (
            EMAIL, PASSWORD_HASH, FULL_NAME, PHONE,
            SPENDING_PREFERENCE, PERSONALITY_TYPE,
            ATTRACTION_PREFERENCES, CUISINE_PREFERENCES,
            DIETARY_RESTRICTIONS, PREFERRED_TRAVEL_CLASS,
            CREATED_AT, IS_ACTIVE
        ) 
        SELECT 
            '{email}', '{password_hash}', '{full_name.replace("'", "''")}', '{phone}',
            '{preferences['spending_preference']}', '{preferences['personality_type']}',
            ARRAY_CONSTRUCT({attractions_str}),
            ARRAY_CONSTRUCT({cuisines_str}),
            ARRAY_CONSTRUCT({dietary_str}),
            '{preferences['preferred_travel_class']}',
            CURRENT_TIMESTAMP(), TRUE
        """

        session.sql(insert_query).collect()
        return True, "Account created successfully"

    except Exception as e:
        return False, f"Error: {str(e)}"


# =====================================================================
#                     DASHBOARD / DATA FUNCTIONS
# =====================================================================

@st.cache_data(ttl=30)
def get_user_subscriptions(user_id, limit: int = 1):
    query = f"""
    WITH recent AS (
        SELECT
            s.SUBSCRIPTION_ID,
            s.USER_EMAIL,
            s.FLIGHT_IATA,
            s.DEPARTURE_AIRPORT,
            s.ARRIVAL_AIRPORT,
            s.SCHEDULED_DEPARTURE,
            s.DELAY_THRESHOLD,
            s.PASSENGER_NAME,
            s.IS_ACTIVE,
            s.CREATED_AT
        FROM GOLD.USER_SUBSCRIPTIONS s
        WHERE s.USER_ID = {user_id}
          AND s.IS_ACTIVE = TRUE
          AND UPPER(s.DEPARTURE_AIRPORT) <> 'PENDING'
          AND UPPER(s.ARRIVAL_AIRPORT)   <> 'PENDING'
        ORDER BY s.CREATED_AT DESC
        LIMIT {limit}
    )
    SELECT
        r.SUBSCRIPTION_ID,
        r.USER_EMAIL,
        r.FLIGHT_IATA,
        r.DEPARTURE_AIRPORT,
        r.ARRIVAL_AIRPORT,
        r.SCHEDULED_DEPARTURE,
        r.DELAY_THRESHOLD,
        r.PASSENGER_NAME,
        r.IS_ACTIVE,
        f.STATUS,
        f.DELAY_MINUTES
    FROM recent r
    LEFT JOIN GOLD.GOLD_FLIGHT_DATA f 
      ON r.FLIGHT_IATA       = f.FLIGHT_IATA
     AND r.DEPARTURE_AIRPORT = f.DEPARTURE_AIRPORT
     AND DATE(r.SCHEDULED_DEPARTURE) = DATE(f.SCHEDULED_DEPARTURE)
    ORDER BY r.SCHEDULED_DEPARTURE DESC;
    """

    try:
        df = session.sql(query).to_pandas()
        return df
    except Exception:
        return pd.DataFrame()


def add_flight_subscription(
    user_id,
    user_email,
    flight_iata,
    departure_airport,
    arrival_airport,
    scheduled_departure,
    passenger_name,
    delay_threshold,
):
    try:
        insert_query = f"""
        INSERT INTO GOLD.USER_SUBSCRIPTIONS 
            (USER_ID, USER_EMAIL, FLIGHT_IATA, DEPARTURE_AIRPORT, ARRIVAL_AIRPORT, 
             SCHEDULED_DEPARTURE, PASSENGER_NAME, DELAY_THRESHOLD, IS_ACTIVE, CREATED_AT)
        SELECT 
            {user_id}, '{user_email}', '{flight_iata}', '{departure_airport}', '{arrival_airport}',
            '{scheduled_departure}', '{passenger_name}', {delay_threshold}, TRUE, CURRENT_TIMESTAMP()
        """

        session.sql(insert_query).collect()
        st.cache_data.clear()
        return True
    except Exception as e:
        st.error(f"Error: {str(e)}")
        return False


# =====================================================================
#   DELAYED FLIGHT QUERY (VIEW + SUBSCRIPTIONS)
# =====================================================================

def get_latest_delayed_flight_for_user(user_id: int):
    sql = f"""
    SELECT
        USER_ID,
        FLIGHT_IATA,
        AIRLINE_NAME,
        DEPARTURE_CITY,
        ARRIVAL_CITY,
        DEPARTURE_AIRPORT,
        ARRIVAL_AIRPORT,
        STATUS,
        DELAY_MINUTES,
        SCHEDULED_DEPARTURE,
        ACTUAL_DEPARTURE,
        UPDATED_AT
    FROM GOLD.VIEW_USER_DELAYED_FLIGHTS
    WHERE USER_ID = {user_id}
      AND STATUS = 'DELAYED'
      AND ACTUAL_DEPARTURE IS NOT NULL
    ORDER BY SCHEDULED_DEPARTURE DESC, UPDATED_AT DESC
    LIMIT 1;
    """

    try:
        df = session.sql(sql).to_pandas()
        if df.empty:
            return None
        row = df.iloc[0]
    except Exception as e:
        st.warning(f"Delay assistant query failed: {e}")
        return None

    flight = {
        "user_id": int(row["USER_ID"]),
        "flight_iata": row["FLIGHT_IATA"],
        "airline_name": row["AIRLINE_NAME"],
        "departure_city": row["DEPARTURE_CITY"],
        "arrival_city": row["ARRIVAL_CITY"],
        "departure_airport": row["DEPARTURE_AIRPORT"],
        "arrival_airport": row["ARRIVAL_AIRPORT"],
        "status": row["STATUS"],
        "delay_minutes": int(row["DELAY_MINUTES"]) if row["DELAY_MINUTES"] is not None else 0,
        "scheduled_departure": str(row["SCHEDULED_DEPARTURE"]),
        "actual_departure": str(row["ACTUAL_DEPARTURE"]),
    }

    flight["is_near_route"] = route_is_near(
        flight["departure_city"], flight["arrival_city"]
    )
    return flight


# =====================================================================
#                       SESSION INIT / STYLING
# =====================================================================

if "authenticated" not in st.session_state:
    st.session_state.authenticated = False
if "user_data" not in st.session_state:
    st.session_state.user_data = None
if "show_signup" not in st.session_state:
    st.session_state.show_signup = False
if "delay_chat" not in st.session_state:
    st.session_state.delay_chat = []
if "delay_chat_flight_key" not in st.session_state:
    st.session_state.delay_chat_flight_key = None
if "current_alt_flights" not in st.session_state:
    st.session_state.current_alt_flights = None
if "current_flight_airports" not in st.session_state:
    st.session_state.current_flight_airports = None

st.markdown(
    """
<style>
    .auth-header {
        text-align: center;
        font-size: 2.5rem;
        font-weight: bold;
        background: linear-gradient(90deg, #667eea 0%, #764ba2 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin: 2rem 0;
    }
    .main-header {
        text-align: center;
        font-size: 3rem;
        font-weight: bold;
        background: linear-gradient(90deg, #667eea 0%, #764ba2 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        padding: 1rem;
    }
</style>
""",
    unsafe_allow_html=True,
)


# =====================================================================
#                           AUTH PAGES
# =====================================================================

def show_login_page():
    st.markdown('<h1 class="auth-header">Login</h1>', unsafe_allow_html=True)

    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        with st.form("login_form"):
            email = st.text_input("📧 Email", placeholder="your@email.com")
            password = st.text_input("🔑 Password", type="password")

            col_a, col_b = st.columns(2)
            with col_a:
                login = st.form_submit_button(
                    "Login", type="primary", use_container_width=True
                )
            with col_b:
                signup = st.form_submit_button("Sign Up", use_container_width=True)

            if login:
                if email and password:
                    user_data = verify_user(email, password)
                    if user_data:
                        st.session_state.authenticated = True
                        st.session_state.user_data = user_data
                        st.session_state.nav_page = "📍 My Flights"
                        st.success("✅ Login successful!")
                        st.rerun()
                    else:
                        st.error("Invalid credentials!")
                else:
                    st.error("Fill all fields")

            if signup:
                st.session_state.show_signup = True
                st.rerun()


def show_signup_page():
    st.markdown('<h1 class="auth-header">Create Account</h1>', unsafe_allow_html=True)

    with st.form("signup_form"):
        st.subheader("Basic Info")
        col1, col2 = st.columns(2)
        with col1:
            full_name = st.text_input("Full Name*")
            email = st.text_input("Email*")
        with col2:
            phone = st.text_input("Phone")
            password = st.text_input("Password*", type="password")

        confirm_password = st.text_input("Confirm Password*", type="password")

        st.divider()
        st.subheader("Travel Preferences")

        col3, col4 = st.columns(2)
        with col3:
            spending = st.selectbox("💰 Spending", ["budget", "moderate", "luxury"])
            personality = st.selectbox(
                "🧠 Personality", ["introvert", "ambivert", "extrovert"]
            )
        with col4:
            travel_class = st.selectbox(
                "💺 Class", ["economy", "premium_economy", "business", "first"]
            )

        st.divider()
        attractions = st.multiselect(
            "🎯 Attractions*",
            [
                "Museums",
                "Historical Sites",
                "Hiking",
                "Beaches",
                "Adventure",
                "Nightlife",
                "Shopping",
                "Culture",
            ],
        )

        cuisines = st.multiselect(
            "🍕 Cuisines*",
            [
                "Italian",
                "Chinese",
                "Indian",
                "Mexican",
                "Japanese",
                "Thai",
                "French",
                "American",
            ],
        )

        dietary = st.multiselect(
            "🥗 Dietary",
            ["Vegetarian", "Vegan", "Gluten-Free", "Halal", "Kosher", "None"],
        )

        agree = st.checkbox("I agree to Terms & Conditions*")

        col_back, col_submit = st.columns(2)
        with col_back:
            back = st.form_submit_button("← Back", use_container_width=True)
        with col_submit:
            submit = st.form_submit_button(
                "Create Account 🚀", type="primary", use_container_width=True
            )

        if back:
            st.session_state.show_signup = False
            st.rerun()

        if submit:
            if not all(
                [full_name, email, password, confirm_password, attractions, cuisines, agree]
            ):
                st.error("❌ Fill all required fields")
            elif password != confirm_password:
                st.error("❌ Passwords don't match")
            elif len(password) < 8:
                st.error("❌ Password must be 8+ characters")
            else:
                prefs = {
                    "spending_preference": spending,
                    "personality_type": personality,
                    "attraction_preferences": attractions,
                    "cuisine_preferences": cuisines,
                    "dietary_restrictions": dietary,
                    "preferred_travel_class": travel_class,
                }

                success, msg = create_user(email, password, full_name, phone, prefs)
                if success:
                    st.success(f"✅ {msg}")
                    st.info("Redirecting to login...")
                    import time as _time

                    _time.sleep(2)
                    st.session_state.show_signup = False
                    st.rerun()
                else:
                    st.error(f"❌ {msg}")


# =====================================================================
#                              MAIN APP
# =====================================================================

if not st.session_state.authenticated:
    if st.session_state.show_signup:
        show_signup_page()
    else:
        show_login_page()
else:
    user_data = st.session_state.user_data

    col_h, col_u = st.columns([4, 1])
    with col_h:
        st.markdown('<h1 class="main-header">✈️ Flywise</h1>', unsafe_allow_html=True)
    with col_u:
        st.write(f"👤 {user_data['FULL_NAME']}")
        if st.button("Logout 🚪"):
            for key in list(st.session_state.keys()):
                del st.session_state[key]
            st.rerun()

    with st.sidebar:
        st.header("🧭 Navigation")
        pages = ["📍 My Flights", "🛫 Monitor Flight", "👤 Profile"]

        if "nav_page" not in st.session_state:
            st.session_state.nav_page = "📍 My Flights"

        page = st.selectbox(
            "Select Page",
            pages,
            key="nav_page",
            label_visibility="collapsed",
        )

    if page == "🛫 Monitor Flight":
        st.header("🛫 Add Flight to Monitor")

        with st.form("flight_monitor_form", clear_on_submit=True):
            st.subheader("Flight Information")

            col1, col2 = st.columns(2)
            with col1:
                flight_number = st.text_input(
                    "✈️ Flight Number (IATA)*",
                    placeholder="AA123",
                    help="Enter the IATA flight number (e.g., AA123, UA456, DL789)",
                )
            with col2:
                passenger_name = st.text_input(
                    "👤 Passenger Name",
                    placeholder="John Doe",
                    value=user_data["FULL_NAME"],
                )

            col3, col4 = st.columns(2)
            with col3:
                departure_airport = st.text_input(
                    "🛫 Departure Airport (IATA)*",
                    placeholder="JFK",
                    help="3-letter IATA code of departure airport (e.g., JFK)",
                )
            with col4:
                arrival_airport = st.text_input(
                    "🛬 Arrival Airport (IATA)*",
                    placeholder="LAX",
                    help="3-letter IATA code of arrival airport (e.g., LAX)",
                )

            col5, col6 = st.columns(2)
            with col5:
                departure_date = st.date_input(
                    "📅 Departure Date*",
                    min_value=date.today(),
                    help="Date of scheduled departure",
                )
            with col6:
                if "departure_time_str" not in st.session_state:
                    st.session_state.departure_time_str = (
                        datetime.now() + timedelta(hours=2)
                    ).strftime("%H:%M")
                departure_time_str = st.text_input(
                    "⏰ Departure Time*",
                    key="departure_time_str",
                    help="Enter local departure time in 24-hour format HH:MM (e.g., 22:45)",
                )

            st.divider()

            threshold = st.slider(
                "⏱ Delay Notification Threshold (min)",
                15,
                120,
                40,
                5,
                help="You'll be notified when delay exceeds this threshold",
            )

            st.divider()

            submitted = st.form_submit_button(
                "🚀 Start Monitoring", type="primary", use_container_width=True
            )

            if submitted:
                if not flight_number:
                    st.error("❌ Please enter a flight number")
                elif not departure_airport or not arrival_airport:
                    st.error("❌ Please enter both departure and arrival airports")
                else:
                    try:
                        departure_time = datetime.strptime(
                            departure_time_str.strip(), "%H:%M"
                        ).time()
                    except ValueError:
                        st.error(
                            "❌ Please enter departure time in HH:MM 24-hour format (e.g., 22:45)"
                        )
                        st.stop()

                    flight_iata = flight_number.upper().strip()
                    dep_airport = departure_airport.upper().strip()
                    arr_airport = arrival_airport.upper().strip()

                    scheduled_departure = datetime.combine(
                        departure_date, departure_time
                    )

                    success = add_flight_subscription(
                        user_id=user_data["USER_ID"],
                        user_email=user_data["EMAIL"],
                        flight_iata=flight_iata,
                        departure_airport=dep_airport,
                        arrival_airport=arr_airport,
                        scheduled_departure=scheduled_departure,
                        passenger_name=passenger_name,
                        delay_threshold=threshold,
                    )

                    if success:
                        st.success(
                            f"""
                        ✅ **Flight {flight_iata} Added to Monitoring!**
                    
                        🛫 From **{dep_airport}**  
                        🛬 To **{arr_airport}**  
                        📅 Departure **{scheduled_departure.strftime('%Y-%m-%d %H:%M')}**
                        """
                        )
                        st.cache_data.clear()
                    else:
                        st.error("⚠ Error adding flight to monitoring. Please try again.")

    elif page == "📍 My Flights":
        st.header("📍 My Active Flights")

        user_subs = get_user_subscriptions(user_data["USER_ID"])

        if user_subs.empty:
            st.info("No flights currently being monitored. Add a flight to get started!")
        else:
            st.success(f"Monitoring {len(user_subs)} recent flight(s)")

            for idx, flight in user_subs.iterrows():
                with st.expander(
                    f"✈️ {flight['FLIGHT_IATA']} - {flight['DEPARTURE_AIRPORT']} → {flight['ARRIVAL_AIRPORT']}"
                ):
                    col1, col2 = st.columns(2)

                    with col1:
                        st.write("**Flight Details:**")
                        st.write(f"Flight: {flight['FLIGHT_IATA']}")
                        st.write(
                            f"Route: {flight['DEPARTURE_AIRPORT']} → {flight['ARRIVAL_AIRPORT']}"
                        )
                        st.write(f"Passenger: {flight.get('PASSENGER_NAME', 'N/A')}")

                    with col2:
                        st.write("**Schedule:**")
                        dep_time = pd.to_datetime(flight["SCHEDULED_DEPARTURE"])
                        st.write(f"Date: {dep_time.strftime('%Y-%m-%d')}")
                        st.write(f"Time: {dep_time.strftime('%H:%M')}")
                        st.write(f"Threshold: {flight['DELAY_THRESHOLD']} min")

        st.divider()

        st.subheader("🧠 Flywise Assistant – Delay Recovery")
        st.caption(
            "This assistant helps when your monitored flights are delayed."
        )

        delayed_flight = get_latest_delayed_flight_for_user(user_data["USER_ID"])

        if delayed_flight is None:
            st.info(
                "No delayed flights detected. When a delay occurs, I'll help you with alternate flights, hotels, restaurants, and more!"
            )
        else:
            current_flight_key = f"{delayed_flight['flight_iata']}_{delayed_flight['scheduled_departure']}"

            # Reset chat if different flight
            if st.session_state.delay_chat_flight_key != current_flight_key:
                st.session_state.delay_chat = []
                st.session_state.delay_chat_flight_key = current_flight_key
                st.session_state.current_alt_flights = None
                st.session_state.current_flight_airports = None

            # Initial greeting if chat is empty
            if not st.session_state.delay_chat:
                initial_msg = build_initial_delay_message_llm(
                    delayed_flight,
                    user_data,
                    is_near_route=delayed_flight["is_near_route"],
                )
                st.session_state.delay_chat.append(("assistant", initial_msg))

            # Flight info banner
            st.warning(
                f"⚠️ **{delayed_flight['flight_iata']}** ({delayed_flight['departure_city']} → {delayed_flight['arrival_city']}) "
                f"is delayed by **{delayed_flight['delay_minutes']} minutes**"
            )

            # Mode selection buttons
            st.markdown("#### What would you like to do?")
            col_mode1, col_mode2, col_mode3 = st.columns(3)
            
            with col_mode1:
                if st.button("✈️ Find Alternate Flights", use_container_width=True, key="btn_flights"):
                    st.session_state.delay_chat.append(("user", "Show me alternate flights"))
                    st.rerun()
            
            with col_mode2:
                if st.button("🗺️ Plan My Trip First", use_container_width=True, key="btn_plan"):
                    intro = (
                        f"Let's plan your time in **{delayed_flight['arrival_city']}**! "
                        f"Ask me about:\n"
                        f"- 🏨 Hotels and places to stay\n"
                        f"- 🍽️ Restaurants and food\n"
                        f"- 🎯 Attractions and things to do\n\n"
                        f"When you're ready, I can help you find alternate flights!"
                    )
                    st.session_state.delay_chat.append(("assistant", intro))
                    st.rerun()
            
            with col_mode3:
                if st.button("📋 Create Full Itinerary", use_container_width=True, key="btn_itinerary"):
                    st.session_state.delay_chat.append(("user", "Create an itinerary for my trip"))
                    st.rerun()

            st.divider()

            # Display chat history
            for role, msg in st.session_state.delay_chat:
                if role == "user":
                    st.markdown(f"**🧑 You:** {msg}")
                else:
                    st.markdown(f"**🤖 Assistant:** {msg}")

            # Display flight cards if available (persists between messages)
            if st.session_state.current_alt_flights:
                st.markdown("---")
                display_all_alternate_flights(
                    alternate_flights=st.session_state.current_alt_flights,
                    dep_airport=st.session_state.current_flight_airports['departure'],
                    arr_airport=st.session_state.current_flight_airports['arrival']
                )
                st.markdown("---")

            # Chat input form with clear on submit
            with st.form("delay_chat_form", clear_on_submit=True):
                user_msg = st.text_input(
                    "Ask about flights, hotels, restaurants, attractions, or anything about your trip...",
                    key="delay_chat_input",
                )
                send = st.form_submit_button("Send", use_container_width=True)

            if send and user_msg:
                st.session_state.delay_chat.append(("user", user_msg))
                
                # 1. Detect what the user wants
                intents = detect_user_intent(user_msg)
                
                # 2. Fetch ONLY what's needed
                options = {}
                if intents:
                    intent_names = ", ".join(intents)
                    with st.spinner(f"Searching for {intent_names}..."):
                        options = get_options_for_intents(
                            intents=intents,
                            user_profile=user_data,
                            flight_context=delayed_flight
                        )
                else:
                    # No specific intent detected - just conversation
                    pass
                
                # 3. Store flights for card display if fetched
                if "alternate_flights" in options and options["alternate_flights"]:
                    st.session_state.current_alt_flights = options["alternate_flights"]
                    st.session_state.current_flight_airports = {
                        'departure': delayed_flight["departure_airport"],
                        'arrival': delayed_flight["arrival_airport"]
                    }
                
                # 4. Generate response with ONLY relevant data
                reply = build_delay_chat_reply_llm(
                    user_message=user_msg,
                    flight=delayed_flight,
                    user_profile=user_data,
                    options=options,
                    chat_history=st.session_state.delay_chat,
                    is_near_route=delayed_flight["is_near_route"],
                )
                
                st.session_state.delay_chat.append(("assistant", reply))
                st.rerun()

            # Clear chat button
            if st.session_state.delay_chat:
                if st.button("🗑️ Clear Chat", key="clear_chat"):
                    st.session_state.delay_chat = [st.session_state.delay_chat[0]]  # Keep initial greeting
                    st.session_state.current_alt_flights = None
                    st.session_state.current_flight_airports = None
                    st.rerun()

    elif page == "👤 Profile":
        st.header("👤 My Profile")

        tab1, tab2 = st.tabs(["Personal Info", "Travel Preferences"])

        with tab1:
            st.subheader("Personal Information")

            col1, col2 = st.columns(2)
            with col1:
                st.text_input("Full Name", value=user_data["FULL_NAME"], disabled=True)
                st.text_input("Email", value=user_data["EMAIL"], disabled=True)
            with col2:
                st.text_input("User ID", value=str(user_data["USER_ID"]), disabled=True)

        with tab2:
            st.subheader("Your Travel Preferences")

            col1, col2 = st.columns(2)

            with col1:
                st.write("**💰 Spending:**", user_data.get("SPENDING_PREFERENCE", "N/A"))
                st.write("**🧠 Personality:**", user_data.get("PERSONALITY_TYPE", "N/A"))
                st.write(
                    "**💺 Travel Class:**",
                    user_data.get("PREFERRED_TRAVEL_CLASS", "N/A"),
                )

            with col2:
                try:
                    attractions = user_data.get("ATTRACTION_PREFERENCES")
                    if attractions:
                        if isinstance(attractions, str):
                            attractions = json.loads(attractions)
                        st.write("**🎯 Attractions:**")
                        for attr in attractions:
                            st.write(f"• {attr}")

                    cuisines = user_data.get("CUISINE_PREFERENCES")
                    if cuisines:
                        if isinstance(cuisines, str):
                            cuisines = json.loads(cuisines)
                        st.write("**🍕 Cuisines:**")
                        for cuisine in cuisines:
                            st.write(f"• {cuisine}")
                except Exception:
                    st.write("Unable to parse preferences")

            st.info("💡 These preferences will be used for personalized recommendations!")

st.divider()
