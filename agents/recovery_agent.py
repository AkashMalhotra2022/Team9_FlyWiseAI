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
