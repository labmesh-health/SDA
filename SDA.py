import streamlit as st
import pandas as pd
import csv
import io
import plotly.express as px
import plotly.graph_objects as go
import numpy as np
from datetime import datetime

# --- Page Configuration ---
st.set_page_config(page_title="converterPRO", page_icon="💡", layout="wide")

# --- Clinical Knowledge Base (from Documentation) ---
ALARM_MAP = {
    ">v": {"name": "Above Technical Limit", "sev": "High", "msg": "Exceeds measurable range. Dilution required."},
    "<v": {"name": "Below Technical Limit", "sev": "High", "msg": "Result below measurable range."},
    "Short": {"name": "Short Sample", "sev": "Critical", "msg": "Insufficient volume. Check for micro-cups or air bubbles."},
    "Clot": {"name": "Clot Detected", "sev": "Critical", "msg": "Fibrin/clot detected during aspiration. Re-spin sample."},
    "Lin": {"name": "Linearity Error", "sev": "Medium", "msg": "Reaction curve non-linear. Review calibration."},
    "Reag": {"name": "Reagent Issue", "sev": "Medium", "msg": "Check reagent pack integrity or volume."},
    "S.Idx": {"name": "Serum Index Warning", "sev": "Low", "msg": "HIL interference (Hemolysis/Icterus/Lipemia)."},
}

@st.cache_data
def process_data(file_bytes):
    content = file_bytes.decode("utf-8", errors="replace")
    reader = csv.reader(io.StringIO(content))
    raw_data = list(reader)
    if len(raw_data) < 2: return None
    row0, header_row = raw_data[0], raw_data[1]

    try:
        # 1. Structural Identification
        draw_idx = header_row.index("Drawing_Date_Time")
        arr_idx = header_row.index("Arrived_Date_Time")
        cup_idx = header_row.index("Sample_Cup")
        start_col = header_row.index("Result") 
        block_size = 11 if "EMF1" in header_row else 8
        
        # 2. Column Normalization
        block_template = header_row[start_col : start_col + block_size]
        module_sub_idx = next((i for i, h in enumerate(block_template) if h in ["Module", "AU", "Unit_ID"]), -1)
        alarm_sub_idx = next((i for i, h in enumerate(block_template) if h in ["Data_Alarm", "Alarm"]), -1)
        sampling_sub_idx = next((i for i, h in enumerate(block_template) if "Sampling_Date_Time" in h), -1)

        fixed_before = header_row[:draw_idx + 1]
        comment_cols = header_row[draw_idx + 1 : cup_idx]
        fixed_after = header_row[cup_idx : start_col]
        
        standard_block_headers = list(block_template)
        if module_sub_idx != -1: standard_block_headers[module_sub_idx] = "Module"
        if alarm_sub_idx != -1: standard_block_headers[alarm_sub_idx] = "Data_Alarm"
        if sampling_sub_idx != -1: standard_block_headers[sampling_sub_idx] = "Sampling_Date_Time"
        
        final_headers = fixed_before + comment_cols + fixed_after + ["ACN code", "Parameter"] + standard_block_headers
        
        # 3. Unpivoting Engine
        blocks = []
        for col in range(start_col, len(header_row), block_size):
            if col + block_size <= len(header_row):
                acn, param = (row0[col], row0[col+1]) if col+1 < len(row0) else ("", "")
                for row_vals in raw_data[2:]:
                    if len(row_vals) > col and any(val.strip() for val in row_vals[col:col+block_size]):
                        payload = row_vals[:draw_idx+1] + row_vals[draw_idx+1:cup_idx] + row_vals[cup_idx:start_col] + [acn, param] + row_vals[col:col+block_size]
                        if len(payload) == len(final_headers): blocks.append(payload)
        
        df = pd.DataFrame(blocks, columns=final_headers)
        
        # 4. New Additions: Datetime & Durations
        df['Drawing_Date_Time'] = pd.to_datetime(df['Drawing_Date_Time'], errors='coerce')
        df['Arrived_Date_Time'] = pd.to_datetime(df['Arrived_Date_Time'], errors='coerce')
        df['Sampling_Date_Time'] = pd.to_datetime(df['Sampling_Date_Time'], errors='coerce')
        df['Result_Numeric'] = pd.to_numeric(df['Result'], errors='coerce')

        # Calculate Journey Durations (New Addition to Table)
        df['Journey_Transport_Min'] = (df['Arrived_Date_Time'] - df['Drawing_Date_Time']).dt.total_seconds() / 60
        df['Journey_Loading_Min'] = (df['Sampling_Date_Time'] - df['Arrived_Date_Time']).dt.total_seconds() / 60
        
        # 5. New Additions: AU Parsing (Sub-units)
        def parse_au(au_str):
            if not au_str or pd.isna(au_str): return "N/A", "Unknown", "Unknown"
            parts = str(au_str).split('-')
            pos = parts[0] if len(parts) > 0 else "N/A"
            mtype = parts[1] if len(parts) > 1 else "N/A"
            sub = parts[2] if len(parts) > 2 else "0"
            return pos, mtype, f"{mtype}-{sub}"

        df[['AU_Position', 'AU_Class', 'AU_SubUnit_ID']] = df['Module'].apply(lambda x: pd.Series(parse_au(x)))
        
        # 6. New Additions: Alarm Interpretation
        df['Alarm_Meaning'] = df['Data_Alarm'].str.strip().apply(lambda x: ALARM_MAP.get(x, {"name": ""})['name'] if x else "")

        # 7. Standard Mappings
        mappings = {
            "Gender": {"0": "Not entered", "1": "Male", "2": "Female"},
            "Discrimination": {"1": "Patient (Routine)", "2": "Patient (STAT)", "3": "QC (Control)"},
            "Run": {"1": "1st run", "2": "Rerun"}
        }
        for col in mappings:
            if col in df.columns: df[col] = df[col].astype(str).map(mappings[col]).fillna(df[col])
            
        return df
    except Exception as e:
        st.error(f"Processing Error: {e}")
        return None

def render_insight(title, obs, impact, pre):
    st.markdown(f"""
    <div style="background-color: #f0f2f6; padding: 20px; border-radius: 10px; border-left: 5px solid #0b41cd; margin-bottom: 20px;">
        <h4 style="margin-top:0; color: #0b41cd;">🧠 Insight: {title}</h4>
        <div style="display: flex; gap: 20px;">
            <div style="flex: 1;"><strong>Observation</strong><br>{obs}</div>
            <div style="flex: 1;"><strong>Impact</strong><br>{impact}</div>
            <div style="flex: 1;"><strong>Prescription</strong><br>{pre}</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

# --- Sidebar ---
with st.sidebar:
    st.title("💡 converterPRO")
    uploaded_file = st.file_uploader("Upload Instrument CSV", type=["csv"])
    if uploaded_file:
        raw_df = process_data(uploaded_file.getvalue())
        if raw_df is not None:
            st.markdown("---")
            st.subheader("📅 Filter View")
            min_d, max_d = raw_df['Arrived_Date_Time'].min().date(), raw_df['Arrived_Date_Time'].max().date()
            sel_range = st.date_input("Date Range", [min_d, max_d], min_value=min_d, max_value=max_d)
            sel_cats = st.multiselect("Sample Types", raw_df['Discrimination'].unique().tolist(), default=raw_df['Discrimination'].unique().tolist())

# --- Main App ---
if uploaded_file and 'raw_df' in locals() and raw_df is not None:
    # Handle Date Selection
    start_d = sel_range[0]
    end_d = sel_range[1] if len(sel_range) > 1 else start_d
    mask = (raw_df['Arrived_Date_Time'].dt.date >= start_d) & \
           (raw_df['Arrived_Date_Time'].dt.date <= end_d) & \
           (raw_df['Discrimination'].isin(sel_cats))
    df = raw_df.loc[mask]

    tabs = st.tabs(["📄 Raw Data", "🕒 Lab Journey", "🧪 Quality/Reruns", "⚠️ Alarms", "⚙️ Hardware Load"])
    
    with tabs[0]:
        st.subheader("Unpivoted Instrument Data (Enriched)")
        st.write("This table contains all unpivoted results plus new clinical intelligence columns.")
        st.dataframe(df, use_container_width=True)
        st.download_button("📥 Export CSV", df.to_csv(index=False), f"Enriched_{uploaded_file.name}")

    with tabs[1]:
        st.subheader("Efficiency Tracker: The Lab Journey")
        j_df = df.dropna(subset=['Journey_Transport_Min', 'Journey_Loading_Min'])
        if not j_df.empty:
            c1, c2 = st.columns(2)
            c1.metric("Avg Transport", f"{j_df['Journey_Transport_Min'].mean():.1f} min")
            c2.metric("Avg Loading", f"{j_df['Journey_Loading_Min'].mean():.1f} min")
            st.plotly_chart(px.box(j_df, x='Discrimination', y='Journey_Loading_Min', color='Discrimination', title="Arrival to Sampling delay"))
            render_insight("Process Bottlenecks", f"Avg loading delay: {j_df['Journey_Loading_Min'].mean():.1f} min.", "Delay impacts total Turnaround Time.", "Review buffer prioritization if STAT > 15m.")

    with tabs[2]:
        st.subheader("First-Pass Yield")
        counts = df['Run'].value_counts()
        st.plotly_chart(px.pie(values=counts.values, names=counts.index, hole=0.5))
        render_insight("Quality Yield", f"Rerun rate: {(counts.get('Rerun', 0)/len(df)*100):.1f}%", "Reruns increase reagent waste.", "Audit assays with >10% rerun rate.")

    with tabs[3]:
        st.subheader("Alarm & Risk Analysis")
        a_df = df[df['Alarm_Meaning'] != ""]
        if not a_df.empty:
            st.plotly_chart(px.treemap(a_df, path=['AU_Class', 'Alarm_Meaning'], color='Alarm_Meaning'))
            render_insight("Clinical Risk", f"Top alarm: {a_df['Alarm_Meaning'].value_counts().idxmax()}", "Alarms compromise result accuracy.", "Focus training on frequent pre-analytical alarms.")

    with tabs[4]:
        st.subheader("Mechanical Load Balancing")
        load = df['AU_SubUnit_ID'].value_counts().reset_index()
        load.columns = ['Unit', 'Count']
        st.plotly_chart(px.bar(load, x='Unit', y='Count', color='Unit'))
        if len(load) > 1:
            imb = load['Count'].max() / load['Count'].min()
            if imb > 1.2:
                render_insight("Mechanical Skew", f"Unit imbalance: {imb:.1f}x", "Uneven wear leads to premature failure.", "Re-map high-volume tests to balance load.")
else:
    st.info("👈 Upload a CSV to begin.")
