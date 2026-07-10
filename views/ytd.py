"""
views/ytd.py
============
Thin wrapper page: renders the YTD report. Registered as a page via
st.Page in app.py (title/icon are set there, not derived from this
filename).
"""

from reports import tonnes_moved_ytd_segment_size as report

report.render()
