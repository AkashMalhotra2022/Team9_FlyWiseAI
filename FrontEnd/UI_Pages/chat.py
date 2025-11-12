def get_bot_response(message: str) -> str:
    msg = (message or "").lower()
    responses = {
        "hello": "Hello! Welcome to FlyWise! ✈️ How can I assist you today?",
        "book": "Sure! Please share your departure and destination cities ✈️",
        "baggage": "Checked: 23kg, Carry-on: 7kg, Personal item allowed 🎒",
        "cancel": "To cancel a booking, please provide your reference number.",
        "help": "I can assist with bookings, flight status, baggage, and cancellations.",
    }
    for k, r in responses.items():
        if k in msg:
            return r
    return "I'm here to help! ✈️ Ask me about flights or travel policies."
