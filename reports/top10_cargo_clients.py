"""
reports/top10_cargo_clients.py
================================
Top 10 Cargo Clients
  - Groups by unique "Cargo ID" to avoid double-counting a cargo that has
    several line items.
  - Uses the "Counterparty Short Name" associated with each Cargo ID as the
    client.
  - Lets the user pick a year and ranks the top 10 clients for that year,
    either by tonnes moved or by number of cargoes.
  - Fancy Plotly visuals: a gold/silver/bronze podium for the top 3 + a
    gradient horizontal bar chart for the full top 10.

Reuses reports/common.py for the API fetch/token/cleaning logic, so it
plugs into the existing tonnes_moved_app the same way home.py / ytd.py do.
"""

import streamlit as st
import pandas as pd
import requests
import plotly.graph_objects as go
import plotly.express as px

from reports import common as c

# ── Extra columns needed for this report (on top of common.REQUIRED_COLS) ──
COL_CARGO_ID     = "Cargo ID"
COL_COUNTERPARTY = "Counterparty Short Name"

EXTRA_REQUIRED_COLS = [COL_CARGO_ID, COL_COUNTERPARTY]

PODIUM_COLORS = ["#FFD700", "#C0C0C0", "#CD7F32"]  # gold, silver, bronze


# ── Data prep ─────────────────────────────────────────────────────────────────
def _build_client_ranking(df: pd.DataFrame) -> pd.DataFrame:
    """One row per unique Cargo ID -> its Counterparty / Year / tonnes,
    then aggregated per Counterparty per Year (tonnes + cargo count)."""
    df_unique = (
        df.dropna(subset=[COL_CARGO_ID, COL_COUNTERPARTY])
        .drop_duplicates(subset=[COL_CARGO_ID])
    )
    ranking = (
        df_unique.groupby([COL_COUNTERPARTY, "Year"], observed=True)
        .agg(Tonnes=(c.COL_QTY, "sum"), Cargos=(COL_CARGO_ID, "nunique"))
        .reset_index()
    )
    return ranking


def _top10_for_year(ranking: pd.DataFrame, year: int, metric: str) -> pd.DataFrame:
    sub = (
        ranking[ranking["Year"] == year]
        .sort_values(metric, ascending=False)
        .head(10)
        .reset_index(drop=True)
    )
    sub.index = sub.index + 1  # rank 1..10
    return sub


# ── Charts ────────────────────────────────────────────────────────────────────
def _podium_chart(top10: pd.DataFrame, metric: str, year: int) -> go.Figure:
    """Gold / silver / bronze podium for the top 3 clients."""
    top3 = top10.head(3).reset_index(drop=True)
    heights = [1.0, 0.75, 0.55]
    # visual order left-to-right: 2nd, 1st, 3rd
    layout_order = [1, 0, 2]

    fig = go.Figure()
    for slot, rank_pos in enumerate(layout_order):
        if rank_pos >= len(top3):
            continue
        row = top3.iloc[rank_pos]
        fig.add_trace(go.Bar(
            x=[f"#{rank_pos + 1}<br>{row[COL_COUNTERPARTY]}"],
            y=[heights[rank_pos]],
            marker=dict(
                color=PODIUM_COLORS[rank_pos],
                line=dict(color="white", width=2),
            ),
            text=f"{row[metric]:,.0f}",
            textposition="outside",
            textfont=dict(size=16, color="#1F2937"),
            width=0.55,
            showlegend=False,
            hovertemplate=f"{row[COL_COUNTERPARTY]}<br>{metric}: {row[metric]:,.0f}<extra></extra>",
        ))

    unit_label = "tonnes" if metric == "Tonnes" else "cargoes"
    fig.update_layout(
        title=f"🏆 Podium — Top 3 Clients ({year}) · {unit_label}",
        yaxis=dict(visible=False, range=[0, 1.35]),
        xaxis=dict(tickfont=dict(size=13)),
        height=380,
        margin=dict(t=60, b=10, l=10, r=10),
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        bargap=0.3,
    )
    return fig


def _bar_chart(top10: pd.DataFrame, metric: str, year: int) -> go.Figure:
    """Horizontal gradient bar chart, #1 at the top."""
    df_sorted = top10.sort_values(metric, ascending=True)
    fig = px.bar(
        df_sorted,
        x=metric,
        y=COL_COUNTERPARTY,
        orientation="h",
        text=metric,
        color=metric,
        color_continuous_scale="Sunsetdark",
    )
    fig.update_traces(
        texttemplate="%{text:,.0f}",
        textposition="outside",
        marker_line_color="white",
        marker_line_width=1,
    )
    fig.update_layout(
        title=f"Top 10 Clients — {year}",
        xaxis_title="Tonnes" if metric == "Tonnes" else "Number of cargoes",
        yaxis_title="",
        height=460,
        coloraxis_showscale=False,
        margin=dict(t=50, b=10, l=10, r=60),
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
    )
    return fig


# ── Render ────────────────────────────────────────────────────────────────────
def render() -> None:
    st.markdown("### 🏆 Top 10 Cargo Clients")
    st.caption(
        "Ranking of clients (**Counterparty Short Name**) based on unique cargoes "
        "(**Cargo ID**) — select a year to see the top 10."
    )

    if st.button("🔄 Load / Refresh", key="btn_top10_clients", type="primary"):
        with st.spinner("Loading data from Veslink…"):
            try:
                df_raw = c.fetch()
            except requests.HTTPError as e:
                st.error(f"❌ API error ({e.response.status_code}): {e.response.text[:300]}")
                st.session_state.pop("top10_data", None)
                return
            except Exception as e:
                st.error(f"❌ Unexpected error: {e}")
                st.session_state.pop("top10_data", None)
                return

        missing = [col for col in c.REQUIRED_COLS + EXTRA_REQUIRED_COLS if col not in df_raw.columns]
        if missing:
            st.error(f"❌ Missing columns in API response: {missing}")
            st.write("Available columns:", list(df_raw.columns))
            st.info(
                "This report needs **Cargo ID** and **Counterparty Short Name** in addition "
                "to the usual columns (CP Date, Qty Unit, Cargo Grades, Vessel Type). "
                "If the current Veslink endpoint in `reports/common.py` doesn't return them, "
                "point `URL` to a report/export that includes client data, and it will work "
                "the same way."
            )
            st.session_state.pop("top10_data", None)
            return

        df_prepared = c.prepare(df_raw)
        df_prepared = df_prepared[df_prepared["Year"] >= c.MIN_YEAR]
        # Cache the prepared data so it survives reruns triggered by other
        # widgets (year selector, metric radio...) — without this, st.button()
        # reverts to False on those reruns and the whole report would disappear.
        st.session_state["top10_data"] = df_prepared

    df = st.session_state.get("top10_data")
    if df is None:
        st.info("Click to run the report.")
        return

    ranking = _build_client_ranking(df)
    if ranking.empty:
        st.warning("No data available to build the ranking.")
        return

    years_available = sorted(ranking["Year"].unique(), reverse=True)

    col_y, col_m = st.columns([2, 2])
    with col_y:
        year = st.selectbox("📅 Year", years_available, index=0, key="top10_year")
    with col_m:
        metric_label = st.radio(
            "Rank by",
            ["Tonnes moved", "Number of cargoes"],
            horizontal=True,
            key="top10_metric",
        )
    metric = "Tonnes" if metric_label == "Tonnes moved" else "Cargos"

    top10 = _top10_for_year(ranking, year, metric)
    if top10.empty:
        st.warning(f"No clients found for {year}.")
        return

    st.divider()

    year_ranking = ranking[ranking["Year"] == year]
    k1, k2, k3 = st.columns(3)
    k1.metric("🥇 Top client", top10.iloc[0][COL_COUNTERPARTY])
    k2.metric(f"Top 10 total ({metric_label.lower()})", f"{top10[metric].sum():,.0f}")
    k3.metric("Active clients this year", year_ranking[COL_COUNTERPARTY].nunique())

    st.plotly_chart(_podium_chart(top10, metric, year), use_container_width=True)
    st.plotly_chart(_bar_chart(top10, metric, year), use_container_width=True)

    st.markdown("#### 📋 Full ranking")
    display_df = top10[[COL_COUNTERPARTY, "Tonnes", "Cargos"]].copy()
    display_df.columns = ["Counterparty Short Name", "Tonnes", "Cargoes"]
    display_df.index.name = "Rank"
    display_df["Tonnes"] = display_df["Tonnes"].map("{:,.0f}".format)
    st.dataframe(display_df, use_container_width=True)

    st.download_button(
        label="⬇️ Export Top 10 (CSV)",
        data=top10.to_csv().encode("utf-8"),
        file_name=f"top10_cargo_clients_{year}.csv",
        mime="text/csv",
        key="dl_top10_clients",
    )


# ── Standalone runner ─────────────────────────────────────────────────────────
if __name__ == "__main__":
    st.set_page_config(page_title="Top 10 Cargo Clients", layout="wide")
    render()