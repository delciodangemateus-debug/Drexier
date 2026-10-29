-- Drexier: authentication-code storage and atomic verification for Supabase.
-- Run this additive migration in SQL Editor when the existing project already
-- has the main Drexier schema installed.

CREATE TABLE IF NOT EXISTS public.auth_challenges (
    challenge_id TEXT PRIMARY KEY CHECK (challenge_id ~ '^[0-9a-f]{32}$'),
    code_hash TEXT NOT NULL CHECK (code_hash ~ '^[0-9a-f]{64}$'),
    purpose TEXT NOT NULL CHECK (purpose IN ('signup', 'login')),
    payload JSONB NOT NULL,
    attempts INTEGER NOT NULL DEFAULT 0 CHECK (attempts BETWEEN 0 AND 4),
    expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT TIMEZONE('utc'::text, NOW())
);

CREATE INDEX IF NOT EXISTS idx_auth_challenges_expires_at
    ON public.auth_challenges(expires_at);

ALTER TABLE public.auth_challenges ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.auth_challenges FROM PUBLIC, anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.auth_challenges TO service_role;

CREATE OR REPLACE FUNCTION public.consume_auth_challenge(
    p_challenge_id TEXT,
    p_code_hash TEXT,
    p_purpose TEXT
)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
    challenge public.auth_challenges%ROWTYPE;
BEGIN
    SELECT * INTO challenge
    FROM public.auth_challenges
    WHERE challenge_id = p_challenge_id
    FOR UPDATE;

    IF NOT FOUND OR challenge.purpose <> p_purpose THEN
        RETURN NULL;
    END IF;

    IF challenge.expires_at <= NOW() THEN
        DELETE FROM public.auth_challenges WHERE challenge_id = p_challenge_id;
        RETURN NULL;
    END IF;

    IF challenge.code_hash <> p_code_hash THEN
        IF challenge.attempts + 1 >= 5 THEN
            DELETE FROM public.auth_challenges WHERE challenge_id = p_challenge_id;
        ELSE
            UPDATE public.auth_challenges
            SET attempts = attempts + 1
            WHERE challenge_id = p_challenge_id;
        END IF;
        RETURN NULL;
    END IF;

    DELETE FROM public.auth_challenges WHERE challenge_id = p_challenge_id;
    RETURN challenge.payload;
END;
$$;

REVOKE ALL ON FUNCTION public.consume_auth_challenge(TEXT, TEXT, TEXT)
    FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.consume_auth_challenge(TEXT, TEXT, TEXT)
    TO service_role;
