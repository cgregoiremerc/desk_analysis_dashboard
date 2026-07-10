"""
reports/tonnes_moved_ytd_segment_size.py
=========================================
Tonnes Moved by YTD — Segment / Size
Filtered to the current year (YTD_YEAR), monthly view.
  1. Tonnes moved YTD by month (CP Date) — by Cargo Grade
  2. Tonnes moved YTD by month (CP Date) — by Vessel Type
"""

import streamlit as st
import requests
import pandas as pd
from reports import common as c

YTD_YEAR = 2026


def render() -> None:
    st.markdown(f"### 📆 Tonnes Moved by YTD — Segment / Size ({YTD_YEAR})")
    st.caption(
        "Tonnes moved since January 1st (based on **CP Date**), for "
        f"**{YTD_YEAR}**, grouped by **Cargo Grade** and then by "
        "**Vessel Type**, monthly view."
    )

    if st.button("🔄 Load / Refresh", key="btn_tonnes_moved_ytd", type="primary"):
        with st.spinner("Loading data from Veslink…"):
            try:
                df_raw = c.fetch()
            except requests.HTTPError as e:
                st.error(f"❌ API error ({e.response.status_code}): {e.response.text[:300]}")
                st.session_state.pop("ytd_data", None)
                return
            except Exception as e:
                st.error(f"❌ Unexpected error: {e}")
                st.session_state.pop("ytd_data", None)
                return

        missing = [col for col in c.REQUIRED_COLS if col not in df_raw.columns]
        if missing:
            st.error(f"❌ Missing columns in API response: {missing}")
            st.write("Available columns:", list(df_raw.columns))
            st.session_state.pop("ytd_data", None)
            return

        df_prepared = c.prepare(df_raw)
        n_dropped = len(df_raw) - len(df_prepared)
        # Cache the prepared data so it survives reruns triggered by other
        # widgets (product checkboxes, slider, tabs...) — without this,
        # st.button() reverts to False on those reruns and the whole report
        # would disappear.
        st.session_state["ytd_data"] = {"df": df_prepared, "n_dropped": n_dropped}

    cached = st.session_state.get("ytd_data")
    if cached is None:
        st.info("Click to run the report.")
        return

    df_full = cached["df"]
    n_dropped = cached["n_dropped"]
    if n_dropped > 0:
        st.warning(f"⚠️ {n_dropped} row(s) skipped (missing/invalid CP Date or Qty Unit).")

    df_2026 = df_full[df_full["Year"] == YTD_YEAR]

    if df_2026.empty:
        st.warning(f"No data available for {YTD_YEAR}.")
        return

    # Cap the data at today's actual date: a single mis-dated row far in the
    # future (data-entry error) would otherwise create a spurious extra month
    # and silently compare 2026 YTD against a near-complete prior year.
    today = pd.Timestamp.now().normalize()
    n_future = (df_2026[c.COL_CP_DATE] > today).sum()
    df_ytd = df_2026[df_2026[c.COL_CP_DATE] <= today]

    if n_future > 0:
        st.warning(
            f"⚠️ {n_future} row(s) dated after today ({today:%b %d, %Y}) were "
            "excluded from the YTD view (likely data-entry errors)."
        )

    if df_ytd.empty:
        st.warning(f"No YTD data available for {YTD_YEAR} up to today.")
        return

    cutoff_date = df_ytd[c.COL_CP_DATE].max()
    st.caption(f"📅 YTD data as of **{cutoff_date:%b %d, %Y}**.")

    st.divider()

    # ── KPIs ────────────────────────────────────────────────────────────────
    total_ytd = df_ytd[c.COL_QTY].sum()

    prior_year = YTD_YEAR - 1
    prior_cutoff = cutoff_date.replace(year=prior_year)
    df_prior_ytd = df_full[
        (df_full["Year"] == prior_year) & (df_full[c.COL_CP_DATE] <= prior_cutoff)
    ]
    total_prior_ytd = df_prior_ytd[c.COL_QTY].sum()

    kpi1, kpi2, kpi3 = st.columns(3)
    kpi1.metric(f"Total tonnes YTD {YTD_YEAR}", f"{total_ytd:,.0f} t")

    if total_prior_ytd > 0:
        yoy = (total_ytd - total_prior_ytd) / total_prior_ytd * 100
        kpi2.metric(
            f"vs YTD {prior_year} (same period)",
            f"{total_prior_ytd:,.0f} t",
            f"{yoy:+.1f}%",
        )
    else:
        kpi2.metric(f"YTD {prior_year}", "n/a")

    kpi3.metric("Active Cargo Grades", df_ytd[c.COL_CARGO_GRADE].nunique())

    with st.container(border=True):
        top_n = st.slider(
            "Number of detailed categories in the charts (the rest is grouped under 'Other')",
            min_value=3, max_value=15, value=8, key="top_n_slider_ytd",
        )

    st.divider()

    tab_grade, tab_vt = st.tabs(["🛢️ By Cargo Grade", "🚢 By Vessel Type"])

    pivot_grade, fig_grade = None, None
    pivot_vt, fig_vt = None, None

    # ── Tab 1: Cargo Grade ──────────────────────────────────────────────
    with tab_grade:
        grades_all = c.pivot_by(df_ytd, c.COL_CARGO_GRADE, period_col="Month").index.tolist()

        selected_grades = c.product_dropdown("🛢️ Cargo Grades", grades_all, "cg_ytd")

        df_grade = df_ytd[df_ytd[c.COL_CARGO_GRADE].isin(selected_grades)]

        if df_grade.empty:
            st.info("No Cargo Grade selected.")
        else:
            pivot_grade = c.pivot_by(df_grade, c.COL_CARGO_GRADE, period_col="Month")
            fig_grade = c.stacked_bar(c.chart_data(pivot_grade, top_n), x_title="Month")
            st.dataframe(pivot_grade.style.format("{:,.0f}"), use_container_width=True)
            st.plotly_chart(fig_grade, use_container_width=True)
            st.download_button(
                label="⬇️ Export Cargo Grade (CSV)",
                data=pivot_grade.to_csv().encode("utf-8"),
                file_name=f"tonnes_moved_ytd_{YTD_YEAR}_by_cargo_grade.csv",
                mime="text/csv",
                key="dl_cargo_grade_ytd",
            )

    # ── Tab 2: Vessel Type ──────────────────────────────────────────────
    with tab_vt:
        vt_all = c.pivot_by(df_ytd, c.COL_VESSEL_TYPE, period_col="Month").index.tolist()

        selected_vt = c.product_dropdown("🚢 Vessel Types", vt_all, "vt_ytd")

        df_vt = df_ytd[df_ytd[c.COL_VESSEL_TYPE].isin(selected_vt)]

        if df_vt.empty:
            st.info("No Vessel Type selected.")
        else:
            pivot_vt = c.pivot_by(df_vt, c.COL_VESSEL_TYPE, period_col="Month")
            fig_vt = c.stacked_bar(c.chart_data(pivot_vt, top_n), x_title="Month")
            st.dataframe(pivot_vt.style.format("{:,.0f}"), use_container_width=True)
            st.plotly_chart(fig_vt, use_container_width=True)
            st.download_button(
                label="⬇️ Export Vessel Type (CSV)",
                data=pivot_vt.to_csv().encode("utf-8"),
                file_name=f"tonnes_moved_ytd_{YTD_YEAR}_by_vessel_type.csv",
                mime="text/csv",
                key="dl_vessel_type_ytd",
            )

    # ── PDF export ──────────────────────────────────────────────────────────
    st.divider()
    st.markdown("#### 📄 PDF Report")
    st.caption("Generates a PDF with exactly what's currently shown above (YTD data, product selection).")

    if st.button("📄 Generate PDF Report", key="btn_pdf_ytd"):
        with st.spinner("Building PDF…"):
            sections = []
            if pivot_grade is not None:
                sections.append({"heading": "By Cargo Grade", "pivot": pivot_grade, "fig": fig_grade})
            if pivot_vt is not None:
                sections.append({"heading": "By Vessel Type", "pivot": pivot_vt, "fig": fig_vt})

            kpis = [
                (f"Total tonnes YTD {YTD_YEAR}", f"{total_ytd:,.0f} t"),
                ("Active Cargo Grades", str(df_ytd[c.COL_CARGO_GRADE].nunique())),
            ]
            if total_prior_ytd > 0:
                kpis.insert(1, (f"vs YTD {prior_year}", f"{total_prior_ytd:,.0f} t ({yoy:+.1f}%)"))

            pdf_bytes = c.build_pdf_report(
                report_title=f"Tonnes Moved by YTD — Segment / Size ({YTD_YEAR})",
                subtitle=(
                    f"YTD data as of {cutoff_date:%b %d, %Y} · "
                    f"{len(selected_grades)} Cargo Grade(s), {len(selected_vt)} Vessel Type(s) selected"
                ),
                kpis=kpis,
                sections=sections,
            )
            st.session_state["ytd_pdf"] = pdf_bytes

    if "ytd_pdf" in st.session_state:
        st.download_button(
            label="⬇️ Download PDF",
            data=st.session_state["ytd_pdf"],
            file_name=f"tonnes_moved_ytd_{YTD_YEAR}_report.pdf",
            mime="application/pdf",
            key="dl_pdf_ytd",
        )


# ── Standalone runner ─────────────────────────────────────────────────────────
if __name__ == "__main__":
    st.set_page_config(page_title=f"Tonnes Moved YTD {YTD_YEAR} - Segment/Size", layout="wide")
    render()
