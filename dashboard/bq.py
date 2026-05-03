"""
Shared BigQuery helper for all dashboard pages.

Usage in any page:
    import sys, os
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from bq import query, fq
"""
import os
import json
import streamlit as st
import pandas as pd
from google.cloud import bigquery
from google.oauth2 import service_account
from dotenv import load_dotenv

load_dotenv()

P = os.getenv("BQ_PROJECT_ID", "angular-axle-492812-q4")
D = os.getenv("BQ_DATASET", "qoyod_marketing")


def fq(table: str) -> str:
    """Return fully-qualified BQ table reference: `project.dataset.table`"""
    return f"`{P}.{D}.{table}`"


@st.cache_data(ttl=3600)
def query(sql: str) -> pd.DataFrame:
    """Run a BQ SQL query and return a DataFrame. Cached 1 hour."""
    creds_json = os.getenv("GOOGLE_APPLICATION_CREDENTIALS_JSON")
    if creds_json:
        info = json.loads(creds_json)
        creds = service_account.Credentials.from_service_account_info(info)
        client = bigquery.Client(project=P, credentials=creds)
    else:
        creds_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "bigquery-key.json")
        # Resolve relative path from repo root (one level up from dashboard/)
        if not os.path.isabs(creds_path):
            creds_path = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                creds_path.lstrip("./\\"),
            )
        creds = service_account.Credentials.from_service_account_file(creds_path)
        client = bigquery.Client(project=P, credentials=creds)
    return client.query(sql).to_dataframe()
