"""
views/top10_clients.py
========================
Thin wrapper page: renders the Top 10 Cargo Clients report. Register it
as a page via st.Page in app.py (title/icon are set there, not derived
from this filename) — see the snippet below.

    pg = st.navigation([
        st.Page("views/home.py", title="Tonnes Moved (Full)", icon="📦"),
        st.Page("views/ytd.py", title="Tonnes Moved (YTD)", icon="📅"),
        st.Page("views/top10_clients.py", title="Top 10 Cargo Clients", icon="🏆"),
    ])
    pg.run()
"""

from reports import top10_cargo_clients as report

report.render()
