"""
app.py
======
Entry point for the Streamlit multi-page app. Uses st.navigation / st.Page
to define page titles and icons explicitly (instead of deriving them from
filenames) — this avoids emoji-encoding issues on Windows and gives full
control over how pages appear in the sidebar.

Run the app with:
    streamlit run app.py
"""

import streamlit as st

st.set_page_config(
    page_title="Tonnes Moved Dashboard",
    page_icon="📦",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Global theme tweaks (KPI cards, spacing) ───────────────────────────────
st.markdown(
    """
    <style>
        div[data-testid="stMetric"] {
            background-color: rgba(148, 163, 184, 0.08);
            border: 1px solid rgba(148, 163, 184, 0.25);
            border-radius: 10px;
            padding: 14px 18px 10px 18px;
        }
        div[data-testid="stMetricLabel"] {
            font-size: 0.85rem;
            opacity: 0.75;
        }
        button[data-testid="stBaseButton-secondary"], 
        button[kind="secondary"] {
            border-radius: 8px;
        }
        div[data-testid="stTabs"] button {
            font-weight: 600;
        }
    </style>
    """,
    unsafe_allow_html=True,
)

home_page = st.Page("views/home.py", title="Tonnes Moved by Year", icon="📦", default=True)
ytd_page  = st.Page("views/ytd.py",  title="Tonnes Moved YTD",      icon="📆")

nav = st.navigation({"Reports": [home_page, ytd_page]})
nav.run()
