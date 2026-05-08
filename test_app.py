import streamlit as st
import pandas as pd
import warnings
from datetime import datetime, timedelta
from sqlalchemy import text
from src.database_setup import get_db_connection

# --- CONFIG ---
warnings.filterwarnings("ignore", category=UserWarning, module='pandas')
st.set_page_config(page_title="Anita's Logistics Grid", layout="wide", initial_sidebar_state="collapsed")


@st.cache_resource
def get_cached_engine():
    """Returns the persistent SQLAlchemy engine/pool."""
    return get_db_connection()


def run_query(query, params=None):
    """Executes a query using the pooled engine via SQLAlchemy."""
    engine = get_cached_engine()
    with engine.connect() as conn:
        # Note: We wrap the query string in text() and pass params as a dict
        return pd.read_sql(text(query), conn, params=params)


# --- DATA PREP ---
def get_grid_data():
    start_date = datetime.now().date() + timedelta(days=1)
    end_date = start_date + timedelta(days=14)
    all_dates = [start_date + timedelta(days=i) for i in range(14)]

    query = """
        SELECT 
            l.location_name                                 AS "Location", 
            l.store_guid                                    AS "location_id",
            (h.estimated_fulfillment_date AT TIME ZONE 'America/New_York')::date AS "Date",
            CASE 
                WHEN extract(hour FROM (h.estimated_fulfillment_date AT TIME ZONE 'America/New_York')) < 13 THEN 'AM'
                ELSE 'PM'
            END AS "DayPart",
            count(DISTINCT h.order_guid) AS "OrderCount",
            sum(sum(c.total_amount)) OVER(
                PARTITION BY l.location_name, (h.estimated_fulfillment_date AT TIME ZONE 'America/New_York')::date
            ) AS "DailyTotalRevenue"
        FROM orders_head h
        LEFT JOIN locations l ON h.location_id::uuid = l.store_guid
        JOIN order_checks c ON h.order_guid = c.order_guid 
        WHERE (h.estimated_fulfillment_date AT TIME ZONE 'America/New_York')::date BETWEEN :start AND :end
        AND h.deleted = FALSE
        GROUP BY 1, 2, 3, 4
    """
    df = run_query(query, params={"start": start_date, "end": end_date})

    if not df.empty:
        rev_map = df.groupby(['Location', 'Date'])['DailyTotalRevenue'].first().to_dict()

        def format_horizontal_slots(group):
            am_count = " 0"
            pm_count = " 0"
            for _, row in group.iterrows():
                if row['DayPart'] == 'AM':
                    am_count = f"{row['OrderCount']:3}"
                else:
                    pm_count = f"{row['OrderCount']:3}"
            return f"AM:{am_count} | PM:{pm_count} "

        grid = df.groupby(['Location', 'Date']).apply(format_horizontal_slots,include_groups=False).unstack(level=1)
        grid = grid.reindex(columns=all_dates).fillna("-")

        for col in grid.columns:
            for idx in grid.index:
                val = grid.at[idx, col]
                if val != "-":
                    rev = rev_map.get((idx, col), 0)
                    grid.at[idx, col] = f"{idx.title()}\n{val}\n${rev:,.2f}"

        loc_map = dict(zip(df['Location'], df['location_id']))
        return grid, loc_map, rev_map
    return pd.DataFrame(columns=all_dates), {}, {}


# --- UI & CSS (Preserved Exactly) ---
st.markdown("""
    <style>
    /* 1. GRID SCALE & HORIZONTAL ALIGNMENT */
    [data-testid="stHorizontalBlock"] {
        gap: 0px !important;
        display: flex !important;
        flex-wrap: nowrap !important;
        overflow-x: auto !important;
    }

    [data-testid="stColumn"] {
        padding: 0px !important;
        margin: 0px !important;
        flex: 1 1 auto !important; 
        min-width: 110px !important; 
    }

    /* 2. THE FUSION FIX: Kill the gap between header and buttons */
    [data-testid="stColumn"] [data-testid="stVerticalBlock"] {
        gap: 0px !important; 
    }

    [data-testid="stColumn"] [data-testid="stMarkdownContainer"] {
        margin-bottom: 0px !important;
        padding-bottom: 0px !important;
    }

    [data-testid="stColumn"] .element-container {
        margin-top: 0px !important;
        padding-top: 0px !important;
        margin-bottom: 0px !important;
    }

    [data-testid="stColumn"] [data-testid="stElementContainer"] {
        width: 100% !important;
        margin: 0px !important;
        padding: 0px !important;
    }

    /* 3. DATE HEADERS */
    .date-header {
        font-size: 14px !important;
        text-transform: uppercase;
        font-weight: bold;
        text-align: center;
        background: #f1f1f1;
        border: 0.5px solid #d0d0d0;
        margin: 0px !important;
        padding: 5px 0px !important;
        width: 100%;
        box-sizing: border-box !important;
        display: block !important;
    }

    /* 4. BUTTON CORE DESIGN */
    div.stButton, .stButton > button {
        width: 100% !important;
    }

    .stButton button {
        width: 100% !important;
        aspect-ratio: 2.2 / 1 !important; 
        height: auto !important;
        margin: 0px !important; 
        border: 0.5px solid #d0d0d0 !important;
        border-top: none !important; 
        border-radius: 0px !important; 
        display: flex !important;
        align-items: center !important;
        justify-content: center !important;
        box-sizing: border-box !important;
        overflow: hidden !important;
        background-color: var(--btn-bg, #ffffff) !important;
    }

    /* 5. TYPOGRAPHY */
    .stButton button div p {
        font-family: 'Open Sans', serif !important;
        font-size: 12px !important;
        line-height: 1.1 !important;
        text-align: center !important;
        white-space: pre-line !important; 
        color: #111 !important;
        font-weight: 700 !important;
        margin: 0 !important;
    }

    .stButton button:disabled {
        background-color: #f9f9f9 !important;
        opacity: 0.5 !important;
    }

    .stButton button:hover {
        background-color: #d3db3b !important;
        cursor: pointer !important;
    }

    div[class*="st-key-"][class*="_gold"] button {
        background-color: #FFF200 !important;
    }

    div[class*="st-key-"][class*="_gold"] button p {
        color: Black !important;
    }

    .total-header {
        font-size: 12px !important;
        text-transform: uppercase;
        font-weight: 800;
        text-align: center;
        background: #333;
        color: white;
        border: 0.5px solid #333;
        margin-top: 10px !important;
        padding: 3px 0px !important;
        width: 100%;
        display: block !important;
    }

    div[class*="st-key-total_"] button {
        background-color: #f8f9fa !important;
        border-top: 1px solid #d0d0d0 !important;
    }
    </style>
""", unsafe_allow_html=True)

st.title("14-Day Future Orders Forecast")

grid_df, loc_map, rev_map = get_grid_data()

if not grid_df.empty:
    cols = st.columns(14)
    for i, date_col in enumerate(grid_df.columns):
        with cols[i]:
            st.markdown(f"<div class='date-header'>{date_col.strftime('%a %m/%d')}</div>", unsafe_allow_html=True)

            for location in grid_df.index:
                cell_content = grid_df.at[location, date_col]

                if cell_content != "-":
                    rev = rev_map.get((location, date_col), 0)
                    suffix = "_gold" if rev >= 1000 else ""
                    button_key = f"btn_{location}_{date_col}{suffix}"

                    # Force the hover text here
                    hover_text = f"{location.title()}\n{cell_content}"

                    if st.button(cell_content, key=button_key, help=hover_text):
                        st.session_state.selected_loc = location
                        st.session_state.selected_date = date_col

                else:
                    # Added for the grey/disabled buttons too
                    st.button(f"{location.title()}\nAM: 0 | PM: 0\n$0.00",
                              key=f"empty_{location}_{date_col}",
                              disabled=True,
                              help=f"{location.title()}: No scheduled orders.")

# --- TOTAL ROW SECTION ---
st.markdown("<div class='total-header'>Daily Summary</div>", unsafe_allow_html=True)

# 1. Sum up the daily totals for all stores
daily_grand_totals = {}
for date_col in grid_df.columns:
    day_sum = 0
    for location in grid_df.index:
        day_sum += rev_map.get((location, date_col), 0)
    daily_grand_totals[date_col] = day_sum

# 2. Create the columns for the footer
total_cols = st.columns(14)
for i, date_col in enumerate(grid_df.columns):
    with total_cols[i]:
        total_rev = daily_grand_totals.get(date_col, 0)

        # Determine if the daily company total is "High Volume" (e.g., $10k)
        suffix = "_gold" if total_rev >= 10000 else ""

        # This matches the 3-line format: NAME / SLOTS / TOTAL
        # We leave the middle line empty or use it for a summary label
        total_label = f"Total Revenue\n${total_rev:,.2f}"

        st.button(total_label, key=f"total_{date_col}{suffix}", disabled=True)
        
## --- DRILL-DOWN ---
if "selected_loc" in st.session_state and "selected_date" in st.session_state:
    sel_loc = st.session_state.selected_loc
    sel_date = st.session_state.selected_date
    db_loc_id = loc_map.get(sel_loc)

    st.write("---")
    st.subheader(f"🔍 {sel_loc.title()} - {sel_date.strftime('%m/%d')}")

    # --- 1. PREP SUMMARIES (Top Row) ---
    # Query for BB Items
    bb_summary_query = """
            SELECT oi.item_name, SUM(oi.quantity) as total_qty
            FROM orders_head h
            JOIN order_checks c ON h.order_guid = c.order_guid
            JOIN order_items oi ON c.check_guid = oi.check_guid
            WHERE h.location_id::uuid = :loc_id 
              AND (h.estimated_fulfillment_date AT TIME ZONE 'America/New_York')::date = :sel_date
              AND h.deleted = FALSE
              AND oi.item_name ILIKE '%%BB%%'
            GROUP BY oi.item_name ORDER BY total_qty DESC
        """

    # Query for Taco Bar Items
    taco_summary_query = """
            SELECT oi.item_name, SUM(oi.quantity) as total_qty
            FROM orders_head h
            JOIN order_checks c ON h.order_guid = c.order_guid
            JOIN order_items oi ON c.check_guid = oi.check_guid
            WHERE h.location_id::uuid = :loc_id 
              AND (h.estimated_fulfillment_date AT TIME ZONE 'America/New_York')::date = :sel_date
              AND h.deleted = FALSE
              AND oi.item_name ILIKE '%%Taco Bar%%'
            GROUP BY oi.item_name ORDER BY total_qty DESC
        """

    bb_df = run_query(bb_summary_query, params={"loc_id": db_loc_id, "sel_date": sel_date})
    taco_df = run_query(taco_summary_query, params={"loc_id": db_loc_id, "sel_date": sel_date})

    if not bb_df.empty or not taco_df.empty:
        st.markdown("### 🌯 Daily Prep Totals")


        # Helper to build the badge string with "No-Split" logic
        def build_badges(df, bg_color, border_color):
            return " ".join([
                f"<span style='display: inline-block; background:{bg_color}; padding:2px 10px; "
                f"margin: 2px; border-radius:5px; border:1px solid {border_color}; "
                f"white-space: nowrap; font-size: 13px;'>"
                f"<b>{row['item_name']}</b>: {int(row['total_qty'])}</span>"
                for _, row in df.iterrows()
            ])


        # Row 1: BB Items
        if not bb_df.empty:
            bb_badges = build_badges(bb_df, "#f0f2f6", "#dcdfe3")
            st.markdown(f"**BB Items:** {bb_badges}", unsafe_allow_html=True)

        # Row 2: Taco Bar Items
        if not taco_df.empty:
            taco_badges = build_badges(taco_df, "#fff4e6", "#ffd8a8")
            st.markdown(f"<div style='margin-top:8px;'><b>Taco Bar:</b> {taco_badges}</div>", unsafe_allow_html=True)

        st.write("---")
    # --- 2. DETAILED ORDER LIST ---
    detail_query = """
        WITH OrderTotals AS (
            SELECT 
                h.order_guid,
                SUM(c.total_amount) as true_order_total
            FROM orders_head h
            JOIN order_checks c ON h.order_guid = c.order_guid
            WHERE h.location_id::uuid = :loc_id 
              AND (h.estimated_fulfillment_date AT TIME ZONE 'America/New_York')::date = :sel_date
              AND h.deleted = FALSE
            GROUP BY h.order_guid
        )
        SELECT 
            h.order_guid,
            h.order_number,
            CONCAT_WS(' ', c.customer_first, c.customer_last) AS customer_name,
            (h.estimated_fulfillment_date AT TIME ZONE 'America/New_York') AS local_time,
            oi.item_name,
            oi.quantity,
            STRING_AGG(DISTINCT im.mod_name, ', ') AS mods,
            ot.true_order_total AS order_total
        FROM orders_head h
        JOIN order_checks c ON h.order_guid = c.order_guid
        JOIN order_items oi ON c.check_guid = oi.check_guid
        LEFT JOIN item_modifiers im ON oi.selection_guid = im.selection_guid
        JOIN OrderTotals ot ON h.order_guid = ot.order_guid
        WHERE h.location_id::uuid = :loc_id 
          AND (h.estimated_fulfillment_date AT TIME ZONE 'America/New_York')::date = :sel_date 
          AND h.deleted = FALSE
        GROUP BY 1, 2, 3, 4, 5, 6, 8
        ORDER BY local_time ASC
    """

    full_df = run_query(detail_query, params={"loc_id": db_loc_id, "sel_date": sel_date})

    if not full_df.empty:
        # Sort=False preserves the SQL 'ORDER BY local_time'
        for order_guid, order_group in full_df.groupby('order_guid', sort=False):
            order_num = order_group['order_number'].iloc[0]
            customer = order_group['customer_name'].iloc[0]
            customer = customer.strip() if customer else "NO NAME"

            time_str = order_group['local_time'].iloc[0].strftime('%I:%M %p')
            total = order_group['order_total'].iloc[0]

            is_high_value = total >= 2000
            alert_emoji = "⚠️ " if is_high_value else ""

            # Use item_name check for delivery tags
            is_delivery = order_group['item_name'].str.contains('delivery', case=False).any()
            tag = " - 🚚 DELIVERY" if is_delivery else ""

            header_label = f"({time_str}) ORDER {order_num} - {customer.upper()} - ${total:,.2f} {alert_emoji}{tag}"

            with st.expander(header_label):
                if is_high_value:
                    st.error(f"**High Value Order: ${total:,.2f}** - Verify production capacity.")

                for _, row in order_group.iterrows():
                    qty = int(row['quantity'])
                    item_name = str(row['item_name']).strip()
                    st.markdown(f"**{qty} - {item_name}**")

                    mods = row.get('mods')
                    if pd.notna(mods) and str(mods).strip() not in ["", "None", "nan"]:
                        st.caption(f"↳ {str(mods).strip()}")
