import streamlit as st
import pandas as pd
import warnings
from datetime import datetime, timedelta
from src.database_setup import get_db_connection

# --- CONFIG ---
warnings.filterwarnings("ignore", category=UserWarning, module='pandas')
st.set_page_config(page_title="Anita's Logistics Grid", layout="wide", initial_sidebar_state="collapsed")


@st.cache_resource
def get_cached_conn():
    return get_db_connection()


def run_query(query, params=()):
    try:
        conn = get_cached_conn()
        if conn.closed != 0:
            st.cache_resource.clear()
            conn = get_cached_conn()
        return pd.read_sql(query, conn, params=params)
    except Exception:
        st.cache_resource.clear()
        conn = get_cached_conn()
        return pd.read_sql(query, conn, params=params)


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
        WHERE (h.estimated_fulfillment_date AT TIME ZONE 'America/New_York')::date BETWEEN %s AND %s
        AND h.deleted = FALSE
        GROUP BY 1, 2, 3, 4
    """
    df = run_query(query, (start_date, end_date))

    if not df.empty:
        rev_map = df.groupby(['Location', 'Date'])['DailyTotalRevenue'].first().to_dict()

        def format_horizontal_slots(group):
            am_count = "  "
            pm_count = "  "
            for _, row in group.iterrows():
                if row['DayPart'] == 'AM':
                    am_count = f"{row['OrderCount']:2}"
                else:
                    pm_count = f"{row['OrderCount']:2}"
            return f"({am_count})am | ({pm_count})pm"

        grid = df.groupby(['Location', 'Date']).apply(format_horizontal_slots).unstack(level=1)
        grid = grid.reindex(columns=all_dates).fillna("-")

        for col in grid.columns:
            for idx in grid.index:
                val = grid.at[idx, col]
                if val != "-":
                    rev = rev_map.get((idx, col), 0)
                    grid.at[idx, col] = f"{idx.upper()}\n{val}\n${rev:,.2f}"

        loc_map = dict(zip(df['Location'], df['location_id']))
        return grid, loc_map, rev_map
    return pd.DataFrame(columns=all_dates), {}


# --- UI & CSS ---
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

    /* Target the Markdown container specifically to kill bottom padding */
    [data-testid="stColumn"] [data-testid="stMarkdownContainer"] {
        margin-bottom: 0px !important;
        padding-bottom: 0px !important;
    }

    /* Target the button container specifically to kill top padding */
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
        /* Force border-collapse behavior */
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
        /* Match header border and remove the top border to 'fuse' with header */
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
    .stButton button:hover {
        background-color: #d3db3b !important;
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

    /* Keep your hover effect - it will still override since it's lower in the code */
    .stButton button:hover {
        background-color: #d3db3b !important;
    }
    
    /* 1. Target the div that contains your gold key in its class */
    div[class*="st-key-"][class*="_gold"] button {
        background-color: #FFF200 !important;
    }

    /* 2. Fix the text color inside that specific button */
    div[class*="st-key-"][class*="_gold"] button p {
        color: Black !important;
    }

    /* 3. Ensure your hover still wins */
    div[class*="st-key-"][class*="_gold"] button:hover {
        background-color: #d3db3b !important;
    }
    </style>
""", unsafe_allow_html=True)

st.title("14-Day Future Orders Forecast")

grid_df, loc_map, rev_map = get_grid_data()

if not grid_df.empty:
    cols = st.columns(14)
    for i, date_col in enumerate(grid_df.columns):
        with cols[i]:
            # Date Header
            st.markdown(f"<div class='date-header'>{date_col.strftime('%a %m/%d')}</div>", unsafe_allow_html=True)

            for location in grid_df.index:
                cell_content = grid_df.at[location, date_col]

                if cell_content != "-":
                    rev = rev_map.get((location, date_col), 0)
                    # We append a suffix to the key ONLY if it is high value
                    suffix = "_gold" if rev >= 1000 else ""
                    button_key = f"btn_{location}_{date_col}{suffix}"

                    if st.button(cell_content, key=button_key):
                        st.session_state.selected_loc = location
                        st.session_state.selected_date = date_col

                else:
                    # Uniform Placeholder - Force Uppercase to match content
                    st.button(f"{location.upper()}\n(  )am | (  )pm\n$0.00",
                              key=f"empty_{location}_{date_col}", disabled=True)

## --- DRILL-DOWN ---
if "selected_loc" in st.session_state and "selected_date" in st.session_state:
    sel_loc = st.session_state.selected_loc
    sel_date = st.session_state.selected_date
    db_loc_id = loc_map.get(sel_loc)

    st.write("---")
    st.subheader(f"🔍 {sel_loc.upper()} - {sel_date.strftime('%m/%d')}")

    detail_query = """
        WITH OrderTotals AS (
            SELECT 
                h.order_guid,
                SUM(c.total_amount) as true_order_total
            FROM orders_head h
            JOIN order_checks c ON h.order_guid = c.order_guid
            WHERE h.location_id::uuid = %s 
              AND (h.estimated_fulfillment_date AT TIME ZONE 'America/New_York')::date = %s
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
        WHERE h.location_id::uuid = %s 
          AND (h.estimated_fulfillment_date AT TIME ZONE 'America/New_York')::date = %s 
          AND h.deleted = FALSE
        GROUP BY 
            h.order_guid,
            h.order_number, 
            c.customer_first, 
            c.customer_last, 
            h.estimated_fulfillment_date, 
            oi.item_name, 
            oi.quantity,
            ot.true_order_total
        ORDER BY local_time ASC
    """
    full_df = run_query(detail_query, (db_loc_id, sel_date, db_loc_id, sel_date))

    if not full_df.empty:
        # Grouping by the unique GUID instead of the non-unique Number
        for order_guid, order_group in full_df.groupby('order_guid', sort=False):
            # We still pull the order_number for the label
            order_num = order_group['order_number'].iloc[0]
            customer = order_group['customer_name'].iloc[0]
            if not customer or customer.strip() == "":
                customer = "NO NAME"

            time_str = order_group['local_time'].iloc[0].strftime('%I:%M %p')
            total = order_group['order_total'].iloc[0]

            is_high_value = total >= 2000
            alert_emoji = "⚠️ " if is_high_value else ""

            is_delivery = order_group['item_name'].str.contains('delivery', case=False).any()
            tag = " - 🚚 DELIVERY" if is_delivery else ""

            header_label = f"({time_str}) ORDER {order_num} - {customer.upper()} - ${total:,.2f} {alert_emoji}{tag}"

            with st.expander(header_label):
                if is_high_value:
                    st.error(f"**High Value Order: ${total:,.2f}** - Verify production capacity.")

                for _, row in order_group.iterrows():
                    st.markdown(f"**{int(row['quantity'])} - {row['item_name']}**")

                    # Check if mods exists and is not 'nan' (string) or None
                    mods = row.get('mods')
                    if pd.notna(mods) and str(mods).lower() != 'nan' and str(mods).strip() != "":
                        st.caption(f"↳ {mods}")
                    
