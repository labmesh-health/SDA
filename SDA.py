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

# --- Clinical Knowledge Base ---
ALARM_MAP = {
    ">v": {"name": "Above Technical Limit", "sev": "High", "msg": "Exceeds measurable range. Dilution required."},
    "<v": {"name": "Below Technical Limit", "sev": "High", "msg": "Result below measurable range."},
    "Short": {"name": "Short Sample", "sev": "Critical", "msg": "Insufficient volume. Check for micro-cups."},
    "Clot": {"name": "Clot Detected", "sev": "Critical", "msg": "Fibrin detected. Re-spin sample."},
    "Lin": {"name": "Linearity Error", "sev": "Medium", "msg": "Non-linear reaction. Review calibration."},
    "Reag": {"name": "Reagent Issue", "sev": "Medium", "msg": "Check reagent pack integrity."},
    "S.Idx": {"name": "Serum Index Warning", "sev": "Low", "msg": "HIL interference detected."},
}

@st.cache_data
def process_data(file_bytes):
    content = file_bytes.decode("utf-8", errors="replace")
    reader = csv.reader(io.StringIO(content))
    raw_data = list(reader)
    if len(raw_data) < 2: return None
    row0, header_row = raw_data[0], raw_data[1]

    try:
        draw_idx = header_row.index("Drawing_Date_Time")
        cup_idx = header_row.index("Sample_Cup")
        start_col = header_row.index("Result") 
        block_size = 11 if "EMF1" in header_row else 8
        
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
        
        blocks = []
        for col in range(start_col, len(header_row), block_size):
            if col + block_size <= len(header_row):
                acn, param = (row0[col], row0[col+1]) if col+1 < len(row0) else ("", "")
                for row_vals in raw_data[2:]:
                    if len(row_vals) > col and any(val.strip() for val in row_vals[col:col+block_size]):
                        payload = row_vals[:draw_idx+1] + row_vals[draw_idx+1:cup_idx] + row_vals[cup_idx:start_col] + [acn, param] + row_vals[col:col+block_size]
                        if len(payload) == len(final_headers): blocks.append(payload)
        
        df = pd.DataFrame(blocks, columns=final_headers)
        
        # Datetimes
        df['Drawing_Date_Time'] = pd.to_datetime(df['Drawing_Date_Time'], errors='coerce')
        df['Arrived_Date_Time'] = pd.to_datetime(df['Arrived_Date_Time'], errors='coerce')
        df['Sampling_Date_Time'] = pd.to_datetime(df['Sampling_Date_Time'], errors='coerce')
        df['Result_Numeric'] = pd.to_numeric(df['Result'], errors='coerce')

        # Enriched Columns
        df['Journey_Transport_Min'] = (df['Arrived_Date_Time'] - df['Drawing_Date_Time']).dt.total_seconds() / 60
        df['Journey_Loading_Min'] = (df['Sampling_Date_Time'] - df['Arrived_Date_Time']).dt.total_seconds() / 60
        
        def parse_au(au_str):
            if not au_str or pd.isna(au_str): return "N/A", "Unknown", "Unknown"
            parts = str(au_str).split('-')
            pos, mtype = parts[0], (parts[1] if len(parts) > 1 else "N/A")
            sub = parts[2] if len(parts) > 2 else "0"
            return pos, mtype, f"{mtype}-{sub}"

        df[['AU_Pos', 'AU_Class', 'AU_SubUnit']] = df['Module'].apply(lambda x: pd.Series(parse_au(x)))
        df['Alarm_Meaning'] = df['Data_Alarm'].str.strip().apply(lambda x: ALARM_MAP.get(x, {"name": ""})['name'] if x else "")

        mappings = {
            "Gender": {"0": "Not entered", "1": "Male", "2": "Female"},
            "Discrimination": {"1": "Patient (Routine)", "2": "Patient (STAT)", "3": "QC (Control)"},
            "Run": {"1": "1st run", "2": "Rerun"}
        }
        for col in mappings:
            if col in df.columns: df[col] = df[col].astype(str).map(mappings[col]).fillna(df[col])
            
        return df
    except Exception as e:
        st.error(f"Processing Error: {e}"); return None

def render_insight(title, obs, impact, pre):
    st.markdown(f"""<div style="background-color: #f0f2f6; padding: 20px; border-radius: 10px; border-left: 5px solid #0b41cd; margin-bottom: 25px;">
        <h4 style="margin-top:0; color: #0b41cd;">🧠 Insight: {title}</h4>
        <div style="display: flex; gap: 20px;"><div style="flex: 1;"><strong>Observation</strong><br>{obs}</div>
        <div style="flex: 1;"><strong>Impact</strong><br>{impact}</div><div style="flex: 1;"><strong>Prescription</strong><br>{pre}</div></div></div>""", unsafe_allow_html=True)

# --- Sidebar ---
with st.sidebar:
    st.title("💡 converterPRO")
    uploaded_file = st.file_uploader("Upload Instrument CSV", type=["csv"])
    if uploaded_file:
        raw_df = process_data(uploaded_file.getvalue())
        if raw_df is not None:
            st.markdown("---")
            min_d, max_d = raw_df['Arrived_Date_Time'].min().date(), raw_df['Arrived_Date_Time'].max().date()
            sel_range = st.date_input("Date Range", [min_d, max_d], min_value=min_d, max_value=max_d)
            sel_cats = st.multiselect("Data Categories", raw_df['Discrimination'].unique().tolist(), default=raw_df['Discrimination'].unique().tolist())

# --- Main App ---
if uploaded_file and 'raw_df' in locals() and raw_df is not None:
    start_d = sel_range[0]
    end_d = sel_range[1] if len(sel_range) > 1 else start_d
    mask = (raw_df['Arrived_Date_Time'].dt.date >= start_d) & (raw_df['Arrived_Date_Time'].dt.date <= end_d) & (raw_df['Discrimination'].isin(sel_cats))
    df = raw_df.loc[mask]

    t = st.tabs(["📄 Raw Data", "📊 Test Analytics", "🧪 Quality & QC", "⚠️ Alarms", "🧠 Insights"])
    
    with t[0]:
        st.dataframe(df, use_container_width=True)
        st.download_button("📥 Export CSV", df.to_csv(index=False), f"Enriched_{uploaded_file.name}")

    with t[1]:
        st.subheader("Throughput & Utilization")
        caps = {"c 503": (1000, 800), "ISE": (900, 850), "e 801": (300, 275)}
        u_df = df.dropna(subset=['Sampling_Date_Time']).copy()
        u_df['S_Hour'], u_df['S_Date'] = u_df['Sampling_Date_Time'].dt.hour, u_df['Sampling_Date_Time'].dt.date
        h_util = u_df.groupby(['S_Date', 'S_Hour', 'AU_Class']).size().reset_index(name='Tests')
        
        # 1. Hourly Pattern (Restored)
        sel_m = st.selectbox("Select Module to view Hourly Pattern:", h_util['AU_Class'].unique().tolist())
        st.plotly_chart(px.line(h_util[h_util['AU_Class'] == sel_m], x='S_Hour', y='Tests', color='S_Date', markers=True).update_layout(xaxis=dict(tickmode='linear', range=[0, 23])), use_container_width=True)

        # 2. Peak Metrics (Restored)
        cols = st.columns(len(caps))
        peak_stats = []
        for idx, (m_type, values) in enumerate(caps.items()):
            m_max, m_prac = values
            peak_val = h_util[h_util['AU_Class'].str.contains(m_type, na=False)]['Tests'].max() if any(m_type in str(x) for x in h_util['AU_Class']) else 0
            cols[idx].metric(f"{m_type} Peak", f"{int(peak_val)} T/Hr", f"{((peak_val/m_prac)*100 if m_prac>0 else 0):.1f}% Capacity")
            peak_stats.append({'Module': m_type, 'Peak': peak_val, 'Practical': m_prac, 'Theoretical': m_max})
        
        # 3. Capacity Bar (Restored)
        fig_p = go.Figure()
        fig_p.add_trace(go.Bar(x=[d['Module'] for d in peak_stats], y=[d['Peak'] for d in peak_stats], name="Peak Throughput", marker_color='#0b41cd'))
        for i, d in enumerate(peak_stats):
            fig_p.add_shape(type="line", x0=i-0.3, y0=d['Practical'], x1=i+0.3, y1=d['Practical'], line=dict(color="orange", width=3, dash="dash"))
            fig_p.add_shape(type="line", x0=i-0.3, y0=d['Theoretical'], x1=i+0.3, y1=d['Theoretical'], line=dict(color="red", width=3))
        st.plotly_chart(fig_p.update_layout(title="Peak Throughput vs Module Limits (Red=Max, Orange=Practical)"), use_container_width=True)

    with t[2]:
        st.subheader("QC Precision & First-Pass Yield")
        q_df = df[df['Discrimination'].str.contains("QC", na=False)].copy()
        if not q_df.empty:
            # 1. QC Matrix (Restored)
            q_df['HF'] = q_df['Arrived_Date_Time'].dt.hour + q_df['Arrived_Date_Time'].dt.minute/60
            st.plotly_chart(px.scatter(q_df, x='HF', y='Parameter', color='Parameter', title="QC Timing Matrix (24h)"), use_container_width=True)
            
            # 2. Precision Table (Restored)
            st.write("#### QC Statistical Summary")
            qc_stats = q_df.groupby(['Parameter', 'Sample_ID'])['Result_Numeric'].agg(Runs='count', Mean='mean', SD='std').reset_index()
            qc_stats['CV%'] = ((qc_stats['SD'] / qc_stats['Mean']) * 100).round(2)
            st.dataframe(qc_stats, use_container_width=True)
            
            # 3. Distribution Boxplots (Restored)
            c1, c2 = st.columns(2)
            c1.plotly_chart(px.box(q_df[q_df['AU_Class'].str.contains("c 503|ISE")], x='Parameter', y='Result_Numeric', title="Chemistry Stability"), use_container_width=True)
            c2.plotly_chart(px.box(q_df[q_df['AU_Class'].str.contains("e 801")], x='Parameter', y='Result_Numeric', title="Immunoassay Stability"), use_container_width=True)
        
        # 4. First Pass Yield
        counts = df['Run'].value_counts()
        st.plotly_chart(px.pie(values=counts.values, names=counts.index, hole=0.4, title="Rerun Ratio"), use_container_width=True)

    with t[3]:
        st.subheader("Error & Alarm Detection")
        # 1. Top 20 Alarms Bar (Restored - Ensures data visibility)
        err_data = df[df['Data_Alarm'].str.strip() != ""].copy()
        if not err_data.empty:
            alarm_counts = err_data.groupby(['Module', 'Data_Alarm']).size().reset_index(name='C').sort_values('C', ascending=False).head(20)
            st.plotly_chart(px.bar(alarm_counts, x='Data_Alarm', y='C', color='Module', text='C', title="Top 20 Raw System Alarms"), use_container_width=True)
            
            # 2. Translated Treemap
            st.plotly_chart(px.treemap(err_data, path=['AU_Class', 'Alarm_Meaning'], title="Translated Alarm Hierarchy"), use_container_width=True)
        else:
            st.success("No alarms detected in this dataset.")

    with t[4]:
        st.subheader("Prescriptive Insights")
        # Sub-Module Load
        load = df['AU_SubUnit'].value_counts().reset_index()
        load.columns = ['Unit', 'Count']
        st.plotly_chart(px.bar(load, x='Unit', y='Count', color='Unit', title="Mechanical Load Balancing"), use_container_width=True)
        
        # Insight Cards
        render_insight("Mechanical Wear", "Load balance analysis.", "Uneven wear leads to premature failure.", "Re-map assays to balance units.")
        j_avg = df['Journey_Loading_Min'].mean()
        render_insight("Lab Journey", f"Avg loading delay: {j_avg:.1f}m", "Impacts TAT.", "Prioritize STAT racks.")

else:
    st.info("👈 Upload a CSV in the sidebar to begin.")
