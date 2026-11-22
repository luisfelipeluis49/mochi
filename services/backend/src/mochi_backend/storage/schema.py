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
    # --- The company's learning history (DECISIONS D-45; docs/TEAM_VIEW.md) -------------------
    # One company per deployment today, but every row says whose it is, so that can change.
    """
    CREATE TABLE IF NOT EXISTS companies (
        company_id text PRIMARY KEY,
        name text NOT NULL,
        created_at timestamptz NOT NULL DEFAULT now()
    )
    """,
    # A person may belong to several companies; `role` is admin (sees the team view) or member.
    """
    CREATE TABLE IF NOT EXISTS company_members (
        company_id text NOT NULL REFERENCES companies (company_id) ON DELETE CASCADE,
        user_id text NOT NULL REFERENCES users (user_id) ON DELETE CASCADE,
        role text NOT NULL,
        team text,
        joined_at timestamptz NOT NULL DEFAULT now(),
        PRIMARY KEY (company_id, user_id)
    )
    """,
    # One row per session, Start to Stop: a meeting or a review. No sentence is kept here; `body`
    # (the SessionRecord) holds who was there and how many sentences each recognised voice said.
    """
    CREATE TABLE IF NOT EXISTS session_records (
        record_id text PRIMARY KEY,
        seq bigserial NOT NULL,
        company_id text NOT NULL REFERENCES companies (company_id) ON DELETE CASCADE,
        session_id text NOT NULL,
        mode text NOT NULL,
        started_at timestamptz NOT NULL,
        ended_at timestamptz,
        body jsonb NOT NULL
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS session_records_by_company
        ON session_records (company_id, started_at)
    """,
    # The fact table of the analytics: one row per time someone needed a word (a hint shown or an
    # answer spoken). A learning event is one card per person and word; this is every occurrence.
    # `record_id` is not a foreign key on purpose: a moment must survive its session's row.
    """
    CREATE TABLE IF NOT EXISTS word_moments (
        moment_id text PRIMARY KEY,
        seq bigserial NOT NULL,
        company_id text NOT NULL REFERENCES companies (company_id) ON DELETE CASCADE,
        record_id text,
        user_id text REFERENCES users (user_id) ON DELETE SET NULL,
        expression text NOT NULL,
        target_language text NOT NULL,
        reason text NOT NULL,
        at timestamptz NOT NULL,
        body jsonb NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS word_moments_by_company ON word_moments (company_id, at)",
    # What was said, sentence by sentence, and whose registered voice said it (DECISIONS D-46).
    # `user_id` is null when no known voice said it. A person reads their own sentences only.
    """
    CREATE TABLE IF NOT EXISTS utterances (
        utterance_id text PRIMARY KEY,
        seq bigserial NOT NULL,
        company_id text NOT NULL REFERENCES companies (company_id) ON DELETE CASCADE,
        record_id text,
        user_id text REFERENCES users (user_id) ON DELETE SET NULL,
        at timestamptz NOT NULL,
        body jsonb NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS utterances_by_record ON utterances (record_id, seq)",
    "CREATE INDEX IF NOT EXISTS utterances_by_user ON utterances (user_id, at)",
    # What Mochi noticed in one person's speech in one session, written after it stopped
    # (DECISIONS D-54). It holds that person's own sentences: only they read it. A person who is
    # removed takes their reports along (ON DELETE CASCADE): a report has no other reader.
    """
    CREATE TABLE IF NOT EXISTS conversation_reports (
        report_id text PRIMARY KEY,
        seq bigserial NOT NULL,
        company_id text NOT NULL REFERENCES companies (company_id) ON DELETE CASCADE,
        record_id text,
        user_id text NOT NULL REFERENCES users (user_id) ON DELETE CASCADE,
        ended_at timestamptz NOT NULL,
        body jsonb NOT NULL
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS conversation_reports_by_user
        ON conversation_reports (user_id, ended_at)
    """,
    """
    CREATE INDEX IF NOT EXISTS word_moments_by_expression
        ON word_moments (company_id, lower(expression))
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
UPSERT_USER = """
    INSERT INTO users (user_id, display_name, comfortable_languages, target_language)
    VALUES (%s, %s, %s, %s)
    ON CONFLICT (user_id) DO UPDATE SET
        display_name = EXCLUDED.display_name,
        comfortable_languages = EXCLUDED.comfortable_languages,
        target_language = EXCLUDED.target_language, updated_at = now()
"""
INSERT_COMPANY = "INSERT INTO companies (company_id, name) VALUES (%s, %s) ON CONFLICT DO NOTHING"
SELECT_COMPANIES = "SELECT company_id, name FROM companies ORDER BY created_at, company_id"
INSERT_MEMBER = """
    INSERT INTO company_members (company_id, user_id, role, team)
    VALUES (%s, %s, %s, %s) ON CONFLICT DO NOTHING
"""
UPSERT_MEMBER = """
    INSERT INTO company_members (company_id, user_id, role, team)
    VALUES (%s, %s, %s, %s)
    ON CONFLICT (company_id, user_id) DO UPDATE SET role = EXCLUDED.role, team = EXCLUDED.team
"""
SELECT_MEMBERS = (
    "SELECT company_id, user_id, role, team FROM company_members ORDER BY joined_at, user_id"
)
UPSERT_RECORD = """
    INSERT INTO session_records
        (record_id, company_id, session_id, mode, started_at, ended_at, body)
    VALUES (%s, %s, %s, %s, %s::timestamptz, %s::timestamptz, %s::jsonb)
    ON CONFLICT (record_id) DO UPDATE SET ended_at = EXCLUDED.ended_at, body = EXCLUDED.body
"""
SELECT_RECORDS = "SELECT record_id, body::text FROM session_records ORDER BY seq"
INSERT_MOMENT = """
    INSERT INTO word_moments
        (moment_id, company_id, record_id, user_id, expression, target_language, reason, at, body)
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s::timestamptz, %s::jsonb)
    ON CONFLICT (moment_id) DO NOTHING
"""
SELECT_MOMENTS = "SELECT moment_id, body::text FROM word_moments ORDER BY seq"
UPSERT_UTTERANCE = """
    INSERT INTO utterances (utterance_id, company_id, record_id, user_id, at, body)
    VALUES (%s, %s, %s, %s, %s::timestamptz, %s::jsonb)
    ON CONFLICT (utterance_id) DO UPDATE SET user_id = EXCLUDED.user_id, body = EXCLUDED.body
"""
SELECT_UTTERANCES = "SELECT utterance_id, body::text FROM utterances ORDER BY seq"
DELETE_UTTERANCES = "DELETE FROM utterances"
INSERT_REPORT = """
    INSERT INTO conversation_reports (report_id, company_id, record_id, user_id, ended_at, body)
    VALUES (%s, %s, %s, %s, %s::timestamptz, %s::jsonb)
    ON CONFLICT (report_id) DO NOTHING
"""
SELECT_REPORTS = "SELECT report_id, body::text FROM conversation_reports ORDER BY seq"
DELETE_REPORTS = "DELETE FROM conversation_reports"
DELETE_MOMENTS = "DELETE FROM word_moments"
DELETE_RECORDS = "DELETE FROM session_records"
