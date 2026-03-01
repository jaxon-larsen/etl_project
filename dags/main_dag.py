from airflow import DAG
from airflow.operators.python import PythonOperator
from datetime import datetime, timedelta

from scripts.music_logic import (scout_instruments, 
                                 save_instruments, 
                                 harvest_recordings, 
                                 move_to_clickhouse
)

default_args = {
    'owner': 'jaxonlarsen',
    'retries': 3,
    'retry_delay': timedelta(minutes=5),
    'depends_on_past': False,
    'start_date': datetime(2026, 2, 23),
}

with DAG(
    'musicbrainz_global_pipeline',
    default_args=default_args,
    schedule_interval=None,
    catchup=False
) as dag:

    t1 = PythonOperator(
        task_id='scout_instruments',
        python_callable=scout_instruments
    )

    t2 = PythonOperator(
        task_id='save_instruments',
        python_callable=save_instruments,
        op_args=[t1.output]
    )

    t3 = PythonOperator(
        task_id='harvest_recordings',
        python_callable=harvest_recordings
    )

    t4 = PythonOperator(
        task_id='move_to_clickhouse',
        python_callable=move_to_clickhouse
    )

    t1 >> t2 >> t3 >> t4
