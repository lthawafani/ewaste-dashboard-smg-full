"""
app.py
======
Streamlit Dashboard - E-Waste Collection Route Optimization
Semarang City | Dashboard System for Smart Reverse Logistics
"""

import io
import streamlit as st
import pandas as pd
import numpy as np
import folium
from streamlit_folium import st_folium
from lns import run_lns, Q_MAX, Q_MIN, W_MIN, K_MAX, C_DEP, C_LAB, C_FUEL

# ============================================================
# CONFIG
# ============================================================
st.set_page_config(
    page_title="E-Waste Route Optimizer — Semarang",
    page_icon="♻️",
    layout="wide"
)

VEHICLE_COLORS = ["blue", "green", "red"]
VEHICLE_LABELS = ["Vehicle 1", "Vehicle 2", "Vehicle 3"]

# ============================================================
# LOAD DATA
# ============================================================
@st.cache_data
def load_data():
    dist_matrix = pd.read_csv("data/distance_matrix.csv", index_col=0)
    locations   = pd.read_csv("data/locations.csv")
    return dist_matrix, locations

try:
    dist_matrix, locations = load_data()
    DATA_LOADED = True
    HAS_KECAMATAN = 'kecamatan' in locations.columns
except FileNotFoundError:
    DATA_LOADED = False
    HAS_KECAMATAN = False

# ============================================================
# HEADER
# ============================================================
st.title("♻️ E-Waste Collection Route Optimization Dashboard")
st.caption("Semarang City | Powered by Large Neighborhood Search (LNS)")
st.divider()

if not DATA_LOADED:
    st.error(
        "Data files not found. Please ensure `data/distance_matrix.csv` "
        "and `data/locations.csv` exist in the `data/` folder."
    )
    st.stop()

# ============================================================
# SIDEBAR
# ============================================================
with st.sidebar:
    st.header("⚙️ System Parameters")
    st.subheader("Vehicle")
    st.markdown(f"""
    - Type: Mitsubishi Canter
    - Max capacity: **{Q_MAX:,} kg**
    - Min load: **{Q_MIN:,} kg**
    - Available fleet: **{K_MAX} units**
    """)
    st.subheader("Cost Components")
    st.markdown(f"""
    - Depreciation: **IDR {C_DEP:,}/vehicle/cycle**
    - Labor: **IDR {C_LAB:,}/vehicle/cycle**
    - Fuel: **IDR {C_FUEL:,}/km**
    """)
    st.subheader("LNS Parameters")
    st.markdown(f"""
    - Min location weight: **{W_MIN} kg**
    - Destroy rate (ρ): **20%**
    - Stopping criterion: **100 iterations without improvement**
    """)
    st.divider()
    st.caption("Research Grant: Dashboard System for Routing Optimization "
               "of E-Waste Collection in Smart Reverse Logistics"
              " with contract number: 066/VRRTT/IV/2026.")

# ============================================================
# SESSION STATE INIT
# ============================================================
loc_nondepo = locations[locations["is_depot"] == 0].reset_index(drop=True)

if 'weights' not in st.session_state:
    st.session_state.weights = {int(row['id']): 0.0
                                 for _, row in loc_nondepo.iterrows()}

if 'last_skipped' not in st.session_state:
    st.session_state.last_skipped = {}

# ============================================================
# SECTION 1 — INPUT
# ============================================================
st.header("📥 E-Waste Weight Input per Location")
st.info(
    f"Enter the estimated e-waste weight (kg) at each collection location. "
    f"Locations with weight **< {W_MIN} kg** will be automatically skipped "
    f"and scheduled for the next collection cycle."
)

# ── Tombol Reset & Load Previous ──
col_btn1, col_btn2, col_btn3 = st.columns([1, 1, 4])

with col_btn1:
    if st.button("🔄 Reset All to Zero", use_container_width=True):
        for loc_id in st.session_state.weights:
            st.session_state.weights[loc_id] = 0.0
        st.rerun()

with col_btn2:
    has_previous = len(st.session_state.last_skipped) > 0
    if st.button(
        "📋 Load Previous Skipped",
        use_container_width=True,
        disabled=not has_previous,
        help="Load weights from locations skipped in the previous cycle"
               if has_previous else "No previous cycle data available"
    ):
        for loc_id, w in st.session_state.last_skipped.items():
            st.session_state.weights[loc_id] = w
        st.rerun()

st.markdown("")

# ── Input form per kecamatan ──
weights_input = {0: 0.0}  # depot

if HAS_KECAMATAN:
    # Group by kecamatan
    kecamatan_list = loc_nondepo['kecamatan'].dropna().unique().tolist()
    kecamatan_list = sorted([k for k in kecamatan_list if k != 'Depot'])

    for kec in kecamatan_list:
        locs_in_kec = loc_nondepo[loc_nondepo['kecamatan'] == kec].reset_index(drop=True)
        n_locs = len(locs_in_kec)

        with st.expander(f"📍 {kec} ({n_locs} locations)", expanded=False):
            cols_per_row = 3
            rows = [locs_in_kec.iloc[i:i+cols_per_row]
                    for i in range(0, len(locs_in_kec), cols_per_row)]

            for row_data in rows:
                cols = st.columns(cols_per_row)
                for col, (_, loc) in zip(cols, row_data.iterrows()):
                    with col:
                        loc_id = int(loc['id'])
                        current_val = st.session_state.weights.get(loc_id, 0.0)
                        # Truncate nama untuk label
                        nama = loc['nama']
                        label = nama if len(nama) <= 35 else nama[:33] + "..."
                        w = st.number_input(
                            label=f"**{label}**",
                            min_value=0.0,
                            max_value=float(Q_MAX),
                            value=current_val,
                            step=1.0,
                            key=f"weight_{loc_id}",
                            help=nama  # full name on hover
                        )
                        st.session_state.weights[loc_id] = w
                        weights_input[loc_id] = w
else:
    # Fallback: tanpa grouping kecamatan
    cols_per_row = 3
    rows = [loc_nondepo.iloc[i:i+cols_per_row]
            for i in range(0, len(loc_nondepo), cols_per_row)]

    for row_data in rows:
        cols = st.columns(cols_per_row)
        for col, (_, loc) in zip(cols, row_data.iterrows()):
            with col:
                loc_id = int(loc['id'])
                current_val = st.session_state.weights.get(loc_id, 0.0)
                nama  = loc['nama']
                label = nama if len(nama) <= 35 else nama[:33] + "..."
                w = st.number_input(
                    label=f"**{label}**",
                    min_value=0.0,
                    max_value=float(Q_MAX),
                    value=current_val,
                    step=1.0,
                    key=f"weight_{loc_id}",
                    help=nama
                )
                st.session_state.weights[loc_id] = w
                weights_input[loc_id] = w

# Summary metrics
total_input    = sum(v for k, v in weights_input.items() if k != 0)
eligible_count = sum(1 for k, v in weights_input.items() if k != 0 and v >= W_MIN)
skipped_count  = sum(1 for k, v in weights_input.items() if k != 0 and 0 < v < W_MIN)

c1, c2, c3 = st.columns(3)
c1.metric("Total Weight Input", f"{total_input:,.0f} kg")
c2.metric("Eligible Locations", f"{eligible_count} locations")
c3.metric("Skipped Locations (< 10 kg)", f"{skipped_count} locations")

st.divider()

# ============================================================
# SECTION 2 — RUN OPTIMIZATION
# ============================================================
st.header("🚀 Run Optimization")

run_btn = st.button("▶ Run LNS Optimization", type="primary", use_container_width=True)

if run_btn:
    with st.spinner("Running LNS optimization... please wait"):
        result = run_lns(weights=weights_input, dist_matrix_df=dist_matrix)

    if not result['dispatch']:
        st.warning(f"⚠️ {result['message']}")
        if result['skipped']:
            st.write("**Skipped locations:**",
                     [locations.loc[locations['id'] == i, 'nama'].values[0]
                      for i in result['skipped']])
        st.stop()

    # Simpan skipped ke session state untuk siklus berikutnya
    st.session_state.last_skipped = {
        node_id: weights_input.get(node_id, 0.0)
        for node_id in result['skipped']
        if weights_input.get(node_id, 0.0) > 0
    }

    st.success(
        f"✅ Optimization completed in **{result['iterations']} iterations**. "
        f"**{result['k_star']} vehicle(s)** active for this collection cycle."
    )

    # ── Save for Next Cycle button ──
    if st.button("💾 Save & Prepare for Next Cycle",
                 help="Resets visited locations to 0 and keeps skipped locations' weights"):
        for loc_id in weights_input:
            if loc_id == 0:
                continue
            if loc_id in result['skipped']:
                pass  # pertahankan bobot lokasi yang di-skip
            else:
                st.session_state.weights[loc_id] = 0.0
        st.success("✅ Ready for next cycle! Skipped locations retained.")
        st.rerun()

    # ============================================================
    # SECTION 3 — COST SUMMARY
    # ============================================================
    st.header("💰 Cost Summary")

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total Cost (TC)", f"IDR {result['tc']:,}")
    col2.metric("Fixed Cost (FC)", f"IDR {result['fc']:,}", help="Depreciation + Labor")
    col3.metric("Variable Cost (VC)", f"IDR {result['vc']:,}", help="Fuel cost")
    col4.metric("Total Distance", f"{result['total_dist']:,.2f} km")

    # LNS vs Initial Solution
    st.subheader("📊 LNS vs Initial Solution (Greedy Nearest Neighbor)")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Initial Distance", f"{result['dist_initial']:,.2f} km")
    c2.metric("LNS Distance", f"{result['total_dist']:,.2f} km",
              delta=f"-{result['improvement_dist']}%", delta_color="inverse")
    c3.metric("Initial Cost", f"IDR {result['tc_initial']:,}")
    c4.metric("LNS Cost", f"IDR {result['tc']:,}",
              delta=f"-{result['improvement_tc']}%", delta_color="inverse")

    # Breakdown per vehicle
    st.subheader("Breakdown per Vehicle")
    breakdown_data = []
    fc_per_vehicle = C_DEP + C_LAB
    for k in range(result['k_star']):
        vc_k = C_FUEL * result['dist_per_route'][k]
        breakdown_data.append({
            "Vehicle"        : VEHICLE_LABELS[k],
            "Distance (km)"  : f"{result['dist_per_route'][k]:,.2f}",
            "Load (kg)"      : f"{result['load_per_route'][k]:,.0f}",
            "Fixed Cost"     : f"IDR {fc_per_vehicle:,}",
            "Variable Cost"  : f"IDR {round(vc_k):,}",
            "Total"          : f"IDR {round(fc_per_vehicle + vc_k):,}"
        })
    st.dataframe(pd.DataFrame(breakdown_data), use_container_width=True, hide_index=True)

    st.divider()

    # ============================================================
    # SECTION 4 — MAP
    # ============================================================
    st.header("🗺️ Optimal Routes")

    center_lat = locations['lat'].mean()
    center_lon = locations['lon'].mean()
    peta = folium.Map(location=[center_lat, center_lon], zoom_start=13,
                      tiles="CartoDB positron")

    # Depot marker
    depot = locations[locations['is_depot'] == 1].iloc[0]
    folium.Marker(
        location=[depot['lat'], depot['lon']],
        popup="<b>DEPOT: TPA Jatibarang</b>",
        tooltip="DEPOT: TPA Jatibarang",
        icon=folium.Icon(color='black', icon='home', prefix='fa')
    ).add_to(peta)

    # Routes per vehicle
    for k, route in enumerate(result['routes']):
        color = VEHICLE_COLORS[k]
        label = VEHICLE_LABELS[k]

        route_coords = []
        for node in route:
            loc_row = locations[locations['id'] == node].iloc[0]
            route_coords.append([loc_row['lat'], loc_row['lon']])

        folium.PolyLine(
            locations=route_coords, color=color,
            weight=3, opacity=0.8, tooltip=label
        ).add_to(peta)

        # Marker dengan nomor urut
        stop_num = 0
        for node in route:
            if node == 0:
                continue
            stop_num += 1
            loc_row = locations[locations['id'] == node].iloc[0]
            nama = loc_row['nama']

            # DivIcon dengan nomor urut
            folium.Marker(
                location=[loc_row['lat'], loc_row['lon']],
                popup=(
                    f"<b>[{label}] Stop {stop_num}</b><br>"
                    f"{nama}<br>"
                    f"Weight: {weights_input[node]:,.0f} kg"
                ),
                tooltip=f"[{label}] Stop {stop_num}: {nama}",
                icon=folium.DivIcon(
                    html=f"""
                    <div style="
                        background-color: {'#3388ff' if color=='blue' else '#2ca02c' if color=='green' else '#d62728'};
                        color: white;
                        border-radius: 50%;
                        width: 24px;
                        height: 24px;
                        display: flex;
                        align-items: center;
                        justify-content: center;
                        font-weight: bold;
                        font-size: 11px;
                        border: 2px solid white;
                        box-shadow: 0 1px 3px rgba(0,0,0,0.4);
                    ">{stop_num}</div>
                    """,
                    icon_size=(24, 24),
                    icon_anchor=(12, 12)
                )
            ).add_to(peta)

    st_folium(peta, width=None, height=500, returned_objects=[])

    # ============================================================
    # SECTION 5 — VISIT SEQUENCE DETAIL
    # ============================================================
    st.subheader("Visit Sequence Detail")

    for k, route in enumerate(result['routes']):
        label = VEHICLE_LABELS[k]
        with st.expander(
            f"🚛 {label} — {result['dist_per_route'][k]:,.2f} km | "
            f"{result['load_per_route'][k]:,.0f} kg",
            expanded=True
        ):
            route_detail = []
            for stop_num, node in enumerate(route):
                loc_row = locations[locations['id'] == node].iloc[0]
                nama    = loc_row['nama']
                route_detail.append({
                    "Stop"       : stop_num,
                    "Location"   : "🏭 DEPOT (TPA Jatibarang)" if node == 0 else nama,
                    "Weight (kg)": "—" if node == 0 else f"{weights_input[node]:,.0f}"
                })
            st.dataframe(pd.DataFrame(route_detail),
                         use_container_width=True, hide_index=True)

    # ============================================================
    # SECTION 6 — SKIPPED LOCATIONS
    # ============================================================
    if result['skipped']:
        st.divider()
        st.subheader("⏭️ Skipped Locations (Scheduled for Next Cycle)")
        skip_data = []
        for node in result['skipped']:
            loc_row = locations[locations['id'] == node].iloc[0]
            skip_data.append({
                "Location"   : loc_row['nama'],
                "Weight (kg)": weights_input.get(node, 0),
                "Reason"     : f"Weight < {W_MIN} kg — deferred to next collection cycle"
            })
        st.dataframe(pd.DataFrame(skip_data), use_container_width=True, hide_index=True)

    # ============================================================
    # SECTION 7 — EXPORT CSV
    # ============================================================
    st.divider()
    st.subheader("📥 Export Results")

    export_rows = []
    fc_per_vehicle = C_DEP + C_LAB

    for k, route in enumerate(result['routes']):
        label    = VEHICLE_LABELS[k]
        dist_k   = result['dist_per_route'][k]
        load_k   = result['load_per_route'][k]
        vc_k     = round(C_FUEL * dist_k)
        total_k  = round(fc_per_vehicle + vc_k)
        stop_num = 0

        for node in route:
            loc_row = locations[locations['id'] == node].iloc[0]
            is_depot = node == 0
            if not is_depot:
                stop_num += 1

            export_rows.append({
                "Vehicle"         : label,
                "Stop"            : stop_num if not is_depot else "DEPOT",
                "Location"        : "DEPOT (TPA Jatibarang)" if is_depot else loc_row['nama'],
                "Kecamatan"       : "Depot" if is_depot else (loc_row.get('kecamatan', '-') if HAS_KECAMATAN else '-'),
                "Weight (kg)"     : "" if is_depot else weights_input.get(node, 0),
                "Route Dist (km)" : dist_k,
                "Route Load (kg)" : load_k,
                "Fixed Cost (IDR)": fc_per_vehicle,
                "Variable Cost (IDR)": vc_k,
                "Total Cost (IDR)": total_k,
                "Status"          : "Visited"
            })

    # Tambahkan skipped locations
    for node in result['skipped']:
        loc_row = locations[locations['id'] == node].iloc[0]
        export_rows.append({
            "Vehicle"            : "-",
            "Stop"               : "-",
            "Location"           : loc_row['nama'],
            "Kecamatan"          : loc_row.get('kecamatan', '-') if HAS_KECAMATAN else '-',
            "Weight (kg)"        : weights_input.get(node, 0),
            "Route Dist (km)"    : "-",
            "Route Load (kg)"    : "-",
            "Fixed Cost (IDR)"   : "-",
            "Variable Cost (IDR)": "-",
            "Total Cost (IDR)"   : "-",
            "Status"             : "Skipped (deferred to next cycle)"
        })

    df_export = pd.DataFrame(export_rows)

    csv_buffer = io.StringIO()
    df_export.to_csv(csv_buffer, index=False)
    csv_str = csv_buffer.getvalue()

    st.download_button(
        label="⬇️ Download Results as CSV",
        data=csv_str,
        file_name="ewaste_route_optimization_results.csv",
        mime="text/csv",
        use_container_width=True
    )
