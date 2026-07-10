"""
reports/common.py
==================
Shared constants and helper functions used by both reports
(API fetch, data cleaning, pivots, Plotly chart, product selector).
"""

import pandas as pd
import requests
import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
from io import BytesIO

# ── Constants ─────────────────────────────────────────────────────────────────
BASE_URL = "https://api.veslink.com/v1/imos/reports/Tonnes_moved_yoy_segment_size"

COL_CP_DATE     = "CP Date"
COL_QTY         = "Qty Unit"
COL_CARGO_GRADE = "Cargo Grades"
COL_VESSEL_TYPE = "Vessel Type"

REQUIRED_COLS = [COL_CP_DATE, COL_QTY, COL_CARGO_GRADE, COL_VESSEL_TYPE]

MIN_YEAR = 2017  # ignore earlier data (sparse / not representative)

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
          "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


# ── Fetch ─────────────────────────────────────────────────────────────────────
def fetch() -> pd.DataFrame:
    # The API token lives in Streamlit secrets (.streamlit/secrets.toml locally,
    # or the app's "Secrets" settings on Community Cloud) — never in source code,
    # so it's safe to push this repo to GitHub / make it public.
    token = st.secrets.get("veslink_token")
    if not token:
        raise RuntimeError(
            "Missing 'veslink_token' secret. Add it to .streamlit/secrets.toml "
            "locally, or to your app's Secrets settings on Community Cloud."
        )
    url = f"{BASE_URL}?apiToken={token}"
    r = requests.get(url, verify=False, timeout=30)
    r.raise_for_status()
    df = pd.read_csv(BytesIO(r.content))
    df.columns = df.columns.str.strip()  # clean stray whitespace in column names
    return df


# ── Data prep ─────────────────────────────────────────────────────────────────
def prepare(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df[COL_CP_DATE] = pd.to_datetime(df[COL_CP_DATE], errors="coerce")
    df["Year"] = df[COL_CP_DATE].dt.year

    # "Qty Unit" comes in as text like "80,000.00 MT": we need to strip the
    # thousands-separator commas and the unit suffix (MT, BBL, etc.) before
    # converting it to a number.
    qty_clean = (
        df[COL_QTY]
        .astype(str)
        .str.replace(",", "", regex=False)              # strip commas
        .str.extract(r"([-+]?\d*\.?\d+)", expand=False)  # keep only the number
    )
    df[COL_QTY] = pd.to_numeric(qty_clean, errors="coerce")

    df = df.dropna(subset=["Year", COL_QTY])
    df["Year"] = df["Year"].astype(int)

    # "Month" column (ordered categorical Jan → Dec), used by the YTD view
    df["Month"] = pd.Categorical(
        df[COL_CP_DATE].dt.month.map(lambda m: MONTHS[m - 1]),
        categories=MONTHS,
        ordered=True,
    )
    return df


def pivot_by(df: pd.DataFrame, group_col: str, period_col: str = "Year") -> pd.DataFrame:
    pivot = (
        df.groupby([group_col, period_col], observed=True)[COL_QTY]
        .sum()
        .reset_index()
        .pivot(index=group_col, columns=period_col, values=COL_QTY)
        .fillna(0)
    )
    pivot = pivot.sort_index(axis=1)  # chronological order (ascending years / Jan→Dec)
    pivot["Total"] = pivot.sum(axis=1)
    return pivot.sort_values("Total", ascending=False)


def chart_data(pivot: pd.DataFrame, top_n: int) -> pd.DataFrame:
    """Groups categories beyond the top N into 'Other' — for the chart only
    (the table keeps the full detail)."""
    data = pivot.drop(columns="Total")
    if len(data) > top_n:
        ordered = data.loc[data.sum(axis=1).sort_values(ascending=False).index]
        top = ordered.iloc[:top_n]
        other = ordered.iloc[top_n:].sum(axis=0)
        other.name = "Other"
        data = pd.concat([top, other.to_frame().T])
    return data


def stacked_bar(data: pd.DataFrame, x_title: str = "Year", y_title: str = "Tonnes") -> go.Figure:
    periods = [str(p) for p in data.columns.tolist()]
    palette = px.colors.qualitative.Set3 + px.colors.qualitative.Pastel
    fig = go.Figure()
    for i, (label, row) in enumerate(data.iterrows()):
        color = "#B0B0B0" if label == "Other" else palette[i % len(palette)]
        fig.add_trace(
            go.Bar(
                name=str(label),
                x=periods,
                y=row.values,
                marker_color=color,
                hovertemplate=f"<b>{label}</b><br>%{{x}}: %{{y:,.0f}} t<extra></extra>",
            )
        )
    fig.update_layout(
        barmode="stack",
        height=460,
        margin=dict(t=20, b=0, l=0, r=0),
        yaxis_title=y_title,
        xaxis_title=x_title,
        legend=dict(orientation="h", yanchor="bottom", y=-0.3),
        hovermode="x unified",
        plot_bgcolor="white",
        paper_bgcolor="white",
        yaxis=dict(gridcolor="#E5E7EB"),
        xaxis=dict(showgrid=False),
    )
    return fig


def product_dropdown(label: str, options: list, key_prefix: str) -> list:
    """Dropdown (popover) with a checkbox per product, collapsed by default.
    Returns the list of currently checked options."""
    cb_keys = [f"{key_prefix}__{opt}" for opt in options]
    for k in cb_keys:
        if k not in st.session_state:
            st.session_state[k] = True  # all checked by default on first load

    n_selected = sum(st.session_state[k] for k in cb_keys)

    with st.popover(f"{label} — {n_selected}/{len(options)} selected", use_container_width=True):
        b1, b2 = st.columns(2)
        if b1.button("Select all", key=f"{key_prefix}_all_btn", use_container_width=True):
            for k in cb_keys:
                st.session_state[k] = True
            st.rerun()
        if b2.button("Deselect all", key=f"{key_prefix}_none_btn", use_container_width=True):
            for k in cb_keys:
                st.session_state[k] = False
            st.rerun()
        st.divider()
        for opt, k in zip(options, cb_keys):
            st.checkbox(opt, key=k)

    return [opt for opt, k in zip(options, cb_keys) if st.session_state[k]]


# ── PDF export ─────────────────────────────────────────────────────────────
def _fig_to_png(fig: go.Figure, width: int = 1000, height: int = 480, scale: float = 2.0) -> bytes:
    """Rasterize a Plotly figure to PNG bytes (requires the 'kaleido' package)."""
    return fig.to_image(format="png", width=width, height=height, scale=scale)


def _pivot_to_table_rows(pivot: pd.DataFrame, max_rows: int = 30):
    """Turns a pivot DataFrame into (header, rows, truncated) for a PDF table.
    Limited to the top `max_rows` (by Total) so the PDF stays a reasonable
    size — the app's CSV export still has the full detail."""
    display_df = pivot.copy()
    truncated = len(display_df) > max_rows
    if truncated:
        display_df = display_df.iloc[:max_rows]

    header = [pivot.index.name or ""] + [str(col) for col in display_df.columns]
    rows = [
        [str(idx)] + [f"{v:,.0f}" for v in row.values]
        for idx, row in display_df.iterrows()
    ]
    return header, rows, truncated


def build_pdf_report(report_title: str, subtitle: str, kpis: list, sections: list) -> bytes:
    """Builds a PDF summarizing exactly what's currently shown in the app.

    kpis:     list of (label, value) tuples
    sections: list of dicts: {"heading": str, "pivot": DataFrame | None, "fig": go.Figure | None}
    """
    from datetime import datetime
    from reportlab.lib.pagesizes import landscape, letter
    from reportlab.lib.units import cm
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image, PageBreak,
    )

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(letter),
        topMargin=1.5 * cm, bottomMargin=1.5 * cm,
        leftMargin=1.5 * cm, rightMargin=1.5 * cm,
    )
    styles = getSampleStyleSheet()
    page_width = landscape(letter)[0] - 3 * cm

    story = [
        Paragraph(report_title, styles["Title"]),
        Paragraph(subtitle, styles["Normal"]),
        Paragraph(f"Generated on {datetime.now():%B %d, %Y at %H:%M}", styles["Normal"]),
        Spacer(1, 14),
    ]

    if kpis:
        kpi_table = Table([[k for k, _ in kpis], [v for _, v in kpis]], hAlign="LEFT")
        kpi_table.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("BOTTOMPADDING", (0, 0), (-1, 0), 6),
            ("LINEBELOW", (0, 0), (-1, 0), 0.5, colors.HexColor("#D1D5DB")),
        ]))
        story += [kpi_table, Spacer(1, 16)]

    for i, section in enumerate(sections):
        story.append(Paragraph(section["heading"], styles["Heading2"]))

        fig = section.get("fig")
        if fig is not None:
            png_bytes = _fig_to_png(fig)
            img_h = page_width * 0.42
            story.append(Image(BytesIO(png_bytes), width=page_width, height=img_h))
            story.append(Spacer(1, 10))

        pivot = section.get("pivot")
        if pivot is not None and not pivot.empty:
            header, rows, truncated = _pivot_to_table_rows(pivot)
            n_cols = len(header)
            first_col_w = 5 * cm
            other_col_w = (page_width - first_col_w) / max(1, n_cols - 1)
            table = Table([header] + rows, colWidths=[first_col_w] + [other_col_w] * (n_cols - 1), repeatRows=1)
            table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2563EB")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 7.5),
                ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F3F4F6")]),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#D1D5DB")),
            ]))
            story.append(table)
            if truncated:
                story.append(Spacer(1, 4))
                story.append(Paragraph(
                    f"Showing the top {len(rows)} rows by total volume — "
                    "use the CSV export in the app for the full detail.",
                    styles["Italic"],
                ))

        if i < len(sections) - 1:
            story.append(PageBreak())

    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()
