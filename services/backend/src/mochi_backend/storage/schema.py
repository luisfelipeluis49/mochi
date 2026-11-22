"""The tables, created with IF NOT EXISTS at startup (no migration tool; DECISIONS D-32)."""

CREATE_TABLES = (
    """
    CREATE TABLE IF NOT EXISTS users (
        user_id text PRIMARY KEY,
        display_name text NOT NULL,
        comfortable_languages text[] NOT NULL,
        target_language text NOT NULL,
        created_at timestamptz NOT NULL DEFAULT now(),
        updated_at timestamptz NOT NULL DEFAULT now()
    )
    """,
    # `body` is the whole LearningEvent as the contract defines it, so a contract change never
    # needs a column change; the other columns are for looking at the table by hand.
    """
    CREATE TABLE IF NOT EXISTS learning_events (
        learning_event_id text PRIMARY KEY,
        seq bigserial NOT NULL,
        user_id text REFERENCES users (user_id) ON DELETE SET NULL,
        expression text NOT NULL,
        learning_state text NOT NULL,
        body jsonb NOT NULL,
        updated_at timestamptz NOT NULL DEFAULT now()
    )
    """,
    # One device (home_pi_01) today, so the voice name alone is the key (case-insensitive).
    # `voiceprint` is biometric data: only the device-key voices routes ever read it.
    """
    CREATE TABLE IF NOT EXISTS voices (
        name_key text PRIMARY KEY,
        name text NOT NULL,
        user_id text REFERENCES users (user_id) ON DELETE SET NULL,
        language text NOT NULL,
        voiceprint double precision[],
        saved text,
        updated_at timestamptz NOT NULL DEFAULT now()
    )
    """,
    # One finished web session of one person (D-42). Last: it references `users`. `body` is the
    # whole SessionRecord; the other columns are for looking at the table by hand.
    """
    CREATE TABLE IF NOT EXISTS session_records (
        record_id text PRIMARY KEY,
        user_id text REFERENCES users (user_id) ON DELETE CASCADE,
        session_id text NOT NULL,
        started_at timestamptz NOT NULL,
        ended_at timestamptz NOT NULL,
        body jsonb NOT NULL
    )
    """,
)

INSERT_USER = """
    INSERT INTO users (user_id, display_name, comfortable_languages, target_language)
    VALUES (%s, %s, %s, %s) ON CONFLICT (user_id) DO NOTHING
"""
SELECT_USERS = (
    "SELECT user_id, display_name, comfortable_languages, target_language "
    "FROM users ORDER BY created_at, user_id"
)
UPSERT_EVENT = """
    INSERT INTO learning_events (learning_event_id, user_id, expression, learning_state, body)
    VALUES (%s, %s, %s, %s, %s::jsonb)
    ON CONFLICT (learning_event_id) DO UPDATE SET
        user_id = EXCLUDED.user_id, expression = EXCLUDED.expression,
        learning_state = EXCLUDED.learning_state, body = EXCLUDED.body, updated_at = now()
"""
SELECT_EVENTS = "SELECT learning_event_id, body::text FROM learning_events ORDER BY seq"
DELETE_EVENTS = "DELETE FROM learning_events"
UPSERT_VOICE = """
    INSERT INTO voices (name_key, name, user_id, language, voiceprint, saved)
    VALUES (%s, %s, %s, %s, %s, %s)
    ON CONFLICT (name_key) DO UPDATE SET
        name = EXCLUDED.name, user_id = EXCLUDED.user_id, language = EXCLUDED.language,
        voiceprint = EXCLUDED.voiceprint, saved = EXCLUDED.saved, updated_at = now()
"""
SELECT_VOICES = "SELECT name, user_id, language, voiceprint, saved FROM voices ORDER BY name_key"
DELETE_VOICE = "DELETE FROM voices WHERE name_key = %s"
INSERT_SESSION = """
    INSERT INTO session_records (record_id, user_id, session_id, started_at, ended_at, body)
    VALUES (%s, %s, %s, %s, %s, %s::jsonb) ON CONFLICT (record_id) DO NOTHING
"""
SELECT_SESSIONS = "SELECT record_id, body::text FROM session_records ORDER BY ended_at, record_id"
