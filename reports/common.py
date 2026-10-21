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
API_ROOT = "https://api.veslink.com/v1/imos/reports"
TONNES_REPORT = "Tonnes_moved_yoy_segment_size"
BASE_URL = f"{API_ROOT}/{TONNES_REPORT}"

COL_CP_DATE     = "CP Date"
COL_QTY         = "CP Qty MT"  # quantity in metric tonnes (numeric, e.g. 80000.0)
COL_CARGO_GRADE = "Cargo Grades"
COL_VESSEL_TYPE = "Vessel Type"

REQUIRED_COLS = [COL_CP_DATE, COL_QTY, COL_CARGO_GRADE, COL_VESSEL_TYPE]

MIN_YEAR = 2017  # ignore earlier data (sparse / not representative)

# Cargo Grades that are the same product under different names in IMOS.
# Key = name as it comes from the API (after upper-casing / trimming),
# value = name shown in the dashboard. Add new pairs here when you spot
# other duplicates in the charts.
GRADE_ALIASES = {
    "CRUDE OIL": "CRUDE",
}

# ── Colour code (same as the "Time remaining until redelivery" chart) ───────
BRAND_RED   = "#E30613"
BRAND_DARK  = "#3C3C3B"
BRAND_GREY  = "#8C8C8C"
TEXT_COLOR  = "#3C3C3B"   # titles / values
MUTED_TEXT  = "#777777"   # axes, subtitles
GRID_COLOR  = "#E6E6E6"
OTHER_COLOR = "#D9D9D9"   # "Other" bucket

# Categorical palette used by every chart, in this order
PALETTE = [
    BRAND_RED, BRAND_DARK, BRAND_GREY,
    "#9E0A0F",  # dark red
    "#F28B8F",  # light red
    "#5F5F5E",  # mid-dark grey
    "#BDBDBD",  # light grey
    "#C9363C",  # red 2
    "#1E1E1D",  # near black
    "#F7C4C6",  # very light red
]


def text_color_for(hex_color: str) -> str:
    """White text on dark fills, dark text on light fills."""
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return "white" if (0.299 * r + 0.587 * g + 0.114 * b) < 160 else TEXT_COLOR


def style_figure(fig: go.Figure, title: str = None, subtitle: str = None,
                 height: int = 460, legend: str = "top-right") -> go.Figure:
    """House style: white background, light horizontal grid, grey axes,
    bold dark title + grey subtitle, legend top-right."""
    full_title = None
    if title:
        full_title = f"<b>{title}</b>"
        if subtitle:
            full_title += f"<br><span style='font-size:14px;color:{MUTED_TEXT}'>{subtitle}</span>"
    legend_cfg = {
        "top-right": dict(orientation="v", yanchor="top", y=1.0, xanchor="right", x=1.0,
                          bgcolor="rgba(255,255,255,0.8)"),
        "bottom": dict(orientation="h", yanchor="top", y=-0.15, xanchor="left", x=0),
    }[legend]
    fig.update_layout(
        title=dict(text=full_title, x=0, xanchor="left", font=dict(size=20, color=TEXT_COLOR)) if full_title else None,
        height=height,
        margin=dict(t=90 if subtitle else (60 if title else 10), b=10, l=10, r=10),
        plot_bgcolor="white", paper_bgcolor="white",
        font=dict(color=MUTED_TEXT, size=13),
        legend=dict(title=None, traceorder="normal", font=dict(color=TEXT_COLOR, size=13), **legend_cfg),
        uniformtext=dict(minsize=10, mode="hide"),
    )
    fig.update_xaxes(showgrid=False, linecolor=GRID_COLOR, tickfont=dict(color=MUTED_TEXT))
    fig.update_yaxes(gridcolor=GRID_COLOR, zeroline=False, tickfont=dict(color=MUTED_TEXT),
                     title_font=dict(color=MUTED_TEXT))
    return fig


def human(v: float) -> str:
    """262_300_000 -> '262.3M', 45_000 -> '45k'."""
    for div, suf in ((1e9, "B"), (1e6, "M"), (1e3, "k")):
        if abs(v) >= div:
            return f"{v / div:,.1f}{suf}".replace(".0" + suf, suf)
    return f"{v:,.0f}"


def add_stack_totals(fig: go.Figure, x: list, totals: list, fmt=None) -> None:
    """Bold total above each stacked bar (fmt: function number -> text)."""
    fmt = fmt or (lambda t: f"{t:,.0f}")
    fig.add_trace(go.Scatter(
        x=x, y=totals, mode="text", text=[f"<b>{fmt(t)}</b>" for t in totals],
        textposition="top center", textfont=dict(size=14, color=TEXT_COLOR),
        showlegend=False, hoverinfo="skip",
    ))
    if len(totals):
        fig.update_yaxes(range=[0, max(totals) * 1.15])


MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
          "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


# ── Fetch ─────────────────────────────────────────────────────────────────────
def fetch_report(report_name: str) -> pd.DataFrame:
    """Downloads any IMOS report exposed through the Veslink API
    (https://api.veslink.com/v1/imos/reports/<report_name>) as a DataFrame.

    The API token lives in Streamlit secrets (.streamlit/secrets.toml locally,
    or the app's "Secrets" settings on Community Cloud) — never in source code,
    so it's safe to push this repo to GitHub."""
    token = st.secrets.get("veslink_token")
    if not token:
        raise RuntimeError(
            "Missing 'veslink_token' secret. Add it to .streamlit/secrets.toml "
            "locally, or to your app's Secrets settings on Community Cloud."
        )
    r = requests.get(f"{API_ROOT}/{report_name}", params={"apiToken": token},
                     verify=False, timeout=60)
    r.raise_for_status()

    # Reports normally come back as CSV; fall back to JSON just in case.
    try:
        df = pd.read_csv(BytesIO(r.content))
    except Exception:
        data = r.json()
        if isinstance(data, dict):
            data = next((v for v in data.values() if isinstance(v, list)), [data])
        df = pd.DataFrame(data)

    df.columns = df.columns.astype(str).str.strip()  # clean stray whitespace in column names
    return df


def fetch() -> pd.DataFrame:
    """Tonnes moved report (used by the Year / YTD / Top 10 pages)."""
    return fetch_report(TONNES_REPORT)


# ── Data prep ─────────────────────────────────────────────────────────────────
def prepare(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df[COL_CP_DATE] = pd.to_datetime(df[COL_CP_DATE], errors="coerce")
    df["Year"] = df[COL_CP_DATE].dt.year

    # "CP Qty MT" is the CP quantity in metric tonnes (e.g. 80000.0). It should
    # already be numeric; as a safety net we strip any thousands-separator
    # commas / stray text before converting, in case it ever comes as text.
    qty_clean = (
        df[COL_QTY]
        .astype(str)
        .str.replace(",", "", regex=False)
        .str.extract(r"([-+]?\d*\.?\d+)", expand=False)
    )
    df[COL_QTY] = pd.to_numeric(qty_clean, errors="coerce")

    # Harmonise Cargo Grades: trim spaces, collapse double spaces, upper-case,
    # then merge known synonyms (e.g. "CRUDE OIL" -> "CRUDE").
    df[COL_CARGO_GRADE] = (
        df[COL_CARGO_GRADE]
        .astype("string")
        .str.strip()
        .str.replace(r"\s+", " ", regex=True)
        .str.upper()
        .replace(GRADE_ALIASES)
    )

    df = df.dropna(subset=["Year", COL_QTY])
    df["Year"] = df["Year"].astype(int)

    # "Month" column (ordered categorical Jan → Dec), used by the YTD view
    df["Month"] = pd.Categorical(
        df[COL_CP_DATE].dt.month.map(lambda m: MONTHS[m - 1]),
        categories=MONTHS,
        ordered=True,
    )
    return df


def get_cached(key: str):
    """Returns the data cached in st.session_state[key], or None.

    If the cache was built by an older version of the code (e.g. before the
    quantity column changed from "Qty Unit" to "CP Qty MT"), it no longer has
    the expected columns: in that case it's discarded so the user simply
    reloads, instead of the page crashing with a KeyError."""
    cached = st.session_state.get(key)
    if cached is None:
        return None
    df = cached["df"] if isinstance(cached, dict) else cached
    if not isinstance(df, pd.DataFrame) or COL_QTY not in df.columns:
        st.session_state.pop(key, None)
        return None
    return cached


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
    fig = go.Figure()
    for i, (label, row) in enumerate(data.iterrows()):
        color = OTHER_COLOR if label == "Other" else PALETTE[i % len(PALETTE)]
        fig.add_trace(
            go.Bar(
                name=str(label),
                x=periods,
                y=row.values,
                marker=dict(color=color, line=dict(color="white", width=1.5)),
                hovertemplate=f"<b>{label}</b><br>%{{x}}: %{{y:,.0f}} t<extra></extra>",
            )
        )
    add_stack_totals(fig, periods, data.sum(axis=0).tolist(), fmt=human)
    fig.update_layout(barmode="stack", bargap=0.35, hovermode="x unified")
    fig.update_xaxes(title=x_title, type="category")
    fig.update_yaxes(title=y_title)
    return style_figure(fig, height=480, legend="bottom")


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
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(BRAND_RED)),
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
