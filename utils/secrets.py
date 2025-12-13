import os

def get_secret(name: str, default: str = "") -> str:
    """
    Works for:
    - Local dev: reads from environment variables (.env loaded by you)
    - Snowflake Streamlit: st.secrets (only if available)
    """
    # 1) Environment variable (local / CI)
    val = os.getenv(name)
    if val:
        return val

    # 2) Snowflake Streamlit secrets
    try:
        import streamlit as st
        if name in st.secrets:
            return str(st.secrets[name])
    except Exception:
        pass

    return default
