-- Flashpoint spawn registry schema (fleet-wide, Postgres).
-- Applied automatically by the spawner on startup when FP_REGISTRY_DSN is set;
-- provided here for manual provisioning / review.

CREATE TABLE IF NOT EXISTS spawn_registry (
    agent_id     TEXT PRIMARY KEY,
    container_id TEXT,
    tier         TEXT,
    mission      TEXT,
    gateway_url  TEXT,
    model        TEXT,
    metadata     JSONB,
    status       TEXT,
    spawned_at   TIMESTAMPTZ,
    destroyed_at TIMESTAMPTZ
);

-- Fast lookups by wave/batch/tenant embedded in metadata, and recent spawns.
CREATE INDEX IF NOT EXISTS spawn_registry_metadata_gin
    ON spawn_registry USING GIN (metadata);
CREATE INDEX IF NOT EXISTS spawn_registry_spawned_at_idx
    ON spawn_registry (spawned_at DESC);
