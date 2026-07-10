"""
reports/tonnes_moved_yoy_segment_size.py
=========================================
Tonnes Moved by Year — Segment / Size (full history, from 2017 onward)
  1. Tonnes moved by year (CP Date) — by Cargo Grade
  2. Tonnes moved by year (CP Date) — by Vessel Type
"""

import streamlit as st
import requests
from reports import common as c


def render() -> None:
    st.markdown("### 📦 Tonnes Moved by Year — Segment / Size")
    st.caption(
        "Tonnes moved by year (based on **CP Date**), grouped by "
        "**Cargo Grade** and then by **Vessel Type**. Data from "
        f"**{c.MIN_YEAR}** onward."
    )

    if st.button("🔄 Load / Refresh", key="btn_tonnes_moved", type="primary"):
        with st.spinner("Loading data from Veslink…"):
            try:
                df_raw = c.fetch()
            except requests.HTTPError as e:
                st.error(f"❌ API error ({e.response.status_code}): {e.response.text[:300]}")
                st.session_state.pop("home_data", None)
                return
            except Exception as e:
                st.error(f"❌ Unexpected error: {e}")
                st.session_state.pop("home_data", None)
                return

        missing = [col for col in c.REQUIRED_COLS if col not in df_raw.columns]
        if missing:
            st.error(f"❌ Missing columns in API response: {missing}")
            st.write("Available columns:", list(df_raw.columns))
            st.session_state.pop("home_data", None)
            return

        df_prepared = c.prepare(df_raw)
        n_dropped = len(df_raw) - len(df_prepared)
        # Cache the prepared data so it survives reruns triggered by other
        # widgets (year filter, product checkboxes, tabs...) — without this,
        # st.button() reverts to False on those reruns and the whole report
        # would disappear.
        st.session_state["home_data"] = {"df": df_prepared, "n_dropped": n_dropped}

    cached = st.session_state.get("home_data")
    if cached is None:
        st.info("Click to run the report.")
        return

    df = cached["df"]
    n_dropped = cached["n_dropped"]
    if n_dropped > 0:
        st.warning(f"⚠️ {n_dropped} row(s) skipped (missing/invalid CP Date or Qty Unit).")

    # Only keep years >= MIN_YEAR (earlier data is too sparse)
    df = df[df["Year"] >= c.MIN_YEAR]

    with st.container(border=True):
        years_available = sorted(df["Year"].unique())
        years_selected = st.multiselect(
            "Filter by year", years_available, default=years_available, key="years_full"
        )
    df = df[df["Year"].isin(years_selected)]

    if df.empty:
        st.warning("No data for the current selection.")
        return

    st.divider()

    # ── KPIs ────────────────────────────────────────────────────────────────
    by_year = df.groupby("Year")[c.COL_QTY].sum().sort_index()
    total_tonnes = by_year.sum()
    latest_year = by_year.index.max()
    prior_year = latest_year - 1

    kpi1, kpi2, kpi3 = st.columns(3)
    kpi1.metric("Total tonnes (period)", f"{total_tonnes:,.0f} t")

    if prior_year in by_year.index and by_year[prior_year] > 0:
        yoy = (by_year[latest_year] - by_year[prior_year]) / by_year[prior_year] * 100
        kpi2.metric(f"{int(latest_year)} vs {int(prior_year)}", f"{by_year[latest_year]:,.0f} t", f"{yoy:+.1f}%")
    else:
        kpi2.metric(f"Year {int(latest_year)}", f"{by_year[latest_year]:,.0f} t")

    kpi3.metric("Active Cargo Grades", df[c.COL_CARGO_GRADE].nunique())

    top_n = 8  # fixed number of detailed categories in the charts (rest grouped under 'Other')

    st.divider()

    tab_grade, tab_vt = st.tabs(["🛢️ By Cargo Grade", "🚢 By Vessel Type"])

    pivot_grade, fig_grade = None, None
    pivot_vt, fig_vt = None, None

    # ── Tab 1: Cargo Grade ──────────────────────────────────────────────
    with tab_grade:
        grades_all = c.pivot_by(df, c.COL_CARGO_GRADE).index.tolist()  # sorted by volume desc

        selected_grades = c.product_dropdown("🛢️ Cargo Grades", grades_all, "cg_full")

        df_grade = df[df[c.COL_CARGO_GRADE].isin(selected_grades)]

        if df_grade.empty:
            st.info("No Cargo Grade selected.")
        else:
            pivot_grade = c.pivot_by(df_grade, c.COL_CARGO_GRADE)
            fig_grade = c.stacked_bar(c.chart_data(pivot_grade, top_n))
            st.dataframe(pivot_grade.style.format("{:,.0f}"), use_container_width=True)
            st.plotly_chart(fig_grade, use_container_width=True)
            st.download_button(
                label="⬇️ Export Cargo Grade (CSV)",
                data=pivot_grade.to_csv().encode("utf-8"),
                file_name="tonnes_moved_by_cargo_grade.csv",
                mime="text/csv",
                key="dl_cargo_grade_full",
            )

    # ── Tab 2: Vessel Type ──────────────────────────────────────────────
    with tab_vt:
        vt_all = c.pivot_by(df, c.COL_VESSEL_TYPE).index.tolist()  # sorted by volume desc

        selected_vt = c.product_dropdown("🚢 Vessel Types", vt_all, "vt_full")

        df_vt = df[df[c.COL_VESSEL_TYPE].isin(selected_vt)]

        if df_vt.empty:
            st.info("No Vessel Type selected.")
        else:
            pivot_vt = c.pivot_by(df_vt, c.COL_VESSEL_TYPE)
            fig_vt = c.stacked_bar(c.chart_data(pivot_vt, top_n))
            st.dataframe(pivot_vt.style.format("{:,.0f}"), use_container_width=True)
            st.plotly_chart(fig_vt, use_container_width=True)
            st.download_button(
                label="⬇️ Export Vessel Type (CSV)",
                data=pivot_vt.to_csv().encode("utf-8"),
                file_name="tonnes_moved_by_vessel_type.csv",
                mime="text/csv",
                key="dl_vessel_type_full",
            )

    # ── PDF export ──────────────────────────────────────────────────────────
    st.divider()
    st.markdown("#### 📄 PDF Report")
    st.caption("Generates a PDF with exactly what's currently shown above (year filter, product selection).")

    if st.button("📄 Generate PDF Report", key="btn_pdf_full"):
        with st.spinner("Building PDF…"):
            sections = []
            if pivot_grade is not None:
                sections.append({"heading": "By Cargo Grade", "pivot": pivot_grade, "fig": fig_grade})
            if pivot_vt is not None:
                sections.append({"heading": "By Vessel Type", "pivot": pivot_vt, "fig": fig_vt})

            years_label = (
                f"{min(years_selected)}–{max(years_selected)}"
                if len(years_selected) > 1 else str(years_selected[0])
            )
            pdf_bytes = c.build_pdf_report(
                report_title="Tonnes Moved by Year — Segment / Size",
                subtitle=f"Years: {years_label} · {len(selected_grades)} Cargo Grade(s), {len(selected_vt)} Vessel Type(s) selected",
                kpis=[
                    ("Total tonnes (period)", f"{total_tonnes:,.0f} t"),
                    (f"Year {int(latest_year)}", f"{by_year[latest_year]:,.0f} t"),
                    ("Active Cargo Grades", str(df[c.COL_CARGO_GRADE].nunique())),
                ],
                sections=sections,
            )
            st.session_state["home_pdf"] = pdf_bytes

    if "home_pdf" in st.session_state:
        st.download_button(
            label="⬇️ Download PDF",
            data=st.session_state["home_pdf"],
            file_name="tonnes_moved_by_year_report.pdf",
            mime="application/pdf",
            key="dl_pdf_full",
        )


# ── Standalone runner ─────────────────────────────────────────────────────────
# Lets you test this module alone with `streamlit run reports/tonnes_moved_yoy_segment_size.py`
if __name__ == "__main__":
    st.set_page_config(page_title="Tonnes Moved by Year - Segment/Size", layout="wide")
    render()
