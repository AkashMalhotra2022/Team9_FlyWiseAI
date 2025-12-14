CREATE TABLE GOLD.HOTELS_GOLD AS
SELECT
    HOTEL_UID,
    CITY,
    PLACE_ID,
    TYPES,
    FORMATTED_ADDRESS,
    LATITUDE,
    LONGITUDE,
    RATING,
    DISPLAY_NAME,
    EDITORIAL_SUMMARY,
    REVIEWS,
    REVIEWS_SUMMARY,
    PRICE_CATEGORY
FROM SILVER.HOTELS;

UPDATE GOLD.HOTELS_GOLD
SET ALL_TEXT = TRIM(
      NVL(DISPLAY_NAME, '')           || ' | '
   || NVL(FORMATTED_ADDRESS, '')      || ' | '
   || NVL(CITY, '')                   || ' | '
   || NVL(PRICE_CATEGORY, '')         || ' | '
   || NVL(TO_VARCHAR(TYPES), '')      || ' | '   -- TYPES is VARIANT
   || NVL(EDITORIAL_SUMMARY, '')      || ' | '
   || NVL(REVIEWS_SUMMARY, '')        || ' | '
   || NVL(TO_VARCHAR(REVIEWS), '')            -- REVIEWS is VARIANT
);


ALTER TABLE GOLD.HOTELS_GOLD
ADD COLUMN EMB_ALL_TEXT VECTOR(FLOAT, 768);

UPDATE GOLD.HOTELS_GOLD
SET EMB_ALL_TEXT = SNOWFLAKE.CORTEX.EMBED_TEXT_768(
    'snowflake-arctic-embed-m',
    ALL_TEXT
);


CREATE OR REPLACE PROCEDURE GOLD.POPULATE_HOTEL_EMBEDDINGS()
RETURNS STRING
LANGUAGE SQL
AS
$$
BEGIN
    UPDATE GOLD.HOTELS_GOLD
    SET
        -- 1) DISPLAY_NAME → embedding
        EMB_DISPLAY_NAME = SNOWFLAKE.CORTEX.EMBED_TEXT_768(
            'snowflake-arctic-embed-m',
            COALESCE(TO_VARCHAR(DISPLAY_NAME), '')
        ),

        -- 2) EDITORIAL_SUMMARY → embedding
        EMB_EDITORIAL_SUMMARY = SNOWFLAKE.CORTEX.EMBED_TEXT_768(
            'snowflake-arctic-embed-m',
            COALESCE(TO_VARCHAR(EDITORIAL_SUMMARY), '')
        ),

        -- 3) REVIEWS (big concatenated text) → embedding
        EMB_REVIEWS_TEXT = SNOWFLAKE.CORTEX.EMBED_TEXT_768(
            'snowflake-arctic-embed-m',
            COALESCE(TO_VARCHAR(REVIEWS), '')
        ),

        -- 4) REVIEWS_SUMMARY → embedding
        EMB_REVIEWS_SUMMARY = SNOWFLAKE.CORTEX.EMBED_TEXT_768(
            'snowflake-arctic-embed-m',
            COALESCE(TO_VARCHAR(REVIEWS_SUMMARY), '')
        ),

        -- 5) TYPES (string like: [ "hotel", "lodging", ... ]) → embedding
        EMB_TYPES_STR = SNOWFLAKE.CORTEX.EMBED_TEXT_768(
            'snowflake-arctic-embed-m',
            COALESCE(TO_VARCHAR(TYPES), '')
        );

    RETURN 'Embeddings populated using snowflake-arctic-embed-m (768 dims).';
END;
$$;
