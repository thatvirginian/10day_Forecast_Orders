import os
from sqlalchemy import create_engine, text
from dotenv import load_dotenv
import streamlit as st
load_dotenv(override=True)


def get_db_url():
    # 1. Check Streamlit Cloud Secrets ONLY if the file exists or we are in the Cloud
    # We check if the internal secrets object is actually populated
    try:
        if st.secrets.load_if_toml_exists() and "PGHOST" in st.secrets:
            s = st.secrets
            return (
                f"postgresql+psycopg2://{s['PGUSER']}:{s['PGPASSWORD']}"
                f"@{s['PGHOST']}:{s['PGPORT']}/{s['PGDATABASE']}"
                f"?sslmode=require"
            )
    except Exception:
        # If st.secrets raises any error locally, just pass through to Step 2
        pass

    # 2. Fallback to os.getenv for your local PC (HQ-PC-29)
    # This is where your .env file data will be used
    return (
        f"postgresql+psycopg2://{os.getenv('PGUSER')}:{os.getenv('PGPASSWORD')}"
        f"@{os.getenv('PGHOST')}:{os.getenv('PGPORT')}/{os.getenv('PGDATABASE')}"
        f"?sslmode=require"
    )


DB_URL = get_db_url()

def get_db_connection():
    """
    Returns a SQLAlchemy Engine.
    In a Streamlit context, you'll wrap this call in @st.cache_resource.
    """
    engine = create_engine(
        DB_URL,
        pool_size=10,           # Keep 10 connections open
        max_overflow=20,        # Allow 20 more during rush hour
        pool_recycle=300,       # Azure kills idle connections; this resets them first
        pool_pre_ping=True      # Transparently reconnects if the pipe is broken
    )
    return engine

