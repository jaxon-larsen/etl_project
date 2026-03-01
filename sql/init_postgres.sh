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
        instrument_name TEXT,
        recording_name TEXT,
        release_year    INT,
        country_code    TEXT
    );
EOSQL
