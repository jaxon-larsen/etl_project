"""
Utility functions for managing harvest progress and database.
Run these standalone or import into other scripts.
"""
import os
import psycopg2
from contextlib import contextmanager

_PG_CONN_PARAMS = {
    "host":     os.environ.get("POSTGRES_HOST", "postgres_source"),
    "database": os.environ.get("POSTGRES_DB", "musicbrainz"),
    "user":     os.environ.get("POSTGRES_USER"),
    "password": os.environ.get("POSTGRES_PASSWORD"),
}

@contextmanager
def _pg_conn():
    conn = psycopg2.connect(**_PG_CONN_PARAMS)
    try:
        yield conn
    finally:
        conn.close()

def reset_harvest_progress(instrument_name=None):
    """
    Reset harvest progress for one or all instruments.
    Use this to re-harvest from scratch.
    
    Args:
        instrument_name: Specific instrument to reset, or None for all
    """
    with _pg_conn() as conn:
        cur = conn.cursor()
        if instrument_name:
            cur.execute("DELETE FROM harvest_progress WHERE instrument_name = %s", (instrument_name,))
            print(f"Reset progress for: {instrument_name}")
        else:
            cur.execute("DELETE FROM harvest_progress")
            print("Reset progress for ALL instruments")
        conn.commit()
        cur.close()

def show_harvest_status():
    """Display current harvest progress for all instruments."""
    with _pg_conn() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT 
                instrument_name, 
                recordings_fetched, 
                last_offset, 
                completed,
                last_updated
            FROM harvest_progress
            ORDER BY instrument_name
        """)
        rows = cur.fetchall()
        
        if not rows:
            print("No harvest progress yet.")
            return
        
        print("\n=== Harvest Progress ===")
        print(f"{'Instrument':<20} {'Fetched':<10} {'Offset':<10} {'Done':<10} {'Updated'}")
        print("-" * 80)
        for row in rows:
            inst, fetched, offset, done, updated = row
            print(f"{inst:<20} {fetched:<10} {offset:<10} {str(done):<10} {updated}")
        print()
        cur.close()

def show_recording_stats():
    """Display statistics about harvested recordings."""
    with _pg_conn() as conn:
        cur = conn.cursor()
        
        # Total unique recordings
        cur.execute("SELECT COUNT(DISTINCT recording_id) FROM recording_data")
        total_unique = cur.fetchone()[0]
        
        # Per instrument breakdown
        cur.execute("""
            SELECT 
                instrument_name, 
                COUNT(DISTINCT recording_id) as unique_recordings,
                COUNT(*) as total_rows,
                COUNT(DISTINCT CASE WHEN release_year IS NOT NULL THEN recording_id END) as with_year
            FROM recording_data
            GROUP BY instrument_name
            ORDER BY instrument_name
        """)
        stats = cur.fetchall()
        
        print("\n=== Recording Statistics ===")
        print(f"Total unique recordings across all instruments: {total_unique}")
        print()
        print(f"{'Instrument':<20} {'Unique':<10} {'Total Rows':<12} {'With Year':<12}")
        print("-" * 80)
        for row in stats:
            inst, unique, total, with_year = row
            print(f"{inst:<20} {unique:<10} {total:<12} {with_year:<12}")
        print()
        cur.close()

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        command = sys.argv[1]
        
        if command == "reset":
            instrument = sys.argv[2] if len(sys.argv) > 2 else None
            reset_harvest_progress(instrument)
        elif command == "status":
            show_harvest_status()
        elif command == "stats":
            show_recording_stats()
        else:
            print("Usage:")
            print("  python harvest_utils.py status      # Show harvest progress")
            print("  python harvest_utils.py stats       # Show recording statistics")
            print("  python harvest_utils.py reset       # Reset ALL instruments")
            print("  python harvest_utils.py reset Sitar # Reset specific instrument")
    else:
        print("Usage:")
        print("  python harvest_utils.py status      # Show harvest progress")
        print("  python harvest_utils.py stats       # Show recording statistics")
        print("  python harvest_utils.py reset       # Reset ALL instruments")
        print("  python harvest_utils.py reset Sitar # Reset specific instrument")
