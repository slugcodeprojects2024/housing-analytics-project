"""
Housing Analytics dashboard.

Run locally:
    streamlit run src/dashboard/app.py
"""
from __future__ import annotations

import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# Add project root to path so imports work when run via streamlit
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from src.dashboard.queries import (
    get_national_kpis,
    get_metro_kpis,
    get_price_trends,
    get_mortgage_vs_price,
    get_affordability_over_time,
    get_metro_comparison,
    get_zip_comparison,
    get_all_metros,
    get_all_counties,
)

# ---- Page config -----------------------------------------------------------

st.set_page_config(
    page_title="Housing Market Analytics",
    page_icon="🏠",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---- Sidebar ---------------------------------------------------------------

st.sidebar.title("🏠 Housing Analytics")
st.sidebar.markdown("---")

view = st.sidebar.radio(
    "View",
    ["Overview", "Trends", "Affordability", "Compare Metros", "Explore ZIPs", "Ask Claude"],
    label_visibility="collapsed",
)

st.sidebar.markdown("---")
st.sidebar.caption("Data: Zillow Research, FRED | Built with Streamlit + Claude API")

# ---- Helper ----------------------------------------------------------------

def format_price(val):
    if val is None:
        return "—"
    if val >= 1_000_000:
        return f"${val / 1_000_000:.2f}M"
    return f"${val:,.0f}"


def format_pct(val):
    if val is None:
        return "—"
    return f"{val:+.1f}%"


# ---- Views -----------------------------------------------------------------

if view == "Overview":
    st.title("Market Overview")

    # National KPIs
    kpis = get_national_kpis()

    st.subheader("National Market")
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Median Home Value", format_price(kpis["current_price"]))
    col2.metric("YoY Change", format_pct(kpis["yoy_change"]))
    col3.metric("30Y Mortgage Rate", f"{kpis['mortgage_rate']:.2f}%" if kpis["mortgage_rate"] else "—")
    col4.metric("Price-to-Income", f"{kpis['price_to_income']:.1f}x" if kpis["price_to_income"] else "—")

    st.caption(f"As of {kpis['current_date']}")

    # Metro selector for detailed KPIs
    st.markdown("---")
    st.subheader("Metro Spotlight")

    metros = get_all_metros()

    # Default to San Jose metro if available
    default_metros = [m for m in metros if "San Jose" in m]
    default_idx = metros.index(default_metros[0]) if default_metros else 0

    selected_metro = st.selectbox("Select a metro area", metros, index=default_idx)

    if selected_metro:
        metro_kpis = get_metro_kpis(selected_metro)
        col1, col2, col3 = st.columns(3)
        col1.metric("Median Home Value", format_price(metro_kpis["current_price"]))
        col2.metric("YoY Change", format_pct(metro_kpis["yoy_change"]))
        col3.metric("Median Rent", format_price(metro_kpis["current_rent"]))

        # Price trend chart for selected metro vs national
        st.markdown("---")
        trend_data = get_price_trends([selected_metro, "United States"])
        if not trend_data.empty:
            fig = px.line(
                trend_data,
                x="metric_date",
                y="value",
                color="name",
                title=f"Home Values: {selected_metro} vs. National",
                labels={"metric_date": "", "value": "Home Value ($)", "name": ""},
            )
            fig.update_layout(
                hovermode="x unified",
                yaxis_tickformat="$,.0f",
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
                height=450,
            )
            st.plotly_chart(fig, use_container_width=True)


elif view == "Trends":
    st.title("Price Trends")
    st.caption("Compare home value trends across metro areas over time")

    metros = get_all_metros()

    # Curated defaults: major metros across different markets
    default_selections = [
        "San Jose-Sunnyvale-Santa Clara, CA",
        "San Francisco-Oakland-Berkeley, CA",
        "New York-Newark-Jersey City, NY-NJ-PA",
        "Austin-Round Rock-Georgetown, TX",
    ]
    defaults = [m for m in default_selections if m in metros]

    selected = st.multiselect(
        "Select metro areas to compare",
        metros,
        default=defaults,
        max_selections=8,
    )

    if selected:
        # Add national as a baseline
        codes = selected + (["United States"] if "United States" not in selected else [])
        trend_data = get_price_trends(codes)

        if not trend_data.empty:
            # Date range filter
            min_date = trend_data["metric_date"].min().to_pydatetime()
            max_date = trend_data["metric_date"].max().to_pydatetime()

            date_range = st.slider(
                "Date range",
                min_value=min_date,
                max_value=max_date,
                value=(min_date, max_date),
                format="YYYY-MM",
            )

            filtered = trend_data[
                (trend_data["metric_date"] >= date_range[0])
                & (trend_data["metric_date"] <= date_range[1])
            ]

            fig = px.line(
                filtered,
                x="metric_date",
                y="value",
                color="name",
                title="Home Value Trends",
                labels={"metric_date": "", "value": "Home Value ($)", "name": ""},
            )
            fig.update_layout(
                hovermode="x unified",
                yaxis_tickformat="$,.0f",
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
                height=500,
            )
            st.plotly_chart(fig, use_container_width=True)

            # Normalized view (index to 100 at start date)
            with st.expander("Show normalized view (indexed to 100)"):
                normalized = filtered.copy()
                for name in normalized["name"].unique():
                    mask = normalized["name"] == name
                    first_val = normalized.loc[mask, "value"].iloc[0]
                    if first_val > 0:
                        normalized.loc[mask, "value"] = (normalized.loc[mask, "value"] / first_val) * 100

                fig2 = px.line(
                    normalized,
                    x="metric_date",
                    y="value",
                    color="name",
                    title="Normalized Home Values (Start = 100)",
                    labels={"metric_date": "", "value": "Index (100 = start)", "name": ""},
                )
                fig2.update_layout(
                    hovermode="x unified",
                    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
                    height=500,
                )
                st.plotly_chart(fig2, use_container_width=True)
    else:
        st.info("Select at least one metro area to see trends.")


elif view == "Affordability":
    st.title("Affordability")
    st.caption("How housing costs relate to income and mortgage rates over time")

    col1, col2 = st.columns(2)

    with col1:
        # Price-to-income ratio over time
        afford_data = get_affordability_over_time()
        if not afford_data.empty:
            fig = px.line(
                afford_data,
                x="date",
                y="price_to_income",
                title="National Price-to-Income Ratio",
                labels={"date": "", "price_to_income": "Ratio"},
            )
            fig.add_hline(
                y=5, line_dash="dash", line_color="red",
                annotation_text="Affordability threshold (5x)",
                annotation_position="top left",
            )
            fig.update_layout(height=450, hovermode="x unified")
            st.plotly_chart(fig, use_container_width=True)

    with col2:
        # Mortgage rate vs home price (dual axis)
        mortgage_data = get_mortgage_vs_price()
        if not mortgage_data.empty:
            fig = make_subplots(specs=[[{"secondary_y": True}]])

            fig.add_trace(
                go.Scatter(
                    x=mortgage_data["date"],
                    y=mortgage_data["home_price"],
                    name="Home Price",
                    line=dict(color="#2196F3"),
                ),
                secondary_y=False,
            )
            fig.add_trace(
                go.Scatter(
                    x=mortgage_data["date"],
                    y=mortgage_data["mortgage_rate"],
                    name="Mortgage Rate",
                    line=dict(color="#FF5722"),
                ),
                secondary_y=True,
            )

            fig.update_layout(
                title_text="Home Prices vs. Mortgage Rates",
                hovermode="x unified",
                height=450,
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            )
            fig.update_yaxes(title_text="Home Value ($)", tickformat="$,.0f", secondary_y=False)
            fig.update_yaxes(title_text="Mortgage Rate (%)", secondary_y=True)

            st.plotly_chart(fig, use_container_width=True)

    # Monthly payment estimate
    st.markdown("---")
    st.subheader("Monthly Payment Estimator")
    st.caption("What would a home cost per month at current rates?")

    est_col1, est_col2, est_col3 = st.columns(3)
    with est_col1:
        home_price_input = st.number_input("Home price ($)", value=500000, step=25000, format="%d")
    with est_col2:
        down_pct = st.slider("Down payment (%)", 0, 50, 20)
    with est_col3:
        kpis = get_national_kpis()
        rate = kpis["mortgage_rate"] if kpis["mortgage_rate"] else 7.0
        rate_input = st.number_input("Interest rate (%)", value=rate, step=0.125, format="%.3f")

    loan_amount = home_price_input * (1 - down_pct / 100)
    monthly_rate = (rate_input / 100) / 12
    n_payments = 360  # 30 years
    if monthly_rate > 0:
        monthly_payment = loan_amount * (monthly_rate * (1 + monthly_rate)**n_payments) / ((1 + monthly_rate)**n_payments - 1)
    else:
        monthly_payment = loan_amount / n_payments

    st.metric("Estimated Monthly Payment", f"${monthly_payment:,.0f}")


elif view == "Compare Metros":
    st.title("Metro Comparison")
    st.caption("Compare current home values across metro areas")

    metros = get_all_metros()

    # Bay Area + major metros as defaults
    default_selections = [
        "San Jose-Sunnyvale-Santa Clara, CA",
        "San Francisco-Oakland-Berkeley, CA",
        "Los Angeles-Long Beach-Anaheim, CA",
        "New York-Newark-Jersey City, NY-NJ-PA",
        "Austin-Round Rock-Georgetown, TX",
        "Denver-Aurora-Lakewood, CO",
        "Seattle-Tacoma-Bellevue, WA",
        "Miami-Fort Lauderdale-Pompano Beach, FL",
        "Phoenix-Mesa-Chandler, AZ",
        "Dallas-Fort Worth-Arlington, TX",
    ]
    defaults = [m for m in default_selections if m in metros]

    selected = st.multiselect(
        "Select metros to compare",
        metros,
        default=defaults,
        max_selections=15,
    )

    if selected:
        comparison = get_metro_comparison(selected)
        if not comparison.empty:
            # Shorten metro names for readability
            comparison["short_name"] = comparison["metro"].str.split(",").str[0]

            fig = px.bar(
                comparison,
                x="short_name",
                y="home_price",
                title="Current Median Home Value by Metro",
                labels={"short_name": "", "home_price": "Home Value ($)"},
                color="home_price",
                color_continuous_scale="RdYlBu_r",
            )
            fig.update_layout(
                yaxis_tickformat="$,.0f",
                showlegend=False,
                height=500,
                xaxis_tickangle=-45,
            )
            fig.update_coloraxes(showscale=False)
            st.plotly_chart(fig, use_container_width=True)

            # Table view
            with st.expander("Show data table"):
                display = comparison[["metro", "home_price"]].copy()
                display["home_price"] = display["home_price"].apply(lambda x: f"${x:,.0f}")
                display.columns = ["Metro Area", "Median Home Value"]
                st.dataframe(display, use_container_width=True, hide_index=True)


elif view == "Explore ZIPs":
    st.title("Explore by ZIP Code")
    st.caption("Drill into ZIP-level data within a county")

    counties = get_all_counties()

    # Default to Santa Clara County
    default_counties = [c for c in counties if "Santa Clara" in c]
    default_idx = counties.index(default_counties[0]) if default_counties else 0

    selected_county = st.selectbox("Select a county", counties, index=default_idx)

    if selected_county:
        zip_data = get_zip_comparison(selected_county)

        if not zip_data.empty:
            st.subheader(f"{selected_county}: {len(zip_data)} ZIP codes")

            # Bar chart of ZIP prices
            fig = px.bar(
                zip_data.head(30),  # Top 30 for readability
                x="zip_code",
                y="home_price",
                title=f"Home Values by ZIP Code — {selected_county}",
                labels={"zip_code": "ZIP Code", "home_price": "Home Value ($)"},
                hover_data=["city"],
                color="home_price",
                color_continuous_scale="RdYlBu_r",
            )
            fig.update_layout(
                yaxis_tickformat="$,.0f",
                height=500,
                xaxis_tickangle=-45,
                xaxis_type="category",
            )
            fig.update_coloraxes(showscale=False)
            st.plotly_chart(fig, use_container_width=True)

            # Price trend for selected ZIPs
            st.markdown("---")
            st.subheader("ZIP Code Trends")

            zip_options = zip_data["zip_code"].tolist()
            selected_zips = st.multiselect(
                "Select ZIP codes to compare trends",
                zip_options,
                default=zip_options[:3],
                max_selections=6,
            )

            if selected_zips:
                trend_data = get_price_trends(selected_zips)
                if not trend_data.empty:
                    fig = px.line(
                        trend_data,
                        x="metric_date",
                        y="value",
                        color="name",
                        title="Home Value Trends by ZIP",
                        labels={"metric_date": "", "value": "Home Value ($)", "name": ""},
                    )
                    fig.update_layout(
                        hovermode="x unified",
                        yaxis_tickformat="$,.0f",
                        height=450,
                        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
                    )
                    st.plotly_chart(fig, use_container_width=True)

            # Full data table
            with st.expander("Show all ZIP codes"):
                display = zip_data.copy()
                display["home_price"] = display["home_price"].apply(lambda x: f"${x:,.0f}")
                display.columns = ["ZIP Code", "City", "Home Value"]
                st.dataframe(display, use_container_width=True, hide_index=True)
        else:
            st.warning(f"No ZIP-level data found for {selected_county}.")


elif view == "Ask Claude":
    st.title("Ask Claude")
    st.caption("Natural-language questions answered with SQL against the housing database")

    if "messages" not in st.session_state:
        st.session_state.messages = []

    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    if prompt := st.chat_input("Ask a question about the housing market..."):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)
        with st.chat_message("assistant"):
            response = "_(Claude integration coming soon — this will convert your question to SQL and query the database.)_"
            st.markdown(response)
            st.session_state.messages.append({"role": "assistant", "content": response})
