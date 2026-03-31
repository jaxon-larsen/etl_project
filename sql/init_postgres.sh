#!/bin/bash
set -e

# Create a separate database for Airflow's internal metadata
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname postgres <<-EOSQL
    CREATE DATABASE airflow_meta;
EOSQL

# Create application tables in the musicbrainz database
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    CREATE TABLE IF NOT EXISTS target_instruments (
        instrument_name TEXT PRIMARY KEY,
        mb_uuid TEXT
    );

    CREATE TABLE IF NOT EXISTS recording_data (
        recording_id    TEXT NOT NULL,
        instrument_name TEXT NOT NULL,
        recording_name  TEXT,
        release_year    INT,
        country_code    TEXT,
        PRIMARY KEY (recording_id, instrument_name)
    );
    
    CREATE INDEX IF NOT EXISTS idx_recording_instrument ON recording_data(instrument_name);
    CREATE INDEX IF NOT EXISTS idx_recording_year ON recording_data(release_year);

    CREATE TABLE IF NOT EXISTS harvest_progress (
        instrument_name TEXT PRIMARY KEY,
        recordings_fetched INT DEFAULT 0,
        last_offset INT DEFAULT 0,
        completed BOOLEAN DEFAULT FALSE,
        last_updated TIMESTAMP DEFAULT NOW()
    );
EOSQL
