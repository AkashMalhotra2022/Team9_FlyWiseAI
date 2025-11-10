import os
import uvicorn
import asyncio
import logging
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Optional
from serpapi import GoogleSearch
from crewai import Agent, Task, Crew, Process, LLM
from datetime import datetime
from functools import lru_cache

# Load API Keys
GEMINI_API_KEY = os.getenv("GOOGLE_API_KEY", "AIzaSyClchzg2ovwisLyKB0AQrc8itcoUEtnGFo")
SERP_API_KEY = os.getenv("SERP_API_KEY", "4fa69c44938102359153f29bc4fce69aefc54b83da94f252b66f724d511f13af")

# Initialize Logger
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


# ==============================================
# 🤖 Initialize Google Gemini AI (LLM)
# ==============================================
@lru_cache(maxsize=1)
def initialize_llm():
    """Initialize and cache the LLM instance to avoid repeated initializations."""
    return LLM(
        model="gemini/gemini-2.0-flash",
        api_key=GEMINI_API_KEY
    )

# ==============================================
# 📝 Pydantic Models
# ==============================================
class UserPersona(BaseModel):
    """User persona for personalized recommendations."""
    travel_experience: str = "Adventure"  # e.g., "Art History", "Adventure", "Food & Culture"
    character_interests: str = "Extrovert"  # e.g., "Explorer & Extrovert", "Relaxation Seeker"
    spending_power: str = "High"  # "Low", "Medium", "High"


class FlightRequest(BaseModel):
    origin: str
    destination: str
    outbound_date: str
    return_date: str
    persona: Optional[UserPersona] = None
    
    def get_persona(self) -> UserPersona:
        """Get persona or return default UserPersona if None."""
        return self.persona if self.persona else UserPersona()


class HotelRequest(BaseModel):
    location: str
    check_in_date: str
    check_out_date: str
    persona: Optional[UserPersona] = None
    
    def get_persona(self) -> UserPersona:
        """Get persona or return default UserPersona if None."""
        return self.persona if self.persona else UserPersona()


class ItineraryRequest(BaseModel):
    destination: str
    check_in_date: str
    check_out_date: str
    flights: str
    hotels: str
    persona: Optional[UserPersona] = None
    
    def get_persona(self) -> UserPersona:
        """Get persona or return default UserPersona if None."""
        return self.persona if self.persona else UserPersona()


class FlightInfo(BaseModel):
    airline: str
    price: str
    duration: str
    stops: str
    departure: str
    arrival: str
    travel_class: str
    return_date: str
    airline_logo: str


class HotelInfo(BaseModel):
    name: str
    price: str
    rating: float
    location: str
    link: str


class AIResponse(BaseModel):
    flights: List[FlightInfo] = []
    hotels: List[HotelInfo] = []
    ai_flight_recommendation: str = ""
    ai_hotel_recommendation: str = ""
    itinerary: str = ""


# ==============================================
# 🚀 Initialize FastAPI
# ==============================================
app = FastAPI(title="Personalized Travel Planning API", version="2.0.0")


# ==============================================
# 💰 Helper function to extract numeric price
# ==============================================
def extract_price(price_str):
    """Extract numeric price from string for sorting."""
    try:
        # Remove currency symbols and commas, then convert to float
        cleaned = price_str.replace('$', '').replace(',', '').strip()
        return float(cleaned) if cleaned and cleaned != "N/A" else float('inf')
    except (ValueError, AttributeError):
        return float('inf')  # Put items with invalid prices at the end


# ==============================================
# 🛫 Fetch Data from SerpAPI
# ==============================================
async def run_search(params):
    """Generic function to run SerpAPI searches asynchronously."""
    try:
        return await asyncio.to_thread(lambda: GoogleSearch(params).get_dict())
    except Exception as e:
        logger.exception(f"SerpAPI search error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Search API error: {str(e)}")


async def search_flights(flight_request: FlightRequest):
    """Fetch real-time flight details from Google Flights using SerpAPI, sorted by price."""
    logger.info(f"Searching flights: {flight_request.origin} to {flight_request.destination}")

    params = {
        "api_key": SERP_API_KEY,
        "engine": "google_flights",
        "hl": "en",
        "gl": "us",
        "departure_id": flight_request.origin.strip().upper(),
        "arrival_id": flight_request.destination.strip().upper(),
        "outbound_date": flight_request.outbound_date,
        "return_date": flight_request.return_date,
        "currency": "USD"
    }

    search_results = await run_search(params)

    if "error" in search_results:
        logger.error(f"Flight search error: {search_results['error']}")
        return {"error": search_results["error"]}

    # Try both best_flights and other_flights to get more options
    all_flights = search_results.get("best_flights", []) + search_results.get("other_flights", [])
    
    if not all_flights:
        logger.warning("No flights found in search results")
        return []

    formatted_flights = []
    for flight in all_flights:
        if not flight.get("flights") or len(flight["flights"]) == 0:
            continue

        first_leg = flight["flights"][0]
        formatted_flights.append(FlightInfo(
            airline=first_leg.get("airline", "Unknown Airline"),
            price=str(flight.get("price", "N/A")),
            duration=f"{flight.get('total_duration', 'N/A')} min",
            stops="Nonstop" if len(flight["flights"]) == 1 else f"{len(flight['flights']) - 1} stop(s)",
            departure=f"{first_leg.get('departure_airport', {}).get('name', 'Unknown')} ({first_leg.get('departure_airport', {}).get('id', '???')}) at {first_leg.get('departure_airport', {}).get('time', 'N/A')}",
            arrival=f"{first_leg.get('arrival_airport', {}).get('name', 'Unknown')} ({first_leg.get('arrival_airport', {}).get('id', '???')}) at {first_leg.get('arrival_airport', {}).get('time', 'N/A')}",
            travel_class=first_leg.get("travel_class", "Economy"),
            return_date=flight_request.return_date,
            airline_logo=first_leg.get("airline_logo", "")
        ))

    # ✅ Sort flights by price (cheapest first for easier selection)
    formatted_flights.sort(key=lambda x: extract_price(x.price))
    
    logger.info(f"Found {len(formatted_flights)} flights (sorted by price)")
    return formatted_flights


async def search_hotels(hotel_request: HotelRequest):
    """Fetch hotel information from SerpAPI, sorted by price."""
    logger.info(f"Searching hotels for: {hotel_request.location}")

    # Build parameters - no rating filter, let AI choose based on spending power
    params = {
        "api_key": SERP_API_KEY,
        "engine": "google_hotels",
        "q": hotel_request.location,
        "hl": "en",
        "gl": "us",
        "check_in_date": hotel_request.check_in_date,
        "check_out_date": hotel_request.check_out_date,
        "currency": "USD",
        "sort_by": 13  # Sort by lowest price
    }
    
    logger.info(f"Hotel search params: {params}")

    search_results = await run_search(params)

    if "error" in search_results:
        logger.error(f"Hotel search error: {search_results['error']}")
        return {"error": search_results["error"]}

    hotel_properties = search_results.get("properties", [])
    if not hotel_properties:
        logger.warning("No hotels found in search results")
        return []

    formatted_hotels = []
    for hotel in hotel_properties:
        try:
            formatted_hotels.append(HotelInfo(
                name=hotel.get("name", "Unknown Hotel"),
                price=hotel.get("rate_per_night", {}).get("lowest", "N/A"),
                rating=hotel.get("overall_rating", 0.0),
                location=hotel.get("location", "N/A"),
                link=hotel.get("link", "N/A")
            ))
        except Exception as e:
            logger.warning(f"Error formatting hotel data: {str(e)}")
            continue

    # Sort hotels by price (cheapest first)
    formatted_hotels.sort(key=lambda x: extract_price(x.price))
    
    logger.info(f"Found {len(formatted_hotels)} hotels (sorted by price)")
    return formatted_hotels


# ==============================================
# 🔄 Format Data for AI
# ==============================================
def format_travel_data(data_type, data):
    """Generic formatter for both flight and hotel data."""
    if not data:
        return f"No {data_type} available."

    if data_type == "flights":
        formatted_text = "✈️ **Available flight options (sorted by price)**:\n\n"
        for i, flight in enumerate(data):
            formatted_text += (
                f"**Flight {i + 1}:**\n"
                f"✈️ **Airline:** {flight.airline}\n"
                f"💰 **Price:** ${flight.price}\n"
                f"⏱️ **Duration:** {flight.duration}\n"
                f"🛑 **Stops:** {flight.stops}\n"
                f"🕔 **Departure:** {flight.departure}\n"
                f"🕖 **Arrival:** {flight.arrival}\n"
                f"💺 **Class:** {flight.travel_class}\n\n"
            )
    elif data_type == "hotels":
        formatted_text = "🏨 **Available Hotel Options (sorted by price)**:\n\n"
        for i, hotel in enumerate(data):
            formatted_text += (
                f"**Hotel {i + 1}:**\n"
                f"🏨 **Name:** {hotel.name}\n"
                f"💰 **Price:** ${hotel.price}\n"
                f"⭐ **Rating:** {hotel.rating}\n"
                f"📍 **Location:** {hotel.location}\n"
                f"🔗 **More Info:** [Link]({hotel.link})\n\n"
            )
    else:
        return "Invalid data type."

    return formatted_text.strip()


# ==============================================
# 🧠 AI Analysis Functions
# ==============================================
def generate_persona_context(persona: UserPersona) -> str:
    """Generate context string from user persona."""
    return f"""
**User Profile:**
- **Travel Experience Focus:** {persona.travel_experience}
- **Character & Interests:** {persona.character_interests}
- **Spending Power:** {persona.spending_power}
"""


async def get_ai_recommendation(data_type, formatted_data, persona: Optional[UserPersona] = None):
    """Unified function for getting AI recommendations for both flights and hotels."""
    logger.info(f"Getting {data_type} analysis from AI")
    llm_model = initialize_llm()
    
    # Use default persona if none provided
    if persona is None:
        persona = UserPersona()
    
    persona_context = generate_persona_context(persona)
    
    # Determine spending tier and recommendation strategy
    spending_power = persona.spending_power
    
    if spending_power == "Low":
        recommendation_focus = "cheapest"
        recommended_option = "Flight 1 (Cheapest)" if data_type == "flights" else "Hotel 1 (Cheapest)"
        value_criteria = "absolute lowest price and maximum savings"
    elif spending_power == "High":
        recommendation_focus = "premium"
        recommended_option = "the best premium option" if data_type == "flights" else "the best premium hotel"
        value_criteria = "best quality, convenience, and premium experience regardless of price"
    else:  # Medium
        recommendation_focus = "best value"
        recommended_option = "the best value option" if data_type == "flights" else "the best value hotel"
        value_criteria = "optimal balance of price, quality, and convenience"

    # Configure agent based on data type
    if data_type == "flights":
        role = "AI Flight Analyst"
        goal = f"Recommend the {recommendation_focus} flight option that matches the user's {spending_power} spending power while considering their persona and preferences."
        backstory = f"AI expert that helps travelers find flight options perfectly suited to their budget tier and travel style."
        description = f"""
        {persona_context}

        Based on the user's **{spending_power}** spending power, analyze the flights and recommend {recommended_option}.

        **Selection Criteria for {spending_power} Spending Power:**
        - Focus on: {value_criteria}
        {"- Prioritize: Cheapest price, willing to accept longer durations and more stops" if spending_power == "Low" else ""}
        {"- Prioritize: Balance of reasonable price with good duration and minimal stops" if spending_power == "Medium" else ""}
        {"- Prioritize: Best airlines, shortest duration, nonstop flights, premium classes" if spending_power == "High" else ""}

        **🎯 Your Recommendation: {recommended_option}**

        Provide analysis in this format:

        **💰 Price Analysis:**
        - Explain why this flight matches their {spending_power} spending power
        - Compare pricing across available options
        {"- Emphasize cost savings and affordability" if spending_power == "Low" else ""}
        {"- Highlight value for money and reasonable pricing" if spending_power == "Medium" else ""}
        {"- Justify the premium price with superior features" if spending_power == "High" else ""}

        **⏱️ Duration & Convenience:**
        - Analyze flight duration relative to price tier
        - Discuss stops and connections
        - Consider travel time and convenience
        {"- Accept trade-offs in duration for savings" if spending_power == "Low" else ""}
        {"- Balance duration with reasonable pricing" if spending_power == "Medium" else ""}
        {"- Emphasize time-saving and convenience" if spending_power == "High" else ""}

        **✈️ Airline & Service Quality:**
        - Comment on airline reputation and service
        - Discuss travel class and amenities
        - Consider overall flight experience

        **✨ Personal Fit:**
        - Explain how this flight aligns with their character ({persona.character_interests})
        - Connect to their interests in {persona.travel_experience}

        **✅ Why This is the Best Choice for {spending_power} Budget:**
        - Summarize the recommendation
        - Justify based on their spending tier
        - Provide confidence in selection

        **Important:** Recommend the option that best matches {spending_power} spending power. Be concise and personalized.
        """
    elif data_type == "hotels":
        role = "AI Hotel Analyst"
        goal = f"Recommend the {recommendation_focus} hotel option that matches the user's {spending_power} spending power while considering their interests."
        backstory = f"AI expert that helps travelers find accommodation perfectly suited to their budget tier and personality."
        description = f"""
        {persona_context}

        Based on the user's **{spending_power}** spending power, analyze the hotels and recommend {recommended_option}.

        **Selection Criteria for {spending_power} Spending Power:**
        - Focus on: {value_criteria}
        {"- Prioritize: Lowest price, acceptable basic amenities and location" if spending_power == "Low" else ""}
        {"- Prioritize: Good balance of price with solid ratings and convenient location" if spending_power == "Medium" else ""}
        {"- Prioritize: Luxury hotels, premium amenities, prime locations, highest ratings" if spending_power == "High" else ""}

        **🎯 Your Recommendation: {recommended_option}**

        Provide analysis in this format:

        **💰 Price Analysis:**
        - Explain why this hotel matches their {spending_power} spending power
        - Compare pricing across available options
        {"- Emphasize affordability and cost savings" if spending_power == "Low" else ""}
        {"- Highlight value proposition and reasonable pricing" if spending_power == "Medium" else ""}
        {"- Justify premium pricing with luxury features" if spending_power == "High" else ""}

        **⭐ Rating & Quality:**
        - Discuss the hotel's rating in context of price tier
        - Comment on guest satisfaction
        - Analyze overall quality
        {"- Note acceptable quality for budget tier" if spending_power == "Low" else ""}
        {"- Emphasize solid quality for the price" if spending_power == "Medium" else ""}
        {"- Highlight exceptional quality and luxury" if spending_power == "High" else ""}

        **📍 Location Benefits:**
        - Describe the hotel's location
        - Highlight proximity to {persona.travel_experience} attractions
        - Discuss convenience for an {persona.character_interests} traveler
        - Mention nearby activities matching their interests

        **🛋️ Amenities & Experience:**
        - Detail amenities relevant to their budget tier
        - Discuss features that appeal to someone interested in {persona.travel_experience}
        - Consider their personality type ({persona.character_interests})

        **✨ Personal Fit:**
        - Explain how this hotel suits their character
        - Connect amenities to their interests
        - Consider social aspects for their personality

        **✅ Why This is the Best Choice for {spending_power} Budget:**
        - Summarize the recommendation
        - Justify based on their spending tier
        - Provide confidence in selection

        **Important:** Recommend the option that best matches {spending_power} spending power. Be concise and personalized.
        """
    else:
        raise ValueError("Invalid data type for AI recommendation")

    # Create the agent and task
    analyze_agent = Agent(
        role=role,
        goal=goal,
        backstory=backstory,
        llm=llm_model,
        verbose=False
    )

    analyze_task = Task(
        description=f"{description}\n\nData to analyze:\n{formatted_data}",
        agent=analyze_agent,
        expected_output=f"A structured, personalized recommendation explaining why the cheapest {data_type} option is the best choice."
    )

    analyst_crew = Crew(
        agents=[analyze_agent],
        tasks=[analyze_task],
        process=Process.sequential,
        verbose=False
    )

    try:
        crew_results = await asyncio.to_thread(analyst_crew.kickoff)

        if hasattr(crew_results, 'outputs') and crew_results.outputs:
            return crew_results.outputs[0]
        elif hasattr(crew_results, 'get'):
            return crew_results.get(role, f"No {data_type} recommendation available.")
        else:
            return str(crew_results)
    except Exception as e:
        logger.exception(f"Error in AI {data_type} analysis: {str(e)}")
        return f"Unable to generate {data_type} recommendation due to an error."


async def generate_itinerary(destination, flights_text, hotels_text, check_in_date, check_out_date, persona: Optional[UserPersona] = None):
    """Generate a detailed travel itinerary based on flight and hotel information."""
    try:
        check_in = datetime.strptime(check_in_date, "%Y-%m-%d")
        check_out = datetime.strptime(check_out_date, "%Y-%m-%d")
        days = (check_out - check_in).days

        llm_model = initialize_llm()
        
        # Use default persona if none provided
        if persona is None:
            persona = UserPersona()
        
        persona_context = generate_persona_context(persona)
        
        # Customize itinerary style based on persona
        if "art" in persona.travel_experience.lower() or "history" in persona.travel_experience.lower():
            activity_focus = "art museums, historical sites, cultural landmarks, galleries, and architectural tours"
        elif "adventure" in persona.travel_experience.lower():
            activity_focus = "outdoor activities, hiking, adventure sports, nature experiences"
        elif "food" in persona.travel_experience.lower():
            activity_focus = "local food markets, authentic restaurants, cooking classes, food tours"
        else:
            activity_focus = "popular attractions, local experiences, and cultural sites"
        
        if "explorer" in persona.character_interests.lower() and "extrovert" in persona.character_interests.lower():
            social_style = "Include social activities, group tours, local meetups, and vibrant social venues. Suggest busy, lively areas and opportunities to meet people."
        elif "introvert" in persona.character_interests.lower():
            social_style = "Focus on peaceful, quiet experiences, self-guided tours, and less crowded times. Suggest serene locations."
        elif "relaxation" in persona.character_interests.lower():
            social_style = "Emphasize relaxing activities, spa recommendations, peaceful parks, and leisurely experiences."
        else:
            social_style = "Balance between active exploration and relaxation time."
        
        # Spending power guidance
        if persona.spending_power == "Low":
            spending_guidance = "Focus on FREE activities and budget-friendly options. Prioritize no-cost attractions, affordable local eateries, and public transportation."
            activity_cost_level = "free or under $20"
            daily_budget_estimate = "Estimate $30-50 per day for food, activities, and local transportation"
        elif persona.spending_power == "High":
            spending_guidance = "Include premium experiences, fine dining, guided tours, and luxury activities. Price is not a primary concern."
            activity_cost_level = "premium experiences at any price point"
            daily_budget_estimate = "Estimate $200-400 per day for food, activities, and transportation"
        else:  # Medium
            spending_guidance = "Balance cost with experience quality. Mix free attractions with reasonably priced activities and mid-range dining."
            activity_cost_level = "mix of free and moderately priced ($20-50)"
            daily_budget_estimate = "Estimate $80-150 per day for food, activities, and transportation"

        analyze_agent = Agent(
            role="AI Travel Planner",
            goal=f"Create a personalized {persona.spending_power} itinerary with complete budget breakdown tailored to the user's interests in {persona.travel_experience}",
            backstory=f"AI travel expert specialized in creating personalized travel plans with accurate budget calculations that match the traveler's personality, interests, and {persona.spending_power} spending power.",
            llm=llm_model,
            verbose=False
        )

        analyze_task = Task(
            description=f"""
            {persona_context}

            Based on the following details, create a {days}-day personalized itinerary with complete budget breakdown:

            **Flight Details** (Selected based on {persona.spending_power} spending power):
            {flights_text}

            **Hotel Details** (Selected based on {persona.spending_power} spending power):
            {hotels_text}

            **Destination**: {destination}

            **Travel Dates**: {check_in_date} to {check_out_date} ({days} days, {days} nights)

            **Personalization Requirements:**
            - The traveler is interested in: {activity_focus}
            - Travel style: {social_style}
            - Spending Power: **{persona.spending_power}**
            - {spending_guidance}
            - Suggest activities that are: {activity_cost_level}
            - {daily_budget_estimate}

            Create an itinerary that includes:
            - Flight arrival and departure information
            - Hotel check-in and check-out details
            - Day-by-day breakdown prioritizing {activity_focus}
            - Activities appropriate for {persona.spending_power} spending power
            - Specific recommendations for {persona.travel_experience} enthusiasts
            - {social_style}
            - Restaurant recommendations matching their budget tier
            - Transportation tips suitable for their spending level
            - Money-saving OR premium experience tips (based on spending power)
            - Special tips for {persona.character_interests}
            
            **CRITICAL: Budget Calculation Section**
            At the END of the itinerary, you MUST include a comprehensive budget breakdown section with:
            
            ## 💰 Total Trip Budget Breakdown
            
            ### Fixed Costs:
            - **Flight (Round Trip):** Extract the exact price from the flight details above and format as $XXX
            - **Hotel ({days} nights):** Extract the per-night rate from hotel details, multiply by {days}, format as $XXX × {days} = $XXX total
            
            ### Estimated Variable Costs:
            - **Daily Food & Dining:** Estimate based on {persona.spending_power} spending power × {days} days
            - **Activities & Attractions:** Estimate based on planned activities and {persona.spending_power} level × {days} days  
            - **Local Transportation:** Estimate for {days} days based on {persona.spending_power} level
            - **Miscellaneous:** 10-15% buffer for unexpected expenses
            
            ### 🎯 Grand Total Estimated Budget:
            **$X,XXX - $X,XXX USD** (provide a realistic range)
            
            Include specific dollar amounts for each category. Be realistic and accurate with the calculations.

            📝 **Format Requirements**:
            - Use markdown formatting with clear headings (# for main, ## for days, ### for sections)
            - Include relevant emojis (🎨 for art, 🏛️ for history, 🍽️ for food, 👥 for social, 💰 for budget items, 💎 for premium items)
            - Use bullet points for activities
            - Include estimated costs for each activity
            - Clearly indicate: {"🆓 for FREE activities, 💵 for budget options" if persona.spending_power == "Low" else "💵 for moderate costs, 💰 for premium" if persona.spending_power == "Medium" else "💎 for luxury experiences"}
            - Add personality notes that match their character ({persona.character_interests})
            - Make it visually appealing and easy to follow
            - Tailor the pace and style to their personality and budget tier
            - **MUST end with the complete budget breakdown section with actual calculations**
            """,
            agent=analyze_agent,
            expected_output=f"A well-structured, personalized itinerary in markdown format that perfectly matches the user's interests, character, and {persona.spending_power} spending power, with a detailed budget breakdown at the end showing total estimated trip cost."
        )

        itinerary_planner_crew = Crew(
            agents=[analyze_agent],
            tasks=[analyze_task],
            process=Process.sequential,
            verbose=False
        )

        crew_results = await asyncio.to_thread(itinerary_planner_crew.kickoff)

        if hasattr(crew_results, 'outputs') and crew_results.outputs:
            return crew_results.outputs[0]
        elif hasattr(crew_results, 'get'):
            return crew_results.get("AI Travel Planner", "No itinerary available.")
        else:
            return str(crew_results)

    except Exception as e:
        logger.exception(f"Error generating itinerary: {str(e)}")
        return "Unable to generate itinerary due to an error. Please try again later."


# ==============================================
# 🚀 API Endpoints
# ==============================================
@app.post("/search_flights/", response_model=AIResponse)
async def get_flight_recommendations(flight_request: FlightRequest):
    """Search flights and get AI recommendation (based on spending power) with personalization."""
    try:
        flights = await search_flights(flight_request)

        if isinstance(flights, dict) and "error" in flights:
            raise HTTPException(status_code=400, detail=flights["error"])

        if not flights:
            raise HTTPException(status_code=404, detail="No flights found")

        flights_text = format_travel_data("flights", flights)
        # Use get_persona() to ensure we always have a persona with defaults
        ai_recommendation = await get_ai_recommendation("flights", flights_text, flight_request.get_persona())

        return AIResponse(
            flights=flights,
            ai_flight_recommendation=ai_recommendation
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Flight search endpoint error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Flight search error: {str(e)}")


@app.post("/search_hotels/", response_model=AIResponse)
async def get_hotel_recommendations(hotel_request: HotelRequest):
    """Search hotels and get AI recommendation (based on spending power) with personalization."""
    try:
        hotels = await search_hotels(hotel_request)

        if isinstance(hotels, dict) and "error" in hotels:
            raise HTTPException(status_code=400, detail=hotels["error"])

        if not hotels:
            raise HTTPException(status_code=404, detail="No hotels found")

        hotels_text = format_travel_data("hotels", hotels)
        # Use get_persona() to ensure we always have a persona with defaults
        ai_recommendation = await get_ai_recommendation("hotels", hotels_text, hotel_request.get_persona())

        return AIResponse(
            hotels=hotels,
            ai_hotel_recommendation=ai_recommendation
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Hotel search endpoint error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Hotel search error: {str(e)}")


@app.post("/complete_search/", response_model=AIResponse)
async def complete_travel_search(flight_request: FlightRequest, hotel_request: Optional[HotelRequest] = None):
    """Search for flights and hotels with personalized recommendations based on spending power."""
    try:
        # If hotel request is not provided, create one from flight request (and copy persona)
        if hotel_request is None:
            hotel_request = HotelRequest(
                location=flight_request.destination,
                check_in_date=flight_request.outbound_date,
                check_out_date=flight_request.return_date,
                persona=flight_request.persona
            )

        flight_task = asyncio.create_task(get_flight_recommendations(flight_request))
        hotel_task = asyncio.create_task(get_hotel_recommendations(hotel_request))

        flight_results, hotel_results = await asyncio.gather(flight_task, hotel_task, return_exceptions=True)

        if isinstance(flight_results, Exception):
            logger.error(f"Flight search failed: {str(flight_results)}")
            flight_results = AIResponse(flights=[], ai_flight_recommendation="Could not retrieve flights.")

        if isinstance(hotel_results, Exception):
            logger.error(f"Hotel search failed: {str(hotel_results)}")
            hotel_results = AIResponse(hotels=[], ai_hotel_recommendation="Could not retrieve hotels.")

        flights_text = format_travel_data("flights", flight_results.flights)
        hotels_text = format_travel_data("hotels", hotel_results.hotels)

        itinerary = ""
        if flight_results.flights and hotel_results.hotels:
            # Use get_persona() to ensure we always have a persona with defaults
            itinerary = await generate_itinerary(
                destination=flight_request.destination,
                flights_text=flights_text,
                hotels_text=hotels_text,
                check_in_date=flight_request.outbound_date,
                check_out_date=flight_request.return_date,
                persona=flight_request.get_persona()
            )

        return AIResponse(
            flights=flight_results.flights,
            hotels=hotel_results.hotels,
            ai_flight_recommendation=flight_results.ai_flight_recommendation,
            ai_hotel_recommendation=hotel_results.ai_hotel_recommendation,
            itinerary=itinerary
        )
    except Exception as e:
        logger.exception(f"Complete travel search error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Travel search error: {str(e)}")


@app.post("/generate_itinerary/", response_model=AIResponse)
async def get_itinerary(itinerary_request: ItineraryRequest):
    """Generate a personalized itinerary based on spending power."""
    try:
        # Use get_persona() to ensure we always have a persona with defaults
        itinerary = await generate_itinerary(
            destination=itinerary_request.destination,
            flights_text=itinerary_request.flights,
            hotels_text=itinerary_request.hotels,
            check_in_date=itinerary_request.check_in_date,
            check_out_date=itinerary_request.check_out_date,
            persona=itinerary_request.get_persona()
        )

        return AIResponse(itinerary=itinerary)
    except Exception as e:
        logger.exception(f"Itinerary generation error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Itinerary generation error: {str(e)}")


# ==============================================
# 🌐 Run FastAPI Server
# ==============================================
if __name__ == "__main__":
    logger.info("Starting Personalized Travel Planning API server")
    uvicorn.run(app, host="0.0.0.0", port=8000)