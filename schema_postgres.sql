-- Exécuter une fois dans la base PostgreSQL choisie, avant de lancer le mode production.
CREATE TABLE IF NOT EXISTS pricing_workspace (
    name TEXT PRIMARY KEY,
    payload JSONB NOT NULL,
    revision INTEGER NOT NULL DEFAULT 0
);
