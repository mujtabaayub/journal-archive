"""
Phase 3: Local web interface for browsing and exploring the journal archive.

Run from project root:
    streamlit run src/app.py
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "journal.db"

st.set_page_config(page_title="Journal Archive", layout="wide", page_icon="📓")


@st.cache_resource
def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


@st.cache_data
def load_data() -> pd.DataFrame:
    conn = get_conn()
    df = pd.read_sql_query(
        """
        SELECT d.draft_id, d.gmail_date, d.subject, d.body_text, d.word_count,
               t.entry_type, t.themes_json, t.entities_json,
               t.mood, t.summary, t.is_pivotal, t.pivotal_reason
        FROM drafts d
        JOIN tags t ON d.draft_id = t.draft_id
        ORDER BY d.gmail_date
        """,
        conn,
    )
    df["date"] = pd.to_datetime(df["gmail_date"]).dt.tz_localize(None)
    df["year"] = df["date"].dt.year.astype(int)
    df["themes"] = df["themes_json"].apply(lambda x: json.loads(x) if x else [])
    df["entities"] = df["entities_json"].apply(lambda x: json.loads(x) if x else [])
    return df


def fts_search(query: str, limit: int = 100) -> list[str]:
    conn = get_conn()
    rows = conn.execute(
        """
        SELECT d.draft_id
        FROM drafts_fts
        JOIN drafts d ON drafts_fts.rowid = d.rowid
        WHERE drafts_fts MATCH ?
        ORDER BY drafts_fts.rank
        LIMIT ?
        """,
        (query, limit),
    ).fetchall()
    return [r[0] for r in rows]


def render_entry(row: pd.Series, expanded: bool = False) -> None:
    date_str = row["date"].strftime("%B %d, %Y")
    pivot_icon = "⭐ " if row["is_pivotal"] else ""
    entry_type = (row["entry_type"] or "").replace("_", " ")
    label = f"{pivot_icon}{date_str} · {row['mood']} · {entry_type}"

    with st.expander(label, expanded=expanded):
        col1, col2 = st.columns([3, 1])
        with col1:
            st.markdown(f"**{row['summary']}**")
            if row["is_pivotal"] and row["pivotal_reason"]:
                st.info(f"⭐ {row['pivotal_reason']}")
            st.divider()
            body = row["body_text"] or ""
            st.text(body[:4000] + ("\n\n[truncated — entry continues]" if len(body) > 4000 else ""))
        with col2:
            if row["themes"]:
                st.markdown("**Themes**")
                for t in row["themes"]:
                    st.markdown(f"- {t}")
            if row["entities"]:
                st.markdown("**Mentions**")
                for e in row["entities"][:8]:
                    st.markdown(f"- {e}")
            st.caption(f"{int(row['word_count'] or 0):,} words")


def browse_tab(df: pd.DataFrame, filtered: pd.DataFrame) -> None:
    st.caption(f"Showing {len(filtered):,} of {len(df):,} entries")

    page_size = 20
    total_pages = max(1, (len(filtered) - 1) // page_size + 1)
    page = st.number_input("Page", min_value=1, max_value=total_pages, value=1, step=1) - 1

    for _, row in filtered.iloc[page * page_size : (page + 1) * page_size].iterrows():
        render_entry(row)


def search_tab(df: pd.DataFrame) -> None:
    query = st.text_input("Search your journal", placeholder="e.g. feeling lost, Proust, running a marathon", key="search_query")
    if not query:
        st.caption("Enter a search term to search across all entry text and subjects.")
        return

    q = query.lower()
    mask = (
        df["body_text"].str.lower().str.contains(q, na=False)
        | df["subject"].str.lower().str.contains(q, na=False)
        | df["summary"].str.lower().str.contains(q, na=False)
    )
    results = df[mask].copy()
    st.caption(f"{len(results)} results for '{query}'")
    for _, row in results.iterrows():
        render_entry(row)


def insights_tab(df: pd.DataFrame) -> None:
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total entries", f"{len(df):,}")
    c2.metric("Pivotal entries", f"{int(df['is_pivotal'].sum()):,}")
    c3.metric("Years covered", f"{int(df['year'].min())}–{int(df['year'].max())}")
    c4.metric("Total words written", f"{int(df['word_count'].sum()):,}")

    st.divider()

    # Entries per year
    vol = df.groupby("year").size().reset_index(name="entries")
    fig = px.bar(vol, x="year", y="entries", title="Entries per year",
                 color_discrete_sequence=["#5B8DB8"])
    fig.update_layout(xaxis=dict(dtick=1))
    st.plotly_chart(fig, use_container_width=True)

    # Entry types over time
    type_year = df.groupby(["year", "entry_type"]).size().reset_index(name="count")
    fig2 = px.bar(type_year, x="year", y="count", color="entry_type",
                  title="Entry types over time", barmode="stack")
    fig2.update_layout(xaxis=dict(dtick=1))
    st.plotly_chart(fig2, use_container_width=True)

    # Mood over time (top 8 moods)
    top_moods = df["mood"].value_counts().head(8).index.tolist()
    mood_year = (
        df[df["mood"].isin(top_moods)]
        .groupby(["year", "mood"])
        .size()
        .reset_index(name="count")
    )
    fig3 = px.bar(mood_year, x="year", y="count", color="mood",
                  title="Mood over time (top 8)", barmode="stack")
    fig3.update_layout(xaxis=dict(dtick=1))
    st.plotly_chart(fig3, use_container_width=True)

    # Top themes over time
    theme_rows = [
        {"year": row["year"], "theme": t.lower()}
        for _, row in df.iterrows()
        for t in row["themes"]
    ]
    theme_df = pd.DataFrame(theme_rows)
    top_themes = theme_df["theme"].value_counts().head(12).index.tolist()
    theme_year = (
        theme_df[theme_df["theme"].isin(top_themes)]
        .groupby(["year", "theme"])
        .size()
        .reset_index(name="count")
    )
    fig4 = px.line(theme_year, x="year", y="count", color="theme",
                   title="Top 12 themes over time", markers=True)
    fig4.update_layout(xaxis=dict(dtick=1))
    st.plotly_chart(fig4, use_container_width=True)

    # Word count per year
    words = df.groupby("year")["word_count"].sum().reset_index(name="words")
    fig5 = px.bar(words, x="year", y="words", title="Words written per year",
                  color_discrete_sequence=["#8DB85B"])
    fig5.update_layout(xaxis=dict(dtick=1))
    st.plotly_chart(fig5, use_container_width=True)


def pivotal_tab(df: pd.DataFrame) -> None:
    pivotal = df[df["is_pivotal"] == 1].sort_values("date").reset_index(drop=True)
    st.caption(
        f"{len(pivotal)} pivotal entries · "
        f"{int(pivotal['year'].min())}–{int(pivotal['year'].max())}"
    )

    fig = px.scatter(
        pivotal, x="date", y="entry_type", color="mood",
        hover_data={"summary": True, "pivotal_reason": True, "date": False, "entry_type": False},
        title="Pivotal entries across time",
        height=350,
        labels={"entry_type": "Type"},
    )
    fig.update_traces(marker=dict(size=10))
    st.plotly_chart(fig, use_container_width=True)

    st.divider()
    for _, row in pivotal.iterrows():
        render_entry(row)


def main() -> None:
    st.title("📓 Journal Archive")
    df = load_data()

    with st.sidebar:
        st.header("Filters")
        years = sorted(df["year"].unique())
        year_range = st.slider(
            "Year range", int(min(years)), int(max(years)),
            (int(min(years)), int(max(years))),
            key="year_range"
        )
        entry_types = sorted(df["entry_type"].dropna().unique())
        selected_types = st.multiselect("Entry type", entry_types, default=entry_types, key="entry_types")
        moods = sorted(df["mood"].dropna().unique())
        selected_moods = st.multiselect("Mood", moods, key="moods")
        pivotal_only = st.checkbox("Pivotal entries only", key="pivotal_only")

    filtered = df[
        (df["year"] >= year_range[0])
        & (df["year"] <= year_range[1])
        & (df["entry_type"].isin(selected_types))
    ]
    if selected_moods:
        filtered = filtered[filtered["mood"].isin(selected_moods)]
    if pivotal_only:
        filtered = filtered[filtered["is_pivotal"] == 1]

    tab1, tab2, tab3, tab4 = st.tabs(["Browse", "Search", "Insights", "Pivotal Entries"])
    with tab1:
        browse_tab(df, filtered)
    with tab2:
        search_tab(df)
    with tab3:
        insights_tab(df)
    with tab4:
        pivotal_tab(df)


if __name__ == "__main__":
    main()
