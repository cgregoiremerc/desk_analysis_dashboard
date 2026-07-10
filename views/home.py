"""
views/home.py
=============
Thin wrapper page: renders the full-history report. Registered as a page
via st.Page in app.py (title/icon are set there, not derived from this
filename).
"""

from reports import tonnes_moved_yoy_segment_size as report

report.render()
