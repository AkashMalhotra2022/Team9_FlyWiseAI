# dags/weather_data_pipeline.py
"""
Weather Data Pipeline DAG
Fetches weather data from Tomorrow.io API and loads into Snowflake
"""

from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.utils.dates import days_ago
from datetime import datetime, timedelta
import sys
import os

# Add the plugins directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from plugins.weather_etl import (
    test_snowflake_connection,
    fetch_and_load_weather,
    generate_summary_report
)

# Default arguments for the DAG
default_args = {
    'owner': 'data-engineering',
    'depends_on_past': False,
    'email_on_failure': False,
    'email_on_retry': False,
    'retries': 2,
    'retry_delay': timedelta(minutes=5),
}

# Define the DAG
with DAG(
    'weather_data_pipeline',
    default_args=default_args,
    description='Fetch weather data from Tomorrow.io and load to Snowflake',
    schedule_interval='0 */6 * * *',  # Run every 6 hours
    start_date=days_ago(1),
    catchup=False,
    tags=['weather', 'etl', 'snowflake'],
) as dag:
    
    # Task 1: Test Snowflake connection and create table if needed
    test_connection = PythonOperator(
        task_id='test_snowflake_connection',
        python_callable=test_snowflake_connection,
    )
    
    # Task 2: Fetch and load weather data for New York
    load_new_york = PythonOperator(
        task_id='load_weather_new_york',
        python_callable=fetch_and_load_weather,
        op_kwargs={'location': 'New York'},
    )
    
    # Task 3: Fetch and load weather data for Los Angeles
    load_los_angeles = PythonOperator(
        task_id='load_weather_los_angeles',
        python_callable=fetch_and_load_weather,
        op_kwargs={'location': 'Los Angeles'},
    )
    
    # Task 4: Fetch and load weather data for Chicago
    load_chicago = PythonOperator(
        task_id='load_weather_chicago',
        python_callable=fetch_and_load_weather,
        op_kwargs={'location': 'Chicago'},
    )
    
    # Task 5: Fetch and load weather data for Houston
    load_houston = PythonOperator(
        task_id='load_weather_houston',
        python_callable=fetch_and_load_weather,
        op_kwargs={'location': 'Houston'},
    )
    
    # Task 6: Fetch and load weather data for Phoenix
    load_phoenix = PythonOperator(
        task_id='load_weather_phoenix',
        python_callable=fetch_and_load_weather,
        op_kwargs={'location': 'Phoenix'},
    )
    
    # Task 7: Fetch and load weather data for Philadelphia
    load_philadelphia = PythonOperator(
        task_id='load_weather_philadelphia',
        python_callable=fetch_and_load_weather,
        op_kwargs={'location': 'Philadelphia'},
    )
    
    # Task 8: Generate summary report
    generate_report = PythonOperator(
        task_id='generate_summary_report',
        python_callable=generate_summary_report,
    )
    
    # Define task dependencies
    # Test connection first
    test_connection >> [
        load_new_york,
        load_los_angeles,
        load_chicago,
        load_houston,
        load_phoenix,
        load_philadelphia
    ]
    
    # All load tasks must complete before generating report
    [
        load_new_york,
        load_los_angeles,
        load_chicago,
        load_houston,
        load_phoenix,
        load_philadelphia
    ] >> generate_report
