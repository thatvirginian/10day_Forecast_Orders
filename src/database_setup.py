import os
import psycopg2
import streamlit as st
from dotenv import load_dotenv

# Load local .env only if it exists (for your local HQ-PC-29 testing)
load_dotenv()

def get_db_connection():
    st.write("Checking connection...") # This will show up on the app screen
    """
    Direct connection to Azure PostgreSQL.
    Priority: 
    1. Streamlit Secrets (Cloud Deployment)
    2. Environment Variables / .env (Local PC)
    """
    # 1. Try to pull from Streamlit Secrets (Cloud)
    if hasattr(st, "secrets") and "DB_HOST" in st.secrets:
        creds = st.secrets
    # 2. Fallback to local Environment Variables
    else:
        creds = os.environ

    try:
        conn = psycopg2.connect(
            host=creds.get("DB_HOST"),
            database=creds.get("DB_NAME"),
            user=creds.get("DB_USER"),
            password=creds.get("DB_PASSWORD"),
            port=creds.get("DB_PORT", "5432"),
            sslmode="require"  # Mandatory for Azure Postgres
        )
        return conn
    except Exception as e:
        # In Streamlit, this will show a clean error message to the user
        st.error(f"Could not connect to the database: {e}")
        return None
