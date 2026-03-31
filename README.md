# MusicBrainz Data Pipeline

A **data pipeline** that extracts music recording data from the MusicBrainz API, stages it in PostgreSQL, and loads it into ClickHouse for analysis. Track global instrument usage trends over time with automated ETL orchestration via Apache Airflow.

---

## 🎯 What This Does

**Data Flow:** MusicBrainz API → PostgreSQL (staging) → ClickHouse (analytics warehouse)

1. **Discovers** popular instruments from MusicBrainz (configurable: 10-200+ instruments)
2. **Harvests** recordings for each instrument (up to 10K per instrument)
3. **Extracts** earliest release year and country for each recording
4. **Loads** data into ClickHouse for trend analysis

**Example Query:** "Which instruments have become more popular since the 1990s?"

---

## 📁 Project Structure

```
db_project/
├── dags/                      # Airflow DAG definitions
│   └── main_dag.py           # Orchestration: defines task order and dependencies
├── scripts/                   # Business logic (imported by Airflow)
│   ├── music_logic.py        # Core ETL functions (scout, harvest, load)
│   └── harvest_utils.py      # CLI utilities for monitoring/debugging
├── sql/                       # Database initialization scripts
│   ├── init_postgres.sh      # Creates tables in PostgreSQL on first start
│   └── init_clickhouse.sql   # Creates tables in ClickHouse on first start
├── docker-compose.yml         # Infrastructure: Postgres, ClickHouse, Airflow
├── Dockerfile                 # Airflow container with Python dependencies
├── requirements.txt           # Python packages (musicbrainzngs, psycopg2, etc.)
└── .env                       # Configuration (DB credentials, instrument count)
```

### Key Files Explained

| File | Purpose |
|------|---------|
| **`scripts/music_logic.py`** | All ETL logic: `scout_instruments()` discovers instruments, `harvest_recordings()` fetches data, `move_to_clickhouse()` loads warehouse |
| **`dags/main_dag.py`** | Airflow DAG: defines 4 tasks in sequence (scout → save → harvest → load). No business logic here. |
| **`docker-compose.yml`** | Service definitions: PostgreSQL (staging), ClickHouse (warehouse), Airflow (orchestrator) |
| **`.env`** | Configuration: database credentials, `INSTRUMENT_COUNT` (how many instruments to discover) |
| **`sql/init_postgres.sh`** | Creates `target_instruments`, `recording_data`, and `harvest_progress` tables on first startup |
| **`sql/init_clickhouse.sql`** | Creates `global_instrument_trends` MergeTree table for analytics |

---

## 🚀 First-Time Setup

### Prerequisites

- **Docker** and **Docker Compose** installed
- **7+ GB available RAM** (1GB Postgres, 1GB ClickHouse, 2GB Airflow, 3GB system)
- **10+ GB disk space** for data volumes
- **Internet connection** for MusicBrainz API access

### Step 1: Clone and Configure

```bash
# Navigate to project directory
cd /path/to/db_project

# Review/edit configuration (optional)
nano .env
```

**Key configuration in `.env`:**
```bash
INSTRUMENT_COUNT=50  # Number of popular instruments to discover (10=test, 50=production, 100+=comprehensive)
```

### Step 2: Start the Infrastructure

```bash
# Start all services in detached mode
docker compose up -d

# Verify all services are running
docker compose ps
```

Expected output:
```
NAME                    STATUS
airflow_orchestrator    Up (healthy)
clickhouse_warehouse    Up
postgres_source         Up (healthy)
```

### Step 3: Access Airflow UI

1. Open browser: **http://localhost:8080**
2. Check container logs for admin password:
   ```bash
   docker logs airflow_orchestrator 2>&1 | grep -i "admin"
   ```
3. Login with username: `admin`, password from logs

### Step 4: Run the Pipeline

1. In Airflow UI, find DAG: **`musicbrainz_global_pipeline`**
2. Click the **▶️ Play button** to trigger
3. Monitor progress in the Graph or Grid view

### Step 5: Query Your Data

#### PostgreSQL (Staging Data)
```bash
# Access Postgres CLI
docker exec -it postgres_source psql -U jaxonlarsen -d musicbrainz

# Check discovered instruments
SELECT * FROM target_instruments LIMIT 10;

# Check harvest progress
SELECT instrument_name, recordings_fetched, completed 
FROM harvest_progress 
ORDER BY recordings_fetched DESC;

# Count recordings per instrument
SELECT instrument_name, COUNT(DISTINCT recording_id) as recordings
FROM recording_data
GROUP BY instrument_name
ORDER BY recordings DESC;
```

#### ClickHouse (Analytics)
```bash
# Access ClickHouse CLI
docker exec -it clickhouse_warehouse clickhouse-client

# Top 20 instruments by recording count
SELECT instrument, COUNT(*) as recordings
FROM global_instrument_trends
GROUP BY instrument
ORDER BY recordings DESC
LIMIT 20;

# Instrument trends over time
SELECT instrument, release_year, COUNT(*) as recordings
FROM global_instrument_trends
WHERE release_year >= 1960
GROUP BY instrument, release_year
ORDER BY release_year, recordings DESC;

# Synthesizer usage by decade
SELECT 
    floor(release_year / 10) * 10 as decade,
    COUNT(*) as recordings
FROM global_instrument_trends
WHERE instrument = 'synthesizer'
GROUP BY decade
ORDER BY decade;
```

---

## ⚙️ How It Works

### Architecture Overview

```
┌─────────────────┐     ┌──────────────┐     ┌───────────────┐
│  MusicBrainz   │────▶│  PostgreSQL  │────▶│  ClickHouse   │
│      API       │     │  (Staging)   │     │  (Warehouse)  │
└─────────────────┘     └──────────────┘     └───────────────┘
         │                      │                     │
         └──────────────────────┴─────────────────────┘
                           │
                    ┌──────▼─────┐
                    │  Airflow   │
                    │ Orchestrator│
                    └────────────┘
```

### Airflow DAG: 4 Tasks in Sequence

The `musicbrainz_global_pipeline` DAG runs these tasks:

1. **`scout_instruments`** (2-10 min)
   - Discovers top N popular instruments from MusicBrainz
   - Uses priority list to ensure key instruments (Piano, Guitar, etc.) are included
   - Configurable via `INSTRUMENT_COUNT` in `.env`
   - Returns: `{instrument_name: mb_uuid}` dictionary

2. **`save_instruments`** (<1 sec)
   - Saves discovered instruments to `target_instruments` table in Postgres
   - Uses `ON CONFLICT DO NOTHING` for idempotency

3. **`harvest_recordings`** (12-30+ hours depending on instrument count)
   - For each instrument, queries MusicBrainz for recordings (paginated)
   - Extracts **earliest release year** across all releases (not most recent)
   - Fetches **country code** from first release found
   - Saves to `recording_data` table with deduplication
   - Checkpoints progress after each API call (resumable on failure)
   - **Rate limit:** 1 request/second (MusicBrainz policy)

4. **`move_to_clickhouse`** (1-5 min)
   - Copies recordings with valid release years from Postgres to ClickHouse
   - Truncates ClickHouse table first for clean state
   - Uses `DISTINCT ON (recording_id)` to avoid duplicates

---

## 🔧 Configuration & Tuning

### Instrument Count

**File:** `.env`
```bash
INSTRUMENT_COUNT=50  # Default: 50 popular instruments
```

| Value | Use Case | Scout Time | Harvest Time | Total Recordings |
|-------|----------|------------|--------------|------------------|
| 10 | Testing/demo | ~2 min | 2-3 hours | ~100K |
| 50 | **Production** | ~5 min | 12-15 hours | ~500K |
| 100 | Comprehensive | ~10 min | 24-30 hours | ~1M |
| 200+ | Research/archive | ~20 min | 48-60+ hours | ~2M |

### Recordings Per Instrument

**File:** `scripts/music_logic.py`, line 77
```python
MAX_RECORDINGS_PER_INSTRUMENT = 10000  # Default: 10,000
```

- **5,000** = Faster harvests, less comprehensive
- **10,000** = Balanced (recommended)
- **20,000** = More coverage, longer runtime

### Priority Instruments

**File:** `scripts/music_logic.py`, line 43
```python
priority_instruments = [
    "Piano", "Guitar", "Drums", "Bass", "Violin", 
    "Synthesizer", "Saxophone", "Trumpet"
]
```

These instruments are always included (if available in MusicBrainz).

### Optional: Filter Out Generic Instruments

**File:** `scripts/music_logic.py`, line 89 (uncomment to enable)
```python
skip_terms = ['unspecified', 'other', 'unknown']
if any(term in name.lower() for term in skip_terms):
    continue
```

---

## 📊 Database Schemas

### PostgreSQL (Staging)

#### `target_instruments`
```sql
CREATE TABLE target_instruments (
    instrument_name TEXT PRIMARY KEY,
    mb_uuid TEXT
);
```

#### `recording_data`
```sql
CREATE TABLE recording_data (
    recording_id    TEXT NOT NULL,
    instrument_name TEXT NOT NULL,
    recording_name  TEXT,
    release_year    INT,
    country_code    TEXT,
    PRIMARY KEY (recording_id, instrument_name)
);
```

#### `harvest_progress`
```sql
CREATE TABLE harvest_progress (
    instrument_name TEXT PRIMARY KEY,
    recordings_fetched INT DEFAULT 0,
    last_offset INT DEFAULT 0,
    completed BOOLEAN DEFAULT FALSE,
    last_updated TIMESTAMP DEFAULT NOW()
);
```

### ClickHouse (Warehouse)

#### `global_instrument_trends`
```sql
CREATE TABLE global_instrument_trends (
    instrument String,
    recording_name String,
    release_year UInt16,
    country_code String
) ENGINE = MergeTree()
ORDER BY (instrument, release_year);
```

---

## 🛠️ Utility Commands

### Monitor Harvest Progress

```bash
# Check status of all instruments
docker exec airflow_orchestrator python /opt/airflow/dags/scripts/harvest_utils.py status

# View detailed statistics
docker exec airflow_orchestrator python /opt/airflow/dags/scripts/harvest_utils.py stats
```

### Reset Progress (Re-harvest)

```bash
# Reset all instruments
docker exec airflow_orchestrator python /opt/airflow/dags/scripts/harvest_utils.py reset

# Reset specific instrument
docker exec airflow_orchestrator python /opt/airflow/dags/scripts/harvest_utils.py reset "piano"
```

### View Logs

```bash
# Airflow logs (all tasks)
docker logs -f airflow_orchestrator

# Postgres logs
docker logs -f postgres_source

# ClickHouse logs
docker logs -f clickhouse_warehouse
```

### Clean Restart

```bash
# Stop services and remove volumes (CAUTION: deletes all data)
docker compose down -v

# Start fresh
docker compose up -d
```

---

## 🐛 Troubleshooting

### Issue: "No instruments found in target_instruments table"

**Cause:** `scout_instruments` task failed or didn't run.

**Solution:**
1. Check Airflow logs: `docker logs airflow_orchestrator`
2. Verify internet connectivity from container: `docker exec airflow_orchestrator curl -I https://musicbrainz.org`
3. Re-run the DAG from Airflow UI

### Issue: Harvest takes too long

**Cause:** MusicBrainz rate limit (1 req/sec) + many instruments

**Solutions:**
- Reduce `INSTRUMENT_COUNT` in `.env`
- Lower `MAX_RECORDINGS_PER_INSTRUMENT` in `music_logic.py`
- Run during off-hours and let it complete overnight
- Check progress: `harvest_utils.py status`

### Issue: Out of disk space

**Cause:** Data volumes (`postgres_data/`, `clickhouse_data/`) growing large

**Solutions:**
```bash
# Check disk usage
du -sh postgres_data/ clickhouse_data/

# Clear old data (CAUTION: permanent)
docker compose down -v
docker volume prune
docker compose up -d
```

### Issue: ClickHouse empty after pipeline runs

**Cause:** Recordings missing `release_year` (filtered out during load)

**Solutions:**
1. Check Postgres data: `SELECT COUNT(*) FROM recording_data WHERE release_year IS NOT NULL;`
2. If count is low, increase `MAX_RECORDINGS_PER_INSTRUMENT`
3. Some instruments have limited metadata in MusicBrainz

### Issue: Duplicate recordings in results

**Expected behavior:** System uses `ON CONFLICT DO NOTHING` and `DISTINCT ON (recording_id)`

**If seeing true duplicates:**
1. Truncate ClickHouse: `TRUNCATE TABLE global_instrument_trends`
2. Re-run `move_to_clickhouse` task from Airflow

---

## 📈 Performance & Scaling

### Current Limits

- **PostgreSQL:** 1GB RAM, handles 10M+ rows comfortably
- **ClickHouse:** 1GB RAM, handles 100M+ rows easily
- **Airflow:** 2GB RAM, single-worker LocalExecutor

### Speed Up Harvesting

**Option 1: Parallel DAG Runs**
1. Split instruments into batches (e.g., A-M, N-Z)
2. Create separate DAG instances
3. Run simultaneously

**Option 2: Reduce Scope**
- Lower `INSTRUMENT_COUNT` from 50 to 25
- Lower `MAX_RECORDINGS_PER_INSTRUMENT` from 10K to 5K

**Option 3: Request Rate Limit Increase**
- Contact MusicBrainz for elevated API access
- Default: 1 req/sec, elevated: 10+ req/sec

### Scale Beyond MusicBrainz

For production workloads:
1. **Mirror MusicBrainz database** locally (~50GB, freely available)
2. **Use additional APIs:** Spotify, Last.fm, Discogs for cross-validation
3. **Distributed workers:** Use Celery + RabbitMQ for parallel harvesting

---

## 🔒 Rate Limiting & API Compliance

**MusicBrainz enforces 1 request per second.**

All API calls in `music_logic.py` include:
```python
time.sleep(1)  # DO NOT REMOVE - prevents IP ban
```

**Removing this will result in:**
- Temporary IP ban (1-24 hours)
- Degraded service for all users
- Pipeline failures

**To request elevated limits:**
- Email: support@musicbrainz.org
- Provide: project description, expected usage
- Consider donating to support the service

---

## 🧪 Testing

### Quick Test (10 instruments, ~2 hours)

```bash
# Edit .env
echo "INSTRUMENT_COUNT=10" >> .env

# Restart
docker compose down && docker compose up -d

# Trigger DAG
# (Use Airflow UI or CLI trigger)

# Monitor
docker exec airflow_orchestrator python /opt/airflow/dags/scripts/harvest_utils.py status
```

### Verify Data Quality

```sql
-- Postgres: Check for nulls
SELECT 
    COUNT(*) as total,
    COUNT(release_year) as with_year,
    COUNT(country_code) as with_country
FROM recording_data;

-- ClickHouse: Year distribution
SELECT 
    floor(release_year / 10) * 10 as decade,
    COUNT(*) as recordings
FROM global_instrument_trends
GROUP BY decade
ORDER BY decade;
```

---

## 📝 Development

### Adding New Instruments

**Option 1:** Edit priority list (always included)
```python
# scripts/music_logic.py, line 43
priority_instruments = [
    "Piano", "Guitar", "Your New Instrument"
]
```

**Option 2:** Increase discovery count
```bash
# .env
INSTRUMENT_COUNT=100  # Discovers more instruments automatically
```

### Modifying ETL Logic

All business logic is in **`scripts/music_logic.py`**:
- `scout_instruments()` - Line 35
- `save_instruments()` - Line 121
- `harvest_recordings()` - Line 132
- `move_to_clickhouse()` - Line 289

**After changes:**
```bash
# Rebuild Airflow container
docker compose build airflow
docker compose up -d airflow

# Trigger DAG to test
```

### Custom Queries

Add SQL files to `sql/` directory and mount in `docker-compose.yml`:
```yaml
volumes:
  - ./sql:/sql
```

Then run:
```bash
docker exec postgres_source psql -U jaxonlarsen -d musicbrainz -f /sql/your_query.sql
```

---

## 🤝 Contributing

### Project Conventions

- **MusicBrainz rate limiting:** Always include `time.sleep(1)` after API calls
- **Idempotency:** Use `ON CONFLICT DO NOTHING` for insert operations
- **Earliest-year logic:** Extract minimum year across releases (debut usage)
- **Module resolution:** Keep `sys.path.append('/opt/airflow')` in DAG files
- **Container networking:** Use Docker service names (e.g., `postgres_source`), not `localhost`

---

## 📚 Additional Resources

- **MusicBrainz API Docs:** https://musicbrainz.org/doc/MusicBrainz_API
- **ClickHouse Docs:** https://clickhouse.com/docs
- **Airflow Docs:** https://airflow.apache.org/docs
- **musicbrainzngs Python Library:** https://python-musicbrainzngs.readthedocs.io

---

## 📄 License

This project uses data from [MusicBrainz](https://musicbrainz.org), which is licensed under [CC0 1.0](https://creativecommons.org/publicdomain/zero/1.0/). Please respect the MusicBrainz API rate limits and [Code of Conduct](https://musicbrainz.org/doc/Code_of_Conduct).

---

**Questions or issues?** Check the Troubleshooting section or review Airflow logs: `docker logs airflow_orchestrator`
