import streamlit as st
import pandas as pd
import warnings
from datetime import datetime, timedelta
from src.database_setup import get_db_connection
from zoneinfo import ZoneInfo

# Suppress the Pandas/SQLAlchemy warning
warnings.filterwarnings("ignore", category=UserWarning, module='pandas')

# --- SETTINGS ---
st.set_page_config(page_title="Anita's Logistics Grid", layout="wide")


@st.cache_resource
def get_cached_conn():
    """Maintains a persistent 'pipe' to Azure."""
    return get_db_connection()


def run_query(query, params=()):
    """Executes SQL with an automatic reconnection safety net."""
    try:
        conn = get_cached_conn()
        # Check if connection is alive (0 is open, non-zero is closed/broken)
        if conn.closed != 0:
            st.cache_resource.clear()
            conn = get_cached_conn()
        return pd.read_sql(query, conn, params=params)
    except Exception as e:
        # If any database error occurs, reset the cache and try one last time
        st.cache_resource.clear()
        conn = get_cached_conn()
        return pd.read_sql(query, conn, params=params)


# --- 1. DATA PREP ---
def get_grid_data():
    start_date = datetime.now().date() + timedelta(days=1)
    end_date = start_date + timedelta(days=10)

    query = """
            SELECT 
                l.location_name                 AS "Location", 
                l.store_guid                    AS "location_id",
                (h.estimated_fulfillment_date AT TIME ZONE 'America/New_York')::date AS "Date",
                CASE 
                    WHEN extract(hour FROM (h.estimated_fulfillment_date AT TIME ZONE 'America/New_York')) < 13 THEN 'AM'
                    ELSE 'PM'
                END AS "DayPart",
                count(h.order_guid) AS "OrderCount"
            FROM orders_head h
            LEFT JOIN locations l ON h.location_id::uuid = l.store_guid
            WHERE (h.estimated_fulfillment_date AT TIME ZONE 'America/New_York')::date BETWEEN %s AND %s
            AND h.deleted = FALSE
            GROUP BY 1, 2, 3, 4
        """
    df = run_query(query, (start_date, end_date))

    if not df.empty:
        df['DisplayValue'] = df.apply(lambda x: f"({x['OrderCount']} : {x['DayPart'].lower()})", axis=1)
        grid = df.pivot_table(
            index='Location', columns='Date', values='DisplayValue',
            aggfunc=lambda x: ' \n '.join(x)
        ).fillna("-")
        loc_map = dict(zip(df['Location'], df['location_id']))
        return grid, loc_map
    return pd.DataFrame(), {}


# --- 2. THE UI ---
st.title("10-Day Orders Overview")

if st.sidebar.button('🔄 Refresh Grid'):
    st.cache_resource.clear()  # Force a fresh DB connection
    st.rerun()

grid_df, loc_map = get_grid_data()

if grid_df.empty:
    st.warning("No future orders found in Azure.")
else:
    st.write("### Order Volume by Store")
    event = st.dataframe(grid_df, width=2000, on_select="rerun", selection_mode="single-cell")

    # --- 3. THE DRILL-DOWN ---
    if event and event.selection.get("cells"):
        cell = event.selection["cells"][0]
        # Robust selection logic for different Streamlit versions
        raw_row = cell[0] if isinstance(cell, (list, tuple)) else cell.get('row')
        raw_col = cell[1] if isinstance(cell, (list, tuple)) else cell.get('column')

        try:
            selected_loc = grid_df.index[raw_row] if isinstance(raw_row, int) else raw_row
            selected_date = grid_df.columns[raw_col] if isinstance(raw_col, int) else raw_col
        except:
            selected_loc, selected_date = None, None

        if selected_loc and selected_date:
            db_location_id = loc_map.get(selected_loc)
            st.write("---")
            st.subheader(f"🔍 Details for {selected_loc} on {selected_date}")

            flat_detail_query = """
                            SELECT 
                                h.order_number,
                                c.customer_first || ' ' || c.customer_last AS customer_name,
                                h.estimated_fulfillment_date AT TIME ZONE 'America/New_York' AS local_time,
                                oi.item_name,
                                oi.quantity,
                                im.mod_name
                            FROM orders_head h
                            JOIN order_checks c ON h.order_guid = c.order_guid
                            JOIN order_items oi ON c.check_guid = oi.check_guid
                            LEFT JOIN item_modifiers im ON oi.selection_guid = im.selection_guid
                            WHERE h.location_id::uuid = %s 
                              AND (h.estimated_fulfillment_date AT TIME ZONE 'America/New_York')::date = %s 
                              AND h.deleted = FALSE
                            -- SORT BY TIME FIRST, THEN ORDER NUMBER
                            ORDER BY local_time ASC, h.order_number ASC
                        """

            full_df = run_query(flat_detail_query, (db_location_id, selected_date))

            if full_df.empty:
                st.info("No records found.")
            else:
                for order_num, order_group in full_df.groupby('order_number', sort=False):
                    customer = order_group['customer_name'].iloc[0]
                    # Ensure we grab the actual timestamp for the label
                    time_val = order_group['local_time'].iloc[0]
                    time_str = time_val.strftime('%I:%M %p')

                    is_delivery = order_group['item_name'].str.contains('delivery', case=False).any()
                    tag = " - 🚚 DELIVERY" if is_delivery else ""

                    with st.expander(f"({time_str}) Order {order_num} - {customer}{tag}"):
                        # Inner loop for items remains the same
                        for item_name, item_group in order_group.groupby('item_name', sort=False):
                            qty = int(item_group['quantity'].iloc[0])
                            st.markdown(f"**{qty} - {item_name}**")

                            mods = item_group['mod_name'].dropna().unique()
                            if len(mods) > 0:
                                st.caption(f"↳ {', '.join(mods)}")
