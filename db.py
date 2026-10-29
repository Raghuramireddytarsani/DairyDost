"""MongoDB connection helper (used by the Streamlit app)."""
import os

import streamlit as st
from dotenv import load_dotenv
from pymongo import MongoClient
from pymongo.errors import PyMongoError
from streamlit.errors import StreamlitSecretNotFoundError

load_dotenv()
DB_NAME = "dairydost"


def _uri() -> str:
    # Streamlit Cloud: put MONGODB_URI in app secrets. Local: use .env
    try:
        return st.secrets["MONGODB_URI"]
    except (KeyError, StreamlitSecretNotFoundError):
        return os.getenv("MONGODB_URI", "")


@st.cache_resource
def get_db():
    uri = _uri()
    if not uri:
        st.error("MONGODB_URI is not set. Add it to .env (local) or Streamlit secrets (cloud).")
        st.stop()
    client = MongoClient(uri, serverSelectionTimeoutMS=8000)
    try:
        client.admin.command("ping")
    except PyMongoError as exc:
        client.close()
        st.error(
            f"Could not connect to MongoDB ({type(exc).__name__}). "
            "Check MONGODB_URI and Atlas Network Access."
        )
        st.stop()
    return client[DB_NAME]
