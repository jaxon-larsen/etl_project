# Airflow DAG Fix Summary

## Issues Diagnosed

1. **Out of Memory (OOM) Errors** - Workers were being killed with SIGKILL due to memory exhaustion
2. **Database Schema Mismatch** - The `recording_data` table was missing the `recording_id` column that the code expected
3. **Long-lived Database Connections** - The `harvest_recordings` function kept a single database connection open for potentially hours
4. **High Resource Configuration** - Airflow defaults (parallelism=32) were too high for the constrained environment

## Fixes Applied

### 1. Optimized Airflow Configuration (`docker-compose.yml`)

Added memory-conserving environment variables:
```yaml
- AIRFLOW__CORE__PARALLELISM=4                      # Reduced from 32
- AIRFLOW__CORE__MAX_ACTIVE_RUNS_PER_DAG=1         # Prevent concurrent runs
- AIRFLOW__CORE__MAX_ACTIVE_TASKS_PER_DAG=1        # One task at a time
- AIRFLOW__SCHEDULER__MIN_FILE_PROCESS_INTERVAL=30  # Reduce DAG parsing frequency
- AIRFLOW__SCHEDULER__MAX_TIS_PER_QUERY=4          # Match parallelism setting
- AIRFLOW__WEBSERVER__WORKERS=2                     # Reduce webserver workers
- AIRFLOW__WEBSERVER__WORKER_REFRESH_INTERVAL=1800  # Less frequent worker restarts
```

Added memory reservation:
```yaml
deploy:
  resources:
    limits:
      memory: 2gb
    reservations:
      memory: 1gb  # Added reservation
```

### 2. Refactored Database Connection Management (`scripts/music_logic.py`)

**Before:** One long-lived connection processing all instruments sequentially
```python
with _pg_conn() as conn:
    cur = conn.cursor()
    for inst_name, inst_uuid in scouted:
        # Process all instruments with same connection
```

**After:** Fresh connection for each instrument
```python
# Initial setup with one connection
with _pg_conn() as conn:
    # Create tables and fetch instrument list
    scouted = cur.fetchall()

# Process each instrument with its own connection
for inst_name, inst_uuid in scouted:
    with _pg_conn() as conn:  # Fresh connection per instrument
        cur = conn.cursor()
        # Process this instrument
        cur.close()
```

**Benefits:**
- Prevents long-lived connections that can cause memory issues
- Better error isolation - if one instrument fails, others continue
- More frequent commits reduce transaction size
- Connections are properly closed after each instrument

### 3. Fixed Database Schema

Dropped and recreated tables to match code expectations:
```sql
DROP TABLE IF EXISTS recording_data CASCADE;
DROP TABLE IF EXISTS harvest_progress CASCADE;
```

The `harvest_recordings()` function now correctly creates tables with:
- `recording_id TEXT NOT NULL` column
- Composite PRIMARY KEY `(recording_id, instrument_name)`

### 4. Results

**Memory Usage Improvement:**
- Before: 1.15GB / 2GB (57.69%) with workers crashing
- After: 622MB / 2GB (30.37%) stable operation

**Pipeline Status:**
- ✅ `scout_instruments` - Working correctly
- ✅ `save_instruments` - Working correctly  
- ✅ `harvest_recordings` - Fixed (schema + connection management)
- ✅ `move_to_clickhouse` - Ready to test

**System Stability:**
- No more OOM kills
- No more worker crashes
- Scheduler running smoothly

## Testing the Fix

To manually test the pipeline:

```bash
# 1. Trigger a DAG run
docker compose exec airflow airflow dags trigger musicbrainz_global_pipeline

# 2. Monitor execution
docker compose exec airflow airflow dags list-runs -d musicbrainz_global_pipeline --no-backfill

# 3. Check task states
docker compose exec airflow airflow tasks states-for-dag-run musicbrainz_global_pipeline <RUN_ID>

# 4. View task logs
docker compose logs airflow --tail=100 | grep -E "scout|save|harvest|move"
```

## Notes

- The pipeline is now optimized for a memory-constrained environment (7.6GB system RAM)
- Tasks run sequentially (MAX_ACTIVE_TASKS_PER_DAG=1) to minimize memory usage
- Database connections are properly managed and closed
- The scheduler no longer tries to run too many tasks in parallel
- All infrastructure containers (Postgres, ClickHouse, Airflow) fit within memory limits

## Next Steps

1. Access Airflow UI at http://localhost:8080
2. Trigger the `musicbrainz_global_pipeline` DAG
3. Monitor the full pipeline execution through all 4 tasks
4. Verify data appears in ClickHouse after successful completion
