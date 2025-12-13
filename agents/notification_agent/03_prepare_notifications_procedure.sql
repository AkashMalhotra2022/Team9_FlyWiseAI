USE SCHEMA FLYWISE_AI_DB.GOLD;

CREATE OR REPLACE PROCEDURE GOLD.PREPARE_FLIGHT_NOTIFICATIONS()
RETURNS STRING
LANGUAGE SQL
AS
$$
BEGIN
    -- 1️⃣ Insert new notification messages into OUTBOX
    INSERT INTO GOLD.FLIGHT_NOTIFICATIONS_OUTBOX (
        FLIGHT_ID,
        FLIGHT_IATA,
        AIRLINE_NAME,
        DEPARTURE_IATA,
        ARRIVAL_IATA,
        DEPARTURE_DATE,
        DEPARTURE_TIME,
        CURRENT_DELAY_MIN,
        MESSAGE_TEXT
    )
    SELECT
        f.FLIGHT_ID,
        f.FLIGHT_IATA,
        f.AIRLINE_NAME,
        f.DEPARTURE_IATA,
        f.ARRIVAL_IATA,
        f.DEPARTURE_DATE,
        f.DEPARTURE_TIME,
        TRY_TO_NUMBER(f.DEPARTURE_DELAY),
        AI_COMPLETE(
            'MISTRAL-LARGE2',
            'You are a helpful airline notification assistant. ' ||
            'Write a short, clear message to a passenger about a flight delay. ' ||
            'Flight: ' || f.FLIGHT_IATA || ' operated by ' || f.AIRLINE_NAME || '. ' ||
            'Route: ' || f.DEPARTURE_IATA || ' to ' || f.ARRIVAL_IATA || '. ' ||
            'Scheduled departure: ' ||
                TO_CHAR(f.DEPARTURE_DATE, 'YYYY-MM-DD') || ' at ' ||
                TO_CHAR(f.DEPARTURE_TIME, 'HH24:MI') || '. ' ||
            'Current delay: ' || TRY_TO_NUMBER(f.DEPARTURE_DELAY) || ' minutes. ' ||
            'Say it in 2–3 short sentences, friendly and concise. ' ||
            'Do NOT include greeting or signature.'
        )
    FROM GOLD.GOLD_FLIGHT_DATA f
    WHERE TRY_TO_NUMBER(f.DEPARTURE_DELAY) >= 40
      AND (
            f.LAST_NOTIFIED_DELAY IS NULL
            OR TRY_TO_NUMBER(f.DEPARTURE_DELAY) > f.LAST_NOTIFIED_DELAY
          );

    -- 2️⃣ Update flight table to prevent duplicate notifications
    UPDATE GOLD.GOLD_FLIGHT_DATA
    SET
        LAST_NOTIFIED_DELAY = TRY_TO_NUMBER(DEPARTURE_DELAY),
        LAST_NOTIFIED_AT    = CURRENT_TIMESTAMP,
        NOTIFY_STATUS       = 'QUEUED',
        NOTIFY_TS           = CURRENT_TIMESTAMP
    WHERE TRY_TO_NUMBER(DEPARTURE_DELAY) >= 40
      AND (
            LAST_NOTIFIED_DELAY IS NULL
            OR TRY_TO_NUMBER(DEPARTURE_DELAY) > LAST_NOTIFIED_DELAY
          );

    RETURN 'Notification agent executed successfully.';
END;
$$;
