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
    ["Overview", "Trends", "Affordability", "Compare Metros", "Explore ZIPs",
     "Purchasing Power", "Forecast", "Rent vs Buy", "Ask Claude"],
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


elif view == "Purchasing Power":
    st.title("Purchasing Power")
    st.caption("Where does your money go the furthest? Compare real affordability by occupation across U.S. metros.")

    import sqlite3 as _sqlite3
    import pydeck as pdk
    from pathlib import Path as _Path

    _db = _Path(__file__).resolve().parent.parent.parent / "data" / "processed" / "housing.db"

    @st.cache_data(ttl=600)
    def get_occupations():
        conn = _sqlite3.connect(_db)
        rows = conn.execute("SELECT DISTINCT occ_code, occ_title FROM metro_wages ORDER BY occ_title").fetchall()
        conn.close()
        return {r[1]: r[0] for r in rows}

    @st.cache_data(ttl=600)
    def get_ppi_map_data(occ_code):
        conn = _sqlite3.connect(_db)
        conn.row_factory = _sqlite3.Row
        rows = conn.execute("""
            SELECT g.geo_code as metro, g.latitude as lat, g.longitude as lon,
                   dm.value as ppi, h.value as home_price,
                   mw.median_wage as wage, mw.occ_title as occupation
            FROM derived_metrics dm
            JOIN geographies g ON g.geography_id = dm.geography_id
            JOIN metro_crosswalk mc ON mc.zillow_metro = g.geo_code
            JOIN metro_wages mw ON mw.area_code = mc.bls_area_code AND mw.occ_code = ?
            JOIN housing_metrics h ON h.geography_id = g.geography_id AND h.metric_type = 'zhvi'
            WHERE dm.metric_name = ? AND g.latitude IS NOT NULL
            AND h.metric_date = (
                SELECT MAX(h2.metric_date) FROM housing_metrics h2
                JOIN geographies g2 ON g2.geography_id = h2.geography_id
                WHERE g2.geo_type = 'metro' AND h2.metric_type = 'zhvi'
            )
        """, (occ_code, f"ppi_{occ_code}")).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    @st.cache_data(ttl=600)
    def get_remote_worker_data(occ_code, earn_metro, live_metros):
        conn = _sqlite3.connect(_db)
        conn.row_factory = _sqlite3.Row
        # Get the wage from the earning metro
        wage_row = conn.execute("""
            SELECT mw.median_wage
            FROM metro_wages mw
            JOIN metro_crosswalk mc ON mc.bls_area_code = mw.area_code
            WHERE mc.zillow_metro = ? AND mw.occ_code = ?
        """, (earn_metro, occ_code)).fetchone()

        if not wage_row:
            conn.close()
            return []

        remote_wage = wage_row["median_wage"]

        # Get housing costs for living metros
        results = []
        for metro in live_metros:
            row = conn.execute("""
                SELECT g.geo_code as metro, h.value as home_price
                FROM housing_metrics h
                JOIN geographies g ON g.geography_id = h.geography_id
                WHERE g.geo_code = ? AND g.geo_type = 'metro' AND h.metric_type = 'zhvi'
                ORDER BY h.metric_date DESC LIMIT 1
            """, (metro,)).fetchone()
            if row:
                home_price = row["home_price"]
                price_to_wage = home_price / remote_wage if remote_wage > 0 else 0
                results.append({
                    "metro": metro,
                    "remote_wage": remote_wage,
                    "home_price": home_price,
                    "price_to_wage": price_to_wage,
                })
        conn.close()
        return results

    occupations = get_occupations()
    occ_names = list(occupations.keys())

    # Default to Software Developers
    default_idx = next((i for i, n in enumerate(occ_names) if "Software" in n), 0)
    selected_occ = st.selectbox("Select your occupation", occ_names, index=default_idx)
    occ_code = occupations[selected_occ]

    # Remote worker toggle
    remote_mode = st.toggle("I work remotely", value=False)

    if remote_mode:
        st.subheader("Remote worker comparison")
        st.caption("See how far your salary goes in different cities")

        all_metros = get_all_metros()
        default_earn = [m for m in all_metros if "San Jose" in m]
        earn_metro = st.selectbox(
            "I earn wages from:",
            all_metros,
            index=all_metros.index(default_earn[0]) if default_earn else 0,
        )

        default_live = [
            "Austin, TX", "Denver, CO", "Raleigh, NC",
            "Nashville, TN", "Pittsburgh, PA",
        ]
        live_metros = st.multiselect(
            "Compare living in:",
            all_metros,
            default=[m for m in default_live if m in all_metros],
            max_selections=10,
        )

        if live_metros:
            remote_data = get_remote_worker_data(occ_code, earn_metro, live_metros)
            if remote_data:
                import pandas as _pd
                df = _pd.DataFrame(remote_data)
                df = df.sort_values("price_to_wage")

                fig = px.bar(
                    df,
                    x="metro",
                    y="price_to_wage",
                    title=f"Home price as multiple of {earn_metro} {selected_occ} wage",
                    labels={"metro": "", "price_to_wage": "Price-to-wage ratio"},
                    color="price_to_wage",
                    color_continuous_scale="RdYlGn_r",
                )
                fig.update_layout(
                    height=450,
                    xaxis_tickangle=-45,
                    yaxis_title="Home price / annual wage",
                )
                fig.update_coloraxes(showscale=False)
                st.plotly_chart(fig, use_container_width=True)

                with st.expander("View data"):
                    display = df.copy()
                    display["remote_wage"] = display["remote_wage"].apply(lambda x: f"${x:,.0f}")
                    display["home_price"] = display["home_price"].apply(lambda x: f"${x:,.0f}")
                    display["price_to_wage"] = display["price_to_wage"].apply(lambda x: f"{x:.1f}x")
                    display.columns = ["Metro", "Remote Wage", "Home Price", "Price-to-Wage"]
                    st.dataframe(display, use_container_width=True, hide_index=True)
            else:
                st.warning(f"No wage data found for {selected_occ} in {earn_metro}")

    else:
        # Standard purchasing power map view
        map_data = get_ppi_map_data(occ_code)

        if map_data:
            import pandas as _pd
            df = _pd.DataFrame(map_data)

            # KPI cards
            col1, col2, col3, col4 = st.columns(4)
            best = df.loc[df["ppi"].idxmax()]
            worst = df.loc[df["ppi"].idxmin()]
            col1.metric("Best metro", best["metro"].split(",")[0], f"PPI {best['ppi']:.0f}")
            col2.metric("Worst metro", worst["metro"].split(",")[0], f"PPI {worst['ppi']:.0f}")
            col3.metric("Metros analyzed", len(df))
            col4.metric("National baseline", "100")

            # Color mapping for pydeck
            def ppi_to_color(ppi):
                if ppi < 60:
                    return [226, 75, 74, 200]       # red
                elif ppi < 100:
                    return [239, 159, 39, 200]      # amber
                elif ppi < 150:
                    return [151, 196, 89, 200]      # green
                else:
                    return [29, 158, 117, 200]      # teal

            df["color"] = df["ppi"].apply(ppi_to_color)
            df["radius"] = df["ppi"].apply(lambda p: max(5000, min(50000, p * 100)))
            df["elevation"] = df["home_price"].apply(lambda p: p / 10)

            # Pydeck 3D map
            layer = pdk.Layer(
                "ColumnLayer",
                data=df,
                get_position=["lon", "lat"],
                get_elevation="elevation",
                elevation_scale=1,
                radius=8000,
                get_fill_color="color",
                pickable=True,
                auto_highlight=True,
            )

            view_state = pdk.ViewState(
                latitude=39.5,
                longitude=-98.0,
                zoom=3.2,
                pitch=45,
                bearing=0,
            )

            tooltip = {
                "html": "<b>{metro}</b><br>"
                        "PPI: {ppi}<br>"
                        "Wage: ${wage}<br>"
                        "Home: ${home_price}",
                "style": {
                    "backgroundColor": "#1a1a2e",
                    "color": "white",
                    "fontSize": "12px",
                    "padding": "8px",
                },
            }

            st.pydeck_chart(pdk.Deck(
                layers=[layer],
                initial_view_state=view_state,
                tooltip=tooltip,
                map_style="mapbox://styles/mapbox/dark-v10",
            ))

            # Legend
            leg1, leg2, leg3, leg4, leg5 = st.columns(5)
            leg1.markdown("**Legend:**")
            leg2.markdown(":red[Unaffordable (PPI < 60)]")
            leg3.markdown(":orange[Stretched (60-100)]")
            leg4.markdown(":green[Comfortable (100-150)]")
            leg5.markdown(":green[Excellent (150+)]")

            st.markdown("---")

            # Scatter plot: wage vs home price
            st.subheader("Wage vs. home price")
            fig = px.scatter(
                df,
                x="wage",
                y="home_price",
                color="ppi",
                color_continuous_scale="RdYlGn",
                size="ppi",
                hover_name="metro",
                title=f"{selected_occ}: wage vs. home price by metro",
                labels={
                    "wage": "Median annual wage ($)",
                    "home_price": "Median home price ($)",
                    "ppi": "Purchasing power index",
                },
            )
            fig.update_layout(
                height=500,
                xaxis_tickformat="$,.0f",
                yaxis_tickformat="$,.0f",
            )
            # Add quadrant lines at national medians
            median_wage = df["wage"].median()
            median_price = df["home_price"].median()
            fig.add_hline(y=median_price, line_dash="dash", line_color="gray", opacity=0.5)
            fig.add_vline(x=median_wage, line_dash="dash", line_color="gray", opacity=0.5)
            fig.add_annotation(x=df["wage"].max(), y=df["home_price"].min(),
                             text="High pay, low cost", showarrow=False,
                             font=dict(size=11, color="green"), xanchor="right")
            fig.add_annotation(x=df["wage"].max(), y=df["home_price"].max(),
                             text="High pay, high cost", showarrow=False,
                             font=dict(size=11, color="orange"), xanchor="right")
            fig.add_annotation(x=df["wage"].min(), y=df["home_price"].max(),
                             text="Low pay, high cost", showarrow=False,
                             font=dict(size=11, color="red"))
            st.plotly_chart(fig, use_container_width=True)

            # Top and bottom tables
            st.markdown("---")
            tcol1, tcol2 = st.columns(2)
            with tcol1:
                st.subheader("Top 10: best purchasing power")
                top = df.nlargest(10, "ppi")[["metro", "wage", "home_price", "ppi"]].copy()
                top["wage"] = top["wage"].apply(lambda x: f"${x:,.0f}")
                top["home_price"] = top["home_price"].apply(lambda x: f"${x:,.0f}")
                top["ppi"] = top["ppi"].apply(lambda x: f"{x:.0f}")
                top.columns = ["Metro", "Wage", "Home Price", "PPI"]
                st.dataframe(top, use_container_width=True, hide_index=True)

            with tcol2:
                st.subheader("Bottom 10: worst purchasing power")
                bottom = df.nsmallest(10, "ppi")[["metro", "wage", "home_price", "ppi"]].copy()
                bottom["wage"] = bottom["wage"].apply(lambda x: f"${x:,.0f}")
                bottom["home_price"] = bottom["home_price"].apply(lambda x: f"${x:,.0f}")
                bottom["ppi"] = bottom["ppi"].apply(lambda x: f"{x:.0f}")
                bottom.columns = ["Metro", "Wage", "Home Price", "PPI"]
                st.dataframe(bottom, use_container_width=True, hide_index=True)
        else:
            st.warning(f"No purchasing power data available for {selected_occ}. Run the derived metrics pipeline.")


elif view == "Forecast":
    st.title("Price Forecast")
    st.caption("6-month home price predictions using Facebook Prophet")

    from src.forecasting.predict import forecast_prices

    forecast_type = st.radio("Geography level", ["Metro", "ZIP Code"], horizontal=True)

    if forecast_type == "Metro":
        all_metros = get_all_metros()
        default_metros = [m for m in all_metros if "San Jose" in m]
        default_idx = all_metros.index(default_metros[0]) if default_metros else 0
        selected = st.selectbox("Select a metro area", all_metros, index=default_idx)
        geo_type = "metro"
    else:
        selected = st.text_input("Enter a ZIP code", value="95051")
        geo_type = "zip"

    months = st.slider("Forecast horizon (months)", 3, 12, 6)
    metric = st.radio("Metric", ["Home value (ZHVI)", "Rent (ZORI)"], horizontal=True)
    metric_type = "zhvi" if "Home" in metric else "zori"

    if st.button("Generate forecast", type="primary"):
        with st.spinner("Training model..."):
            result = forecast_prices(selected, metric_type=metric_type, months=months, geo_type=geo_type)

        if result["metadata"].get("error"):
            st.error(result["metadata"]["error"])
        elif not result["forecast"].empty:
            meta = result["metadata"]

            # KPI cards
            col1, col2, col3 = st.columns(3)
            col1.metric(
                "Current value",
                f"${meta['last_actual_value']:,.0f}",
            )
            col2.metric(
                f"{months}-month forecast",
                f"${meta['forecast_end_value']:,.0f}",
                f"{meta['forecast_change_pct']:+.1f}%",
            )
            col3.metric("Data points used", f"{meta['data_points']} months")

            # Build combined chart
            hist = result["historical"].copy()
            fitted = result["fitted"].copy()
            fc = result["forecast"].copy()

            fig = go.Figure()

            # Historical actual values
            fig.add_trace(go.Scatter(
                x=hist["date"], y=hist["actual"],
                mode="lines", name="Actual",
                line=dict(color="#2196F3", width=2),
            ))

            # Forecast line
            # Connect forecast to last actual point
            bridge_date = hist["date"].iloc[-1]
            bridge_val = hist["actual"].iloc[-1]
            fc_with_bridge = pd.concat([
                pd.DataFrame({"date": [bridge_date], "predicted": [bridge_val],
                              "lower": [bridge_val], "upper": [bridge_val]}),
                fc
            ])

            fig.add_trace(go.Scatter(
                x=fc_with_bridge["date"], y=fc_with_bridge["predicted"],
                mode="lines", name="Forecast",
                line=dict(color="#FF9800", width=2, dash="dash"),
            ))

            # Confidence interval
            fig.add_trace(go.Scatter(
                x=pd.concat([fc_with_bridge["date"], fc_with_bridge["date"][::-1]]),
                y=pd.concat([fc_with_bridge["upper"], fc_with_bridge["lower"][::-1]]),
                fill="toself",
                fillcolor="rgba(255,152,0,0.15)",
                line=dict(color="rgba(255,152,0,0)"),
                name="Confidence interval",
                showlegend=True,
            ))

            # Vertical line at forecast start
            fig.add_vline(
                x=bridge_date, line_dash="dot",
                line_color="gray", opacity=0.5,
                annotation_text="Forecast start",
            )

            metric_label = "Home Value" if metric_type == "zhvi" else "Rent"
            fig.update_layout(
                title=f"{metric_label} Forecast: {selected}",
                xaxis_title="",
                yaxis_title=f"{metric_label} ($)",
                yaxis_tickformat="$,.0f",
                hovermode="x unified",
                height=500,
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            )

            # Only show last 5 years + forecast for readability
            import datetime
            five_years_ago = bridge_date - pd.DateOffset(years=5)
            fig.update_xaxes(range=[five_years_ago, fc["date"].max()])

            st.plotly_chart(fig, use_container_width=True)

            st.caption(
                "Forecast generated using Facebook Prophet with multiplicative seasonality. "
                "The shaded area shows the 80% confidence interval. "
                "This is a statistical projection based on historical trends and should not be used as investment advice."
            )


elif view == "Rent vs Buy":
    st.title("Rent vs Buy Calculator")
    st.caption("Should you rent or buy? Compare the financial outcomes based on local data.")

    import sqlite3 as _sqlite3
    from pathlib import Path as _Path

    _db = _Path(__file__).resolve().parent.parent.parent / "data" / "processed" / "housing.db"

    @st.cache_data(ttl=600)
    def get_local_data(metro_name):
        conn = _sqlite3.connect(_db)
        conn.row_factory = _sqlite3.Row

        # Latest home price
        price = conn.execute("""
            SELECT h.value FROM housing_metrics h
            JOIN geographies g ON g.geography_id = h.geography_id
            WHERE g.geo_code = ? AND g.geo_type = 'metro' AND h.metric_type = 'zhvi'
            ORDER BY h.metric_date DESC LIMIT 1
        """, (metro_name,)).fetchone()

        # Latest rent
        rent = conn.execute("""
            SELECT h.value FROM housing_metrics h
            JOIN geographies g ON g.geography_id = h.geography_id
            WHERE g.geo_code = ? AND g.geo_type = 'metro' AND h.metric_type = 'zori'
            ORDER BY h.metric_date DESC LIMIT 1
        """, (metro_name,)).fetchone()

        # Latest mortgage rate
        rate = conn.execute("""
            SELECT value FROM macro_indicators
            WHERE indicator = 'mortgage_30y'
            ORDER BY obs_date DESC LIMIT 1
        """).fetchone()

        # Historical appreciation (5yr CAGR)
        prices_5y = conn.execute("""
            SELECT h.value, h.metric_date FROM housing_metrics h
            JOIN geographies g ON g.geography_id = h.geography_id
            WHERE g.geo_code = ? AND g.geo_type = 'metro' AND h.metric_type = 'zhvi'
            ORDER BY h.metric_date DESC LIMIT 61
        """, (metro_name,)).fetchall()

        conn.close()

        appreciation = None
        if len(prices_5y) >= 60:
            latest = prices_5y[0]["value"]
            five_yrs_ago = prices_5y[-1]["value"]
            if five_yrs_ago > 0:
                appreciation = ((latest / five_yrs_ago) ** (1/5) - 1) * 100

        return {
            "home_price": price["value"] if price else None,
            "monthly_rent": rent["value"] if rent else None,
            "mortgage_rate": rate["value"] if rate else 6.5,
            "appreciation_rate": appreciation if appreciation else 3.0,
        }

    all_metros = get_all_metros()
    default_metros = [m for m in all_metros if "San Jose" in m]
    default_idx = all_metros.index(default_metros[0]) if default_metros else 0

    selected_metro = st.selectbox("Select a metro area", all_metros, index=default_idx, key="rvb_metro")
    local = get_local_data(selected_metro)

    st.markdown("---")
    st.subheader("Adjust assumptions")

    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**Buying**")
        home_price = st.number_input("Home price ($)", value=int(local["home_price"] or 500000), step=25000, format="%d")
        down_payment_pct = st.slider("Down payment (%)", 0, 50, 20)
        mortgage_rate = st.number_input("Mortgage rate (%)", value=local["mortgage_rate"], step=0.125, format="%.3f")
        property_tax_rate = st.number_input("Property tax rate (%)", value=1.1, step=0.1, format="%.1f")
        home_insurance = st.number_input("Home insurance ($/mo)", value=200, step=25)
        maintenance_pct = st.number_input("Maintenance (% of home value/yr)", value=1.0, step=0.25, format="%.2f")
        appreciation = st.number_input("Expected appreciation (%/yr)", value=local["appreciation_rate"], step=0.5, format="%.1f")

    with col2:
        st.markdown("**Renting**")
        monthly_rent = st.number_input("Monthly rent ($)", value=int(local["monthly_rent"] or 2500), step=100, format="%d")
        rent_increase = st.number_input("Annual rent increase (%)", value=3.0, step=0.5, format="%.1f")
        renters_insurance = st.number_input("Renters insurance ($/mo)", value=30, step=5)

        st.markdown("**Investment**")
        investment_return = st.number_input("Investment return (%/yr)", value=7.0, step=0.5, format="%.1f",
                                           help="Return on money invested instead of buying")

    time_horizon = st.slider("Time horizon (years)", 1, 30, 7)

    # Compute buying costs
    down_payment = home_price * down_payment_pct / 100
    loan_amount = home_price - down_payment
    monthly_rate = (mortgage_rate / 100) / 12
    n_payments = 360

    if monthly_rate > 0:
        monthly_mortgage = loan_amount * (monthly_rate * (1 + monthly_rate)**n_payments) / ((1 + monthly_rate)**n_payments - 1)
    else:
        monthly_mortgage = loan_amount / n_payments

    monthly_property_tax = home_price * property_tax_rate / 100 / 12
    monthly_maintenance = home_price * maintenance_pct / 100 / 12

    # Year-by-year comparison
    buy_total = down_payment
    rent_total = 0.0
    investment_balance = down_payment  # renter invests the down payment
    current_rent = monthly_rent
    current_home_value = home_price
    remaining_loan = loan_amount

    yearly_data = []

    for year in range(1, time_horizon + 1):
        # Buying costs this year
        yearly_mortgage = monthly_mortgage * 12
        yearly_tax = monthly_property_tax * 12
        yearly_insurance_buy = home_insurance * 12
        yearly_maintenance_cost = current_home_value * maintenance_pct / 100
        buy_yearly_cost = yearly_mortgage + yearly_tax + yearly_insurance_buy + yearly_maintenance_cost
        buy_total += buy_yearly_cost

        # Home equity
        current_home_value *= (1 + appreciation / 100)

        # Rough principal paydown (simplified)
        interest_this_year = remaining_loan * mortgage_rate / 100
        principal_this_year = yearly_mortgage - interest_this_year
        remaining_loan = max(0, remaining_loan - principal_this_year)
        equity = current_home_value - remaining_loan

        # Renting costs this year
        yearly_rent = current_rent * 12
        yearly_insurance_rent = renters_insurance * 12
        rent_yearly_cost = yearly_rent + yearly_insurance_rent
        rent_total += rent_yearly_cost

        # Renter invests the difference
        monthly_savings = (buy_yearly_cost - rent_yearly_cost) / 12
        if monthly_savings > 0:
            investment_balance = investment_balance * (1 + investment_return / 100) + monthly_savings * 12
        else:
            investment_balance = investment_balance * (1 + investment_return / 100)

        current_rent *= (1 + rent_increase / 100)

        # Net worth comparison
        buy_net = equity
        rent_net = investment_balance

        yearly_data.append({
            "year": year,
            "buy_monthly_cost": buy_yearly_cost / 12,
            "rent_monthly_cost": rent_yearly_cost / 12,
            "home_equity": equity,
            "investment_balance": investment_balance,
            "buy_net_worth": buy_net,
            "rent_net_worth": rent_net,
            "buy_advantage": buy_net - rent_net,
        })

    import pandas as _pd
    results = _pd.DataFrame(yearly_data)

    # Summary
    st.markdown("---")
    final = results.iloc[-1]
    verdict = "Buy" if final["buy_advantage"] > 0 else "Rent"
    advantage = abs(final["buy_advantage"])

    if verdict == "Buy":
        st.success(f"**Buying is better by ${advantage:,.0f}** after {time_horizon} years in {selected_metro}")
    else:
        st.info(f"**Renting is better by ${advantage:,.0f}** after {time_horizon} years in {selected_metro}")

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Monthly mortgage payment", f"${monthly_mortgage:,.0f}")
    col2.metric("Monthly rent (current)", f"${monthly_rent:,.0f}")
    col3.metric(f"Home equity (yr {time_horizon})", f"${final['home_equity']:,.0f}")
    col4.metric(f"Investment balance (yr {time_horizon})", f"${final['investment_balance']:,.0f}")

    # Net worth comparison chart
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=results["year"], y=results["buy_net_worth"],
        mode="lines+markers", name="Buy (home equity)",
        line=dict(color="#2196F3", width=2),
    ))
    fig.add_trace(go.Scatter(
        x=results["year"], y=results["rent_net_worth"],
        mode="lines+markers", name="Rent (investments)",
        line=dict(color="#FF9800", width=2),
    ))
    fig.update_layout(
        title="Net worth comparison: buy vs rent",
        xaxis_title="Year",
        yaxis_title="Net worth ($)",
        yaxis_tickformat="$,.0f",
        hovermode="x unified",
        height=450,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )
    st.plotly_chart(fig, use_container_width=True)

    # Monthly cost comparison
    fig2 = go.Figure()
    fig2.add_trace(go.Scatter(
        x=results["year"], y=results["buy_monthly_cost"],
        mode="lines+markers", name="Buy (total monthly cost)",
        line=dict(color="#2196F3", width=2),
    ))
    fig2.add_trace(go.Scatter(
        x=results["year"], y=results["rent_monthly_cost"],
        mode="lines+markers", name="Rent (total monthly cost)",
        line=dict(color="#FF9800", width=2),
    ))
    fig2.update_layout(
        title="Monthly cost comparison over time",
        xaxis_title="Year",
        yaxis_title="Monthly cost ($)",
        yaxis_tickformat="$,.0f",
        hovermode="x unified",
        height=400,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )
    st.plotly_chart(fig2, use_container_width=True)

    st.caption(
        "This calculator uses simplified assumptions. Actual costs vary based on tax deductions, "
        "HOA fees, closing costs, opportunity costs, and market conditions. "
        "Not financial advice."
    )


elif view == "Ask Claude":
    st.title("Ask Claude")
    st.caption("Ask questions in plain English — Claude writes SQL, queries the database, and explains the results")

    from src.llm.text_to_sql import ask as ask_claude

    # Example questions
    with st.expander("Example questions to try"):
        examples = [
            "What are the most expensive ZIP codes in Santa Clara County?",
            "How have home prices in San Jose changed since 2020?",
            "Compare median home values in San Jose, Austin, and Denver metros",
            "What's the current national median home price and how does it compare to last year?",
            "Which metros have the highest rent-to-home-value ratio?",
            "Show me the 10 cheapest metros in California",
            "How did mortgage rates change during 2022-2023?",
            "What ZIP codes in the Bay Area are under $1 million?",
        ]
        for ex in examples:
            if st.button(ex, key=f"ex_{ex[:30]}"):
                st.session_state["prefill_question"] = ex

    # Chat history
    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []

    # Display previous messages
    for msg in st.session_state.chat_history:
        with st.chat_message(msg["role"]):
            if msg["role"] == "assistant" and "sql" in msg:
                # Show the SQL in a collapsible block
                st.markdown(msg["content"])
                with st.expander("View SQL query"):
                    st.code(msg["sql"], language="sql")
                if msg.get("data"):
                    with st.expander(f"View data ({msg['row_count']} rows)"):
                        st.dataframe(msg["data"], use_container_width=True, hide_index=True)
            else:
                st.markdown(msg["content"])

    # Handle prefilled question from example buttons
    prefill = st.session_state.pop("prefill_question", None)

    # Chat input
    prompt = st.chat_input("Ask a question about the housing market...")
    question = prefill or prompt

    if question:
        # Show user message
        st.session_state.chat_history.append({"role": "user", "content": question})
        with st.chat_message("user"):
            st.markdown(question)

        # Query Claude
        with st.chat_message("assistant"):
            with st.spinner("Thinking..."):
                result = ask_claude(question)

            if result.error:
                st.error(result.error)
                if result.sql:
                    st.code(result.sql, language="sql")
                st.session_state.chat_history.append({
                    "role": "assistant",
                    "content": f"Error: {result.error}",
                })
            elif result.sql is None:
                # Claude couldn't generate SQL
                st.markdown(result.explanation)
                st.session_state.chat_history.append({
                    "role": "assistant",
                    "content": result.explanation,
                })
            else:
                # Success — show summary, SQL, and data
                st.markdown(result.summary)

                with st.expander("View SQL query"):
                    st.code(result.sql, language="sql")

                if result.rows:
                    import pandas as pd
                    df = pd.DataFrame(result.rows)
                    with st.expander(f"View data ({len(result.rows)} rows)"):
                        st.dataframe(df, use_container_width=True, hide_index=True)

                    # Auto-chart if the results have a date column and a value column
                    date_cols = [c for c in df.columns if "date" in c.lower()]
                    value_cols = [c for c in df.columns if df[c].dtype in ("float64", "int64") and c not in ("geography_id",)]
                    if date_cols and value_cols:
                        name_cols = [c for c in df.columns if c in ("name", "metro", "city", "zip_code", "geo_code")]
                        color_col = name_cols[0] if name_cols else None
                        fig = px.line(
                            df,
                            x=date_cols[0],
                            y=value_cols[0],
                            color=color_col,
                            title="Query Results",
                            labels={date_cols[0]: "", value_cols[0]: value_cols[0].replace("_", " ").title()},
                        )
                        fig.update_layout(hovermode="x unified", height=400)
                        if any(df[value_cols[0]] > 10000):
                            fig.update_layout(yaxis_tickformat="$,.0f")
                        st.plotly_chart(fig, use_container_width=True)

                st.session_state.chat_history.append({
                    "role": "assistant",
                    "content": result.summary,
                    "sql": result.sql,
                    "data": result.rows[:50] if result.rows else None,
                    "row_count": len(result.rows) if result.rows else 0,
                })

        st.rerun()
