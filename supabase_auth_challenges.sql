-- Drexier: authentication-code storage, lockout, and atomic verification.
-- Run this additive migration in SQL Editor when the main Drexier schema exists.

CREATE TABLE IF NOT EXISTS public.auth_challenges (
    challenge_id TEXT PRIMARY KEY CHECK (challenge_id ~ '^[0-9a-f]{32}$'),
    code_hash TEXT NOT NULL CHECK (code_hash ~ '^[0-9a-f]{64}$'),
    email TEXT,
    purpose TEXT NOT NULL,
    payload JSONB NOT NULL,
    attempts INTEGER NOT NULL DEFAULT 0,
    expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT TIMEZONE('utc'::text, NOW())
);

ALTER TABLE public.auth_challenges
    ADD COLUMN IF NOT EXISTS email TEXT;

UPDATE public.auth_challenges
SET email = LOWER(TRIM(payload->>'email'))
WHERE email IS NULL;

ALTER TABLE public.auth_challenges
    ALTER COLUMN email SET NOT NULL;

ALTER TABLE public.auth_challenges
    DROP CONSTRAINT IF EXISTS auth_challenges_purpose_check;
ALTER TABLE public.auth_challenges
    ADD CONSTRAINT auth_challenges_purpose_check
    CHECK (purpose IN ('signup', 'login', 'password_reset'));

ALTER TABLE public.auth_challenges
    DROP CONSTRAINT IF EXISTS auth_challenges_attempts_check;
ALTER TABLE public.auth_challenges
    ADD CONSTRAINT auth_challenges_attempts_check
    CHECK (attempts BETWEEN 0 AND 4);

CREATE INDEX IF NOT EXISTS idx_auth_challenges_expires_at
    ON public.auth_challenges(expires_at);

CREATE TABLE IF NOT EXISTS public.auth_code_lockouts (
    email TEXT NOT NULL,
    purpose TEXT NOT NULL CHECK (purpose IN ('signup', 'login', 'password_reset')),
    failed_attempts INTEGER NOT NULL DEFAULT 0 CHECK (failed_attempts BETWEEN 0 AND 5),
    locked_until TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT TIMEZONE('utc'::text, NOW()),
    PRIMARY KEY (email, purpose)
);

ALTER TABLE public.auth_challenges ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.auth_code_lockouts ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.auth_challenges FROM PUBLIC, anon, authenticated;
REVOKE ALL ON TABLE public.auth_code_lockouts FROM PUBLIC, anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.auth_challenges TO service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.auth_code_lockouts TO service_role;

CREATE OR REPLACE FUNCTION public.auth_code_lockout_seconds(
    p_email TEXT,
    p_purpose TEXT
)
RETURNS INTEGER
LANGUAGE SQL
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
    SELECT GREATEST(0, CEIL(EXTRACT(EPOCH FROM (locked_until - NOW())))::INTEGER)
    FROM public.auth_code_lockouts
    WHERE email = LOWER(TRIM(p_email))
      AND purpose = p_purpose
      AND locked_until > NOW()
    LIMIT 1;
$$;

REVOKE ALL ON FUNCTION public.auth_code_lockout_seconds(TEXT, TEXT)
    FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.auth_code_lockout_seconds(TEXT, TEXT)
    TO service_role;

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
    current_failures INTEGER;
    current_lockout TIMESTAMPTZ;
BEGIN
    SELECT * INTO challenge
    FROM public.auth_challenges
    WHERE challenge_id = p_challenge_id
    FOR UPDATE;

    IF NOT FOUND OR challenge.purpose <> p_purpose THEN
        RETURN jsonb_build_object('status', 'invalid');
    END IF;

    IF challenge.expires_at <= NOW() THEN
        DELETE FROM public.auth_challenges WHERE challenge_id = p_challenge_id;
        RETURN jsonb_build_object('status', 'expired');
    END IF;

    IF challenge.code_hash <> p_code_hash THEN
        UPDATE public.auth_challenges
        SET attempts = LEAST(attempts + 1, 4)
        WHERE challenge_id = p_challenge_id;

        INSERT INTO public.auth_code_lockouts (email, purpose, failed_attempts)
        VALUES (challenge.email, p_purpose, 1)
        ON CONFLICT (email, purpose) DO UPDATE
        SET failed_attempts = CASE
                WHEN public.auth_code_lockouts.locked_until IS NOT NULL
                     AND public.auth_code_lockouts.locked_until <= NOW() THEN 1
                ELSE LEAST(public.auth_code_lockouts.failed_attempts + 1, 5)
            END,
            locked_until = CASE
                WHEN (
                    CASE
                        WHEN public.auth_code_lockouts.locked_until IS NOT NULL
                             AND public.auth_code_lockouts.locked_until <= NOW() THEN 1
                        ELSE LEAST(public.auth_code_lockouts.failed_attempts + 1, 5)
                    END
                ) >= 5 THEN NOW() + INTERVAL '15 minutes'
                ELSE NULL
            END,
            updated_at = NOW()
        RETURNING failed_attempts, locked_until
        INTO current_failures, current_lockout;

        IF current_failures >= 5 AND current_lockout > NOW() THEN
            DELETE FROM public.auth_challenges WHERE challenge_id = p_challenge_id;
            RETURN jsonb_build_object(
                'status', 'locked',
                'retry_after', CEIL(EXTRACT(EPOCH FROM (current_lockout - NOW())))::INTEGER
            );
        END IF;

        RETURN jsonb_build_object('status', 'invalid');
    END IF;

    DELETE FROM public.auth_code_lockouts
    WHERE email = challenge.email AND purpose = p_purpose;
    DELETE FROM public.auth_challenges WHERE challenge_id = p_challenge_id;
    RETURN jsonb_build_object('status', 'ok', 'payload', challenge.payload);
END;
$$;

REVOKE ALL ON FUNCTION public.consume_auth_challenge(TEXT, TEXT, TEXT)
    FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.consume_auth_challenge(TEXT, TEXT, TEXT)
    TO service_role;
