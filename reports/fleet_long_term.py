"""
reports/fleet_long_term.py
===========================
Fleet on hire — vessels we still control as of today, split by the time
remaining until redelivery (< 3 months, 3-6 months, 6-12 months, 1-2 years,
2-3 years, > 3 years), with an optional minimum remaining period.

Data: two IMOS reports from the Veslink API, merged on the vessel code
  - Vessel_segments   : Vessel code, Delivery Date, Redelivery Date
                        (+ the column flagging TCT segments, auto-detected)
  - Vessel_segments_2 : Vessel code, Vessel type

Logic
  1. Keep segments with Status Delivered / Redelivered / Fixed (selectable),
     excluding TCT segments (optional).
  2. A vessel can have several segments -> keep its latest Redelivery Date.
  3. Keep vessels whose Redelivery Date >= today (+ optional minimum period).
  4. Segment derived from the Vessel type: D… = Dry, T… = Wet,
     LP… / LN… = Gas.
"""

import streamlit as st
import pandas as pd
import requests
import plotly.express as px
import plotly.graph_objects as go

from reports import common as c

REPORT_SEGMENTS = "Vessel_segments"
REPORT_TYPES    = "Vessel_segments_2"

# Accepted column names (compared case-insensitively, spaces/underscores ignored)
COL_ALIASES = {
    "vessel_code": ["vessel code", "vesselcode", "vessel_code", "vessel"],
    "delivery":    ["delivery date", "deliverydate", "delivery_date", "delivery"],
    "redelivery":  ["redelivery date", "redeliverydate", "redelivery_date", "redelivery"],
    "vessel_type": ["vessel type", "vesseltype", "vessel_type", "type"],
    "status":      ["status", "segment status", "vessel status"],
}

# Vessel_segments "Status" values selected by default (others can be added in the page)
DEFAULT_STATUSES = ["Delivered", "Redelivered", "Fixed"]

# Dashboard colour code (see reports/common.py)
SEGMENT_COLORS = {"Dry": c.BRAND_RED, "Wet": c.BRAND_DARK, "Gas": c.BRAND_GREY, "Other": c.OTHER_COLOR}

# Remaining-period buckets, counted from TODAY (months from today)
BUCKETS = [
    (0, 3, "< 3 months"),
    (3, 6, "3-6 months"),
    (6, 12, "6-12 months"),
    (12, 24, "1-2 years"),
    (24, 36, "2-3 years"),
    (36, None, "> 3 years"),
]
# Already-redelivered buckets (months from today, negative = in the past),
# shown oldest -> newest on the left of the chart
PAST_BUCKETS = [
    (None, -24, "> 2 years<br>ago"),
    (-24, -12, "1-2 years<br>ago"),
    (-12, -6, "6-12 months<br>ago"),
    (-6, -3, "3-6 months<br>ago"),
    (-3, 0, "< 3 months<br>ago"),
]
# "Already redelivered" look-back filter (label -> months back, None = hidden)
LOOKBACKS = {
    "Hide": None,
    "Last 6 months": 6,
    "Last 12 months": 12,
    "Last 2 years": 24,
    "All history": 10_000,
}
# Minimum remaining period filter (label -> months from today)
MIN_PERIODS = {
    "As of today (all vessels)": 0,
    "3 months +": 3,
    "6 months +": 6,
    "1 year +": 12,
    "2 years +": 24,
    "3 years +": 36,
}
SEGMENT_ORDER = ["Dry", "Wet", "Gas", "Other"]
CACHE_KEY = "fleet_data"


# ── Helpers ───────────────────────────────────────────────────────────────────
def _norm(name) -> str:
    return str(name).strip().lower().replace("_", " ")


def _pick_columns(df: pd.DataFrame, needed: list, report: str) -> pd.DataFrame:
    """Renames the needed columns to standard names; clear error if missing."""
    norm = {col: _norm(col) for col in df.columns}
    mapping = {}
    for std in needed:
        aliases = [_norm(a) for a in COL_ALIASES[std]]
        match = next((col for col, low in norm.items() if low in aliases), None)
        if match is None:
            raise KeyError(
                f"Column for '{std}' not found in report {report}. "
                f"Available columns: {list(df.columns)}"
            )
        mapping[match] = std
    return df.rename(columns=mapping)


def _clean_code(s: pd.Series) -> pd.Series:
    # "1234.0" (numbers read as floats) and "1234" must match
    return s.astype(str).str.strip().str.replace(r"\.0$", "", regex=True).str.upper()


def _to_date(s: pd.Series) -> pd.Series:
    """ISO dates first (what the API returns); falls back to day-first."""
    out = pd.to_datetime(s, errors="coerce")
    if out.isna().mean() > 0.5:
        out = pd.to_datetime(s, errors="coerce", dayfirst=True)
    return out


def segment_from_type(vessel_type) -> str:
    t = str(vessel_type).strip().upper()
    if t.startswith(("LP", "LN")):
        return "Gas"
    if t.startswith("D"):
        return "Dry"
    if t.startswith("T"):
        return "Wet"
    return "Other"


def _detect_tct_column(df: pd.DataFrame):
    """Returns the column with the most 'TCT' values (or None)."""
    best, best_n = None, 0
    for col in df.columns:
        n = df[col].astype(str).str.contains(r"\bTCT\b", case=False, regex=True).sum()
        if n > best_n:
            best, best_n = col, n
    return best


def load_fleet() -> dict:
    seg_raw = c.fetch_report(REPORT_SEGMENTS)
    typ_raw = c.fetch_report(REPORT_TYPES)

    seg = _pick_columns(seg_raw, ["vessel_code", "delivery", "redelivery"], REPORT_SEGMENTS)
    typ = _pick_columns(typ_raw, ["vessel_code", "vessel_type"], REPORT_TYPES)

    tct_col = _detect_tct_column(seg_raw)
    seg["is_tct"] = (
        seg_raw[tct_col].astype(str).str.contains(r"\bTCT\b", case=False, regex=True)
        if tct_col else False
    )

    # Status of the segment (Delivered / Redelivered / Fixed / Canceled ...)
    try:
        seg = _pick_columns(seg, ["status"], REPORT_SEGMENTS)
        seg["status"] = (seg["status"].astype(str).str.strip().str.capitalize()  # "delivered" = "Delivered"
                         .replace({"Nan": "(blank)", "": "(blank)"}))
        has_status = True
    except KeyError:
        seg["status"] = "(no Status column)"
        has_status = False

    seg = seg[["vessel_code", "delivery", "redelivery", "is_tct", "status"]].copy()
    seg["vessel_code"] = _clean_code(seg["vessel_code"])
    seg["delivery"] = _to_date(seg["delivery"])
    seg["redelivery"] = _to_date(seg["redelivery"])

    typ = typ[["vessel_code", "vessel_type"]].copy()
    typ["vessel_code"] = _clean_code(typ["vessel_code"])
    typ["vessel_type"] = typ["vessel_type"].astype(str).str.strip()
    typ = typ.drop_duplicates("vessel_code")  # one type per vessel

    df = seg.merge(typ, on="vessel_code", how="left")
    df["vessel_type"] = df["vessel_type"].replace({"nan": None}).fillna("Unknown")
    df["segment"] = df["vessel_type"].map(segment_from_type)

    return {
        "df": df,
        "tct_col": tct_col,
        "has_status": has_status,
        "n_unmatched": int(df.loc[df["vessel_type"] == "Unknown", "vessel_code"].nunique()),
        "seg_cols": list(seg_raw.columns),
        "typ_cols": list(typ_raw.columns),
    }


def fleet_on_hire(df: pd.DataFrame, today: pd.Timestamp, min_months: int,
                  only_current: bool, exclude_tct: bool, statuses: list = None,
                  lookback_months: int = None) -> tuple:
    """Returns (vessels to show, vessels on hire today, threshold).
    With lookback_months, vessels already redelivered within that period are
    added (flag past=True) so the past can be compared with today."""
    base = df.dropna(subset=["redelivery"])
    if statuses is not None:
        base = base[base["status"].isin(statuses)]
    if exclude_tct:
        base = base[~base["is_tct"]]
    if only_current:
        base = base[base["delivery"] <= today]

    # A vessel can have several segments -> keep its latest redelivery
    vessels = (
        base.sort_values("redelivery")
        .groupby("vessel_code", as_index=False)
        .last()
    )
    on_hire = vessels[vessels["redelivery"] >= today]  # still on hire today
    threshold = today + pd.DateOffset(months=min_months)
    out = on_hire[on_hire["redelivery"] >= threshold].copy()
    out["past"] = False
    edges = [today + pd.DateOffset(months=lo) for lo, _, _ in BUCKETS] + [pd.Timestamp.max]
    out["Remaining"] = pd.cut(out["redelivery"], bins=edges,
                              labels=[lbl for _, _, lbl in BUCKETS], right=False).astype(str)

    if lookback_months:
        start = today - pd.DateOffset(months=lookback_months)
        past = vessels[(vessels["redelivery"] < today) & (vessels["redelivery"] >= start)].copy()
        past["past"] = True
        p_edges = [pd.Timestamp.min] + [today + pd.DateOffset(months=hi) for _, hi, _ in PAST_BUCKETS]
        past["Remaining"] = pd.cut(past["redelivery"], bins=p_edges,
                                   labels=[lbl for _, _, lbl in PAST_BUCKETS], right=False).astype(str)
        out = pd.concat([past, out], ignore_index=True)

    out["years_remaining"] = (out["redelivery"] - today).dt.days / 365.25
    return out.sort_values("redelivery"), on_hire, threshold


# ── Charts ────────────────────────────────────────────────────────────────────
def _lighten(hex_color: str, amount: float) -> str:
    """Blend a colour with white (amount 0 = unchanged, 1 = white)."""
    h = hex_color.lstrip("#")
    rgb = [int(h[i:i + 2], 16) for i in (0, 2, 4)]
    return "#" + "".join(f"{int(v + (255 - v) * amount):02X}" for v in rgb)


def _by_bucket(lt: pd.DataFrame, title: str, subtitle: str) -> go.Figure:
    data = lt.groupby(["past", "Remaining", "segment"]).size().reset_index(name="Vessels")
    present = set(data["Remaining"])
    past_order = [lbl for _, _, lbl in PAST_BUCKETS if lbl in present]
    order = past_order + [lbl for _, _, lbl in BUCKETS if lbl in present]

    fig = go.Figure()
    for is_past in (True, False):
        for seg in SEGMENT_ORDER:
            d = data[(data["segment"] == seg) & (data["past"] == is_past)]
            if d.empty:
                continue
            # already redelivered = lighter tint of the same colour (text stays sharp)
            color = _lighten(SEGMENT_COLORS[seg], 0.55) if is_past else SEGMENT_COLORS[seg]
            fig.add_trace(go.Bar(
                name=seg, legendgroup=seg, x=d["Remaining"], y=d["Vessels"],
                showlegend=not is_past or seg not in set(data.loc[~data["past"], "segment"]),
                marker=dict(color=color, line=dict(color="white", width=2)),
                text=d["Vessels"], textposition="inside", insidetextanchor="middle", textangle=0,
                textfont=dict(color=c.text_color_for(color), size=13),
                hovertemplate=(f"<b>{seg}</b><br>%{{x}}: %{{y}} vessels"
                               f"{' (already redelivered)' if is_past else ''}<extra></extra>"),
            ))
    totals = data.groupby("Remaining")["Vessels"].sum().reindex(order)
    c.add_stack_totals(fig, order, totals.tolist())
    fig.update_layout(barmode="stack", bargap=0.42)
    if past_order and len(order) > len(past_order):
        x = len(past_order) - 0.5  # between the last past bucket and the first future one
        fig.add_shape(type="line", x0=x, x1=x, y0=0, y1=1, yref="paper",
                      line=dict(color=c.BRAND_RED, width=2, dash="dash"))
        fig.add_annotation(x=x, y=1, yref="paper", text="<b>Today</b>", showarrow=False,
                           xanchor="left", yanchor="top", xshift=4,
                           font=dict(color=c.BRAND_RED, size=12))
    fig.update_xaxes(type="category", categoryorder="array", categoryarray=order,
                     title=None, tickfont=dict(size=14))
    fig.update_yaxes(title="Number of vessels")
    return c.style_figure(fig, title=title, subtitle=subtitle, height=520)


def _donut(lt: pd.DataFrame) -> go.Figure:
    counts = lt["segment"].value_counts().reindex(SEGMENT_ORDER).dropna().astype(int)
    colors = [SEGMENT_COLORS[s] for s in counts.index]
    fig = go.Figure(go.Pie(
        labels=counts.index, values=counts.values, hole=0.6, sort=False,
        marker=dict(colors=colors, line=dict(color="white", width=2)),
        textinfo="label+value", textposition="inside", insidetextorientation="horizontal",
        textfont=dict(size=14, color=[c.text_color_for(x) for x in colors]),
        hovertemplate="%{label}: %{value} vessels (%{percent})<extra></extra>",
    ))
    fig.add_annotation(text=f"<b>{len(lt)}</b><br>vessels", showarrow=False,
                       font=dict(size=24, color=c.TEXT_COLOR))
    c.style_figure(fig, title="Split by segment", height=460)
    fig.update_layout(showlegend=False)
    return fig


def _by_type(lt: pd.DataFrame) -> go.Figure:
    data = (lt.groupby(["vessel_type", "segment"]).size()
            .reset_index(name="Vessels").sort_values("Vessels"))
    fig = go.Figure()
    for seg in SEGMENT_ORDER:
        d = data[data["segment"] == seg]
        if d.empty:
            continue
        fig.add_trace(go.Bar(
            name=seg, y=d["vessel_type"], x=d["Vessels"], orientation="h",
            marker=dict(color=SEGMENT_COLORS[seg], line=dict(color="white", width=1)),
            text=d["Vessels"], textposition="outside", cliponaxis=False,
            textfont=dict(color=c.TEXT_COLOR),
            hovertemplate="%{y}: %{x} vessels<extra></extra>",
        ))
    n = data["vessel_type"].nunique()
    fig.update_yaxes(categoryorder="total ascending", showgrid=False, title=None)
    fig.update_xaxes(title="Number of vessels", showgrid=True, gridcolor=c.GRID_COLOR)
    c.style_figure(fig, title="Vessels by type", height=max(460, 28 * n + 120))
    # colours already explained by the main chart -> no legend (it overlapped the top bar)
    fig.update_layout(margin=dict(t=60, b=10, l=10, r=40), barmode="stack", showlegend=False)
    return fig


def _timeline(lt: pd.DataFrame, today: pd.Timestamp) -> go.Figure:
    g = lt.assign(start=today).sort_values("redelivery")
    fig = px.timeline(g, x_start="start", x_end="redelivery", y="vessel_code",
                      color="segment", color_discrete_map=SEGMENT_COLORS,
                      hover_data={"vessel_type": True, "start": False,
                                  "redelivery": "|%d %b %Y", "segment": False,
                                  "Remaining": True},
                      category_orders={"segment": SEGMENT_ORDER})
    fig.update_traces(marker_line_color="white", marker_line_width=0.5)
    fig.update_yaxes(title=None, categoryorder="array",
                     categoryarray=g["vessel_code"].tolist()[::-1], tickfont=dict(size=10),
                     showgrid=False)
    # vertical markers: today + each bucket boundary
    for lo, _, lbl in BUCKETS[1:]:
        x = today + pd.DateOffset(months=lo)
        fig.add_shape(type="line", x0=x, x1=x, y0=0, y1=1, yref="paper", layer="above",
                      line=dict(color=c.GRID_COLOR, width=1, dash="dot"))
    fig.add_shape(type="line", x0=today, x1=today, y0=0, y1=1, yref="paper", layer="above",
                  line=dict(color=c.BRAND_RED, width=2))
    fig.add_annotation(x=today, y=1, yref="paper", text="<b>Today</b>", showarrow=False,
                       yanchor="bottom", xanchor="left", font=dict(color=c.BRAND_RED, size=12))
    c.style_figure(fig, height=max(420, 16 * len(g) + 140))
    fig.update_xaxes(showgrid=True, gridcolor=c.GRID_COLOR, title=None)
    fig.update_layout(margin=dict(t=40, b=10, l=10, r=10))
    return fig


# ── Time series: number of TCs on hire over time ─────────────────────────────
HISTORY = {"Last 12 months": 12, "Last 2 years": 24, "Last 5 years": 60, "All history": None}
FORWARD = {"None": 0, "+6 months": 6, "+12 months": 12, "+24 months": 24}


def tc_segments(df: pd.DataFrame, statuses, exclude_tct: bool, segments: list) -> pd.DataFrame:
    """Segment rows used for the time series (same filters as the page)."""
    base = df.dropna(subset=["delivery", "redelivery"])
    if statuses is not None:
        base = base[base["status"].isin(statuses)]
    if exclude_tct:
        base = base[~base["is_tct"]]
    return base[base["segment"].isin(segments)]


def count_on_hire(seg: pd.DataFrame, dates) -> pd.DataFrame:
    """Number of distinct vessels on hire (Delivery <= date < Redelivery) at
    each date, by segment. Returns a DataFrame: index = date, columns = segments."""
    dates = pd.DatetimeIndex(dates)
    rows = []
    for d in dates:
        on = seg[(seg["delivery"] <= d) & (seg["redelivery"] > d)]
        counts = on.drop_duplicates("vessel_code")["segment"].value_counts()
        rows.append(counts.rename(d))
    out = pd.DataFrame(rows).reindex(columns=[s for s in SEGMENT_ORDER]).fillna(0).astype(int)
    out.index = dates
    return out.loc[:, out.sum() > 0]


def _ts_chart(ts: pd.DataFrame, today: pd.Timestamp) -> go.Figure:
    fig = go.Figure()
    # stacked areas, Dry at the bottom
    for seg in [s for s in SEGMENT_ORDER if s in ts.columns]:
        color = SEGMENT_COLORS[seg]
        fig.add_trace(go.Scatter(
            x=ts.index, y=ts[seg], name=seg, stackgroup="fleet", mode="lines",
            line=dict(color=color, width=1.5), fillcolor=_lighten(color, 0.15),
            hovertemplate=f"<b>{seg}</b> %{{x|%b %Y}}: %{{y}} vessels<extra></extra>",
        ))
    total = ts.sum(axis=1)
    fig.add_trace(go.Scatter(
        x=ts.index, y=total, name="Total", mode="lines",
        line=dict(color=c.TEXT_COLOR, width=2, dash="dot"),
        hovertemplate="<b>Total</b> %{x|%b %Y}: %{y} vessels<extra></extra>",
    ))
    if ts.index.max() > today:
        fig.add_vrect(x0=today, x1=ts.index.max(), fillcolor="#F4F4F4", opacity=0.6,
                      layer="below", line_width=0)
        fig.add_annotation(x=today, y=1, yref="paper", xanchor="left", yanchor="top", xshift=6,
                           text="Contracted (known redeliveries)", showarrow=False,
                           font=dict(color=c.MUTED_TEXT, size=11))
    fig.add_shape(type="line", x0=today, x1=today, y0=0, y1=1, yref="paper",
                  line=dict(color=c.BRAND_RED, width=2, dash="dash"))
    fig.add_annotation(x=today, y=1, yref="paper", xanchor="right", yanchor="top", xshift=-4,
                       text="<b>Today</b>", showarrow=False, font=dict(color=c.BRAND_RED, size=12))
    fig.update_yaxes(title="Number of vessels on hire", rangemode="tozero")
    fig.update_layout(hovermode="x unified")
    return c.style_figure(fig, title="Number of TCs on hire over time",
                          subtitle="Distinct vessels with Delivery ≤ date < Redelivery, by segment (monthly)",
                          height=500, legend="bottom")


def _render_timeseries(df: pd.DataFrame, today: pd.Timestamp, statuses, exclude_tct: bool,
                       segments: list) -> None:
    st.divider()
    st.markdown("#### 📈 TCs on hire over time")
    seg = tc_segments(df, statuses, exclude_tct, segments)
    if seg.empty:
        st.info("No segment with both Delivery and Redelivery dates for the time series.")
        return

    h1, h2, _ = st.columns([1, 1, 2])
    hist_lbl = h1.selectbox("History", list(HISTORY), index=1, key="fleet_ts_history")
    fwd_lbl = h2.selectbox("Look ahead", list(FORWARD), index=2, key="fleet_ts_forward",
                           help="Shows how the fleet runs off with the redeliveries already known.")
    months = HISTORY[hist_lbl]
    start = (seg["delivery"].min() if months is None else today - pd.DateOffset(months=months))
    end = today + pd.DateOffset(months=FORWARD[fwd_lbl])
    dates = pd.date_range(start.to_period("M").to_timestamp(), end, freq="MS")
    dates = dates.union(pd.DatetimeIndex([today]))  # exact point for today
    ts = count_on_hire(seg, dates)
    if ts.empty:
        st.info("No vessel on hire over this period.")
        return

    # Today vs 1 / 2 years ago
    ref = count_on_hire(seg, [today, today - pd.DateOffset(years=1), today - pd.DateOffset(years=2)])
    tot = ref.sum(axis=1).tolist()
    m = st.columns(3)
    m[0].metric(f"TCs on hire today", tot[0])
    m[1].metric(f"1 year ago ({today - pd.DateOffset(years=1):%d %b %Y})", tot[1],
                delta=tot[0] - tot[1], help="Delta = today minus 1 year ago")
    m[2].metric(f"2 years ago ({today - pd.DateOffset(years=2):%d %b %Y})", tot[2],
                delta=tot[0] - tot[2], help="Delta = today minus 2 years ago")

    st.plotly_chart(_ts_chart(ts, today), use_container_width=True)

    with st.expander("📋 Monthly figures"):
        table = ts.copy()
        table["Total"] = table.sum(axis=1)
        table.index = table.index.strftime("%d %b %Y")
        st.dataframe(table, use_container_width=True)
        st.download_button("⬇️ Export time series (CSV)", table.to_csv().encode("utf-8"),
                           file_name=f"tc_on_hire_timeseries_{today:%Y%m%d}.csv", mime="text/csv",
                           key="dl_fleet_ts")


# ── Render ────────────────────────────────────────────────────────────────────
def render() -> None:
    st.markdown("### 🚢 Fleet — Time to Redelivery")
    st.caption(
        f"Vessels on hire as of today, by time remaining until **Redelivery Date**. "
        f"IMOS reports **{REPORT_SEGMENTS}** (delivery / redelivery) and "
        f"**{REPORT_TYPES}** (vessel type), merged on the vessel code."
    )

    if st.button("🔄 Load / Refresh", key="btn_fleet", type="primary"):
        with st.spinner("Loading data from Veslink…"):
            try:
                st.session_state[CACHE_KEY] = load_fleet()
            except requests.HTTPError as e:
                st.error(f"❌ API error ({e.response.status_code}): {e.response.text[:300]}")
                st.session_state.pop(CACHE_KEY, None)
                return
            except Exception as e:
                st.error(f"❌ {e}")
                st.session_state.pop(CACHE_KEY, None)
                return

    cached = st.session_state.get(CACHE_KEY)
    if cached is None:
        st.info("Click to run the report.")
        return

    df = cached["df"]
    today = pd.Timestamp.now().normalize()
    has_tct = cached["tct_col"] is not None

    with st.container(border=True):
        f1, f2, f3 = st.columns([1.2, 1.3, 2])
        period_lbl = f1.selectbox("Minimum remaining period", list(MIN_PERIODS), index=0,
                                  key="fleet_min_period")
        segments = [s for s in SEGMENT_ORDER if s in df["segment"].unique()]
        seg_sel = f2.multiselect("Segments", segments, default=segments, key="fleet_segments")
        # Status options = every status found in Vessel_segments; default
        # Delivered / Redelivered / Fixed (matched case-insensitively)
        all_statuses = sorted(df["status"].unique(), key=str.lower)
        default_status = [s for s in all_statuses if s.lower() in {d.lower() for d in DEFAULT_STATUSES}]
        status_sel = f3.multiselect("Status (Vessel_segments)", all_statuses, default=default_status,
                                    key="fleet_status", disabled=not cached.get("has_status", False),
                                    help="Default: Delivered, Redelivered, Fixed. Add other statuses "
                                         "(e.g. Canceled) if needed.")
        g1, g2, g3 = st.columns([1.2, 1.3, 2])
        only_current = g1.toggle("Started segments only", value=False, key="fleet_current",
                                 help="Ignore segments that start in the future (Delivery > today). "
                                      "Off by default so that 'Fixed' vessels not yet delivered are counted.")
        exclude_tct = g2.toggle("Exclude TCT", value=True, key="fleet_tct", disabled=not has_tct,
                                help="Excludes segments flagged TCT in Vessel_segments.")
        lookback_lbl = g3.selectbox("Already redelivered (compare with the past)", list(LOOKBACKS),
                                    index=0, key="fleet_lookback",
                                    help="Adds vessels whose redelivery date is already past, "
                                         "shown in lighter colours on the left of the chart.")

    min_months = MIN_PERIODS[period_lbl]
    lt, on_hire, threshold = fleet_on_hire(df, today, min_months, only_current, exclude_tct and has_tct,
                                             statuses=status_sel if cached.get("has_status") else None,
                                             lookback_months=LOOKBACKS[lookback_lbl])
    lt = lt[lt["segment"].isin(seg_sel)]
    past = lt[lt["past"]]
    lt_all, lt = lt, lt[~lt["past"]]  # lt = on hire today (KPIs, donut, type, timeline)

    if lt_all.empty:
        st.warning("No vessel matches the current selection.")
        return

    counts = lt["segment"].value_counts()
    k = st.columns(5 if len(past) else 4)
    k[0].metric("🚢 Vessels", len(lt), help=f"{len(on_hire)} vessels on hire as of today")
    for col, seg in zip(k[1:4], ["Dry", "Wet", "Gas"]):
        col.metric(seg, int(counts.get(seg, 0)))
    if len(past):
        k[4].metric("↩️ Already redelivered", len(past), help=f"{lookback_lbl}")

    title = f"Time remaining until redelivery by segment (as of {today:%d %b %Y})"
    subtitle = (f"All vessels on hire as of today — {len(lt)} vessels" if min_months == 0 else
                f"Redelivery on or after {threshold:%d %b %Y} ({period_lbl}) — {len(lt)} vessels")
    if len(past):
        subtitle += f" · {len(past)} already redelivered ({lookback_lbl.lower()}, lighter colours)"

    st.plotly_chart(_by_bucket(lt_all, title, subtitle), use_container_width=True)

    if lt.empty:
        st.info("No vessel on hire today for the current selection.")
        return

    left, right = st.columns([1, 2], gap="large")
    left.plotly_chart(_donut(lt), use_container_width=True)
    right.plotly_chart(_by_type(lt), use_container_width=True)

    _render_timeseries(df, today, status_sel if cached.get("has_status") else None,
                       exclude_tct and has_tct, seg_sel)

    with st.expander(f"🗓️ Timeline per vessel ({len(lt)})"):
        st.plotly_chart(_timeline(lt, today), use_container_width=True)

    st.markdown("#### 📋 Vessel list")
    table = lt_all[["vessel_code", "vessel_type", "segment", "Remaining", "delivery", "redelivery",
                "years_remaining"]].rename(
        columns={"vessel_code": "Vessel code", "vessel_type": "Vessel type", "segment": "Segment",
                 "delivery": "Delivery", "redelivery": "Redelivery", "years_remaining": "Years remaining"})
    table["Remaining"] = table["Remaining"].astype(str).str.replace("<br>", " ", regex=False)
    st.dataframe(table, use_container_width=True, hide_index=True,
                 column_config={"Delivery": st.column_config.DateColumn(format="DD MMM YYYY"),
                                "Redelivery": st.column_config.DateColumn(format="DD MMM YYYY"),
                                "Years remaining": st.column_config.NumberColumn(format="%.1f")})
    st.download_button("⬇️ Export vessel list (CSV)", table.to_csv(index=False).encode("utf-8"),
                       file_name=f"fleet_redelivery_{today:%Y%m%d}.csv", mime="text/csv",
                       key="dl_fleet")

    with st.expander("ℹ️ Data checks"):
        if not cached.get("has_status"):
            st.warning(f"No 'Status' column found in {REPORT_SEGMENTS}: status filter disabled.")
        st.write(f"Segments by Status in {REPORT_SEGMENTS}:", df["status"].value_counts())
        st.write(f"TCT column detected in {REPORT_SEGMENTS}: **{cached['tct_col'] or 'none found'}**")
        st.write(f"Vessels with no type in {REPORT_TYPES}: **{cached['n_unmatched']}**")
        st.write(f"{REPORT_SEGMENTS} columns:", cached["seg_cols"])
        st.write(f"{REPORT_TYPES} columns:", cached["typ_cols"])


if __name__ == "__main__":
    st.set_page_config(page_title="Fleet — Time to Redelivery", layout="wide")
    render()
