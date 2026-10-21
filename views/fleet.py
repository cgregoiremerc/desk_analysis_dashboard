"""
views/fleet.py
==============
Thin wrapper page: renders the Long-term Fleet report. Registered as a page
via st.Page in app.py.
"""

from reports import fleet_long_term as report

report.render()
