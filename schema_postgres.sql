-- Exécuter une fois dans la base PostgreSQL choisie, avant de lancer le mode production.
CREATE TABLE IF NOT EXISTS pricing_workspace (
    name TEXT PRIMARY KEY,
    payload JSONB NOT NULL,
    revision INTEGER NOT NULL DEFAULT 0
);
-- Market Price Radar : relevés append-only et décisions séparées.
CREATE TABLE IF NOT EXISTS radar_observation (
 id TEXT PRIMARY KEY, workspace TEXT NOT NULL, run_id TEXT NOT NULL,
 ean TEXT NOT NULL, retailer TEXT NOT NULL, zone TEXT NOT NULL, center TEXT NOT NULL,
 observed_at TEXT, collected_at TEXT NOT NULL, payload TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS radar_observation_lookup
 ON radar_observation(workspace, ean, retailer, zone, center, observed_at);
CREATE INDEX IF NOT EXISTS radar_observation_recent ON radar_observation(workspace, observed_at);
CREATE TABLE IF NOT EXISTS radar_run (
 id TEXT PRIMARY KEY, workspace TEXT NOT NULL, started_at TEXT NOT NULL, payload TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS radar_run_recent ON radar_run(workspace, started_at);
CREATE TABLE IF NOT EXISTS radar_review (
 id TEXT PRIMARY KEY, observation_id TEXT NOT NULL REFERENCES radar_observation(id),
 workspace TEXT NOT NULL, reviewed_at TEXT NOT NULL, payload TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS radar_review_lookup ON radar_review(workspace, observation_id, reviewed_at);
CREATE TABLE IF NOT EXISTS radar_mapping (
 workspace TEXT NOT NULL, retailer TEXT NOT NULL, url TEXT NOT NULL,
 payload TEXT NOT NULL, PRIMARY KEY(workspace, retailer, url)
);
