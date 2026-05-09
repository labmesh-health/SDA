import streamlit as st
import pandas as pd
import csv
import io
import plotly.express as px
import plotly.graph_objects as go
import numpy as np

# --- Page Configuration ---
st.set_page_config(page_title="converterPRO", page_icon="💡", layout="wide")

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
        df['Arrived_Date_Time'] = pd.to_datetime(df['Arrived_Date_Time'], errors='coerce')
        df['Sampling_Date_Time'] = pd.to_datetime(df['Sampling_Date_Time'], errors='coerce')
        df['Result_Numeric'] = pd.to_numeric(df['Result'], errors='coerce')
        
        mappings = {"Gender": {"0": "Not entered", "1": "Male", "2": "Female"},
                    "Discrimination": {"1": "Patient (Routine)", "2": "Patient (STAT)", "3": "QC (Control)"}}
        for col in mappings:
            if col in df.columns: df[col] = df[col].astype(str).map(mappings[col]).fillna(df[col])
        return df
    except Exception as e:
        st.error(f"Processing Error: {e}"); return None

# --- Sidebar ---
with st.sidebar:
    st.title("💡 converterPRO")
    uploaded_file = st.file_uploader("Upload Instrument CSV", type=["csv"])
    if uploaded_file:
        raw_df = process_data(uploaded_file.getvalue())
        if raw_df is not None:
            st.markdown("---")
            min_d, max_d = raw_df['Arrived_Date_Time'].min().date(), raw_df['Arrived_Date_Time'].max().date()
            sel_range = st.date_input("Date Range", [min_d, max_d])
            sel_cats = st.multiselect("Data Categories", raw_df['Discrimination'].unique().tolist(), default=raw_df['Discrimination'].unique().tolist())

    st.sidebar.markdown("---")
    st.sidebar.caption("⚙️ **Engine Details**")
    st.sidebar.markdown("- **Adaptive Engine:** v4.1\n- **Compatibility:** cobas pro\n- **Copyright:** LabMesh.com")

# --- Main App ---
if uploaded_file and raw_df is not None:
    mask = (raw_df['Arrived_Date_Time'].dt.date >= sel_range[0]) & (raw_df['Arrived_Date_Time'].dt.date <= sel_range[1]) & (raw_df['Discrimination'].isin(sel_cats))
    df = raw_df.loc[mask]

    t1, t2, t3, t4 = st.tabs(["📄 Raw Data", "📊 Test Analytics", "🧪 Quality Control", "⚠️ Error Detection"])
    
    with t1:
        st.subheader("Instrument Raw Data")
        st.dataframe(df, use_container_width=True)
        st.download_button("📥 Export CSV", df.to_csv(index=False), "export.csv")

    with t2:
        st.subheader("Module Throughput & Capacity")
        if 'Module' in df.columns and 'Sampling_Date_Time' in df.columns:
            caps = {"c 503": (1000, 800), "ISE": (900, 850), "e 801": (300, 275)}
            util_df = df.copy().dropna(subset=['Sampling_Date_Time'])
            util_df['Norm_Mod'] = util_df['Module'].apply(lambda x: next((k for k in caps if k in str(x)), "Other"))
            util_df['S_Hour'] = util_df['Sampling_Date_Time'].dt.hour
            util_df['S_Date'] = util_df['Sampling_Date_Time'].dt.strftime('%Y-%m-%d')
            
            # --- 1. Peak KPI Metrics ---
            hourly_util = util_df.groupby(['S_Date', 'S_Hour', 'Norm_Mod']).size().reset_index(name='Tests')
            cols = st.columns(len(caps))
            peak_stats = []
            for idx, (m_type, values) in enumerate(caps.items()):
                m_max, m_prac = values
                peak_val = hourly_util[hourly_util['Norm_Mod'] == m_type]['Tests'].max() if m_type in hourly_util['Norm_Mod'].values else 0
                cols[idx].metric(f"{m_type} Peak", f"{peak_val} T/Hr", f"{((peak_val/m_prac)*100):.1f}% Capacity" if m_prac > 0 else "0%")
                peak_stats.append({'Module': m_type, 'Peak': peak_val, 'Practical': m_prac, 'Theoretical': m_max})

            # --- 2. Interactive Throughput Line Graph ---
            st.markdown("---")
            st.write("#### 📈 Module Throughput Pattern (Line Graph)")
            available_modules = hourly_util['Norm_Mod'].unique().tolist()
            selected_mod_view = st.selectbox("Select Module to View Hourly Pattern", available_modules)
            
            filtered_trend = hourly_util[hourly_util['Norm_Mod'] == selected_mod_view]
            fig_trend = px.line(filtered_trend, x='S_Hour', y='Tests', color='S_Date', 
                                markers=True, text='Tests',
                                labels={'S_Hour': 'Hour (24h)', 'Tests': 'Total Tests Processed'},
                                title=f"Hourly Performance Trend: {selected_mod_view}")
            fig_trend.update_traces(textposition="top center")
            fig_trend.update_layout(xaxis=dict(tickmode='linear', range=[0, 23]))
            st.plotly_chart(fig_trend, use_container_width=True)

            # --- 3. Peak Bar Chart with Limit Lines ---
            st.markdown("---")
            st.write("#### 🚀 Peak Throughput vs. Instrument Limits")
            fig_peak = go.Figure()
            fig_peak.add_trace(go.Bar(x=[d['Module'] for d in peak_stats], y=[d['Peak'] for d in peak_stats], name='Actual Peak', marker_color='#0b41cd', text=[d['Peak'] for d in peak_stats], textposition='auto'))
            for i, d in enumerate(peak_stats):
                fig_peak.add_shape(type="line", x0=i-0.4, y0=d['Practical'], x1=i+0.4, y1=d['Practical'], line=dict(color="orange", width=3, dash="dash"))
                fig_peak.add_shape(type="line", x0=i-0.4, y0=d['Theoretical'], x1=i+0.4, y1=d['Theoretical'], line=dict(color="red", width=3))
            st.plotly_chart(fig_peak, use_container_width=True)
            st.caption("🔴 Red = Theoretical Max | 🟠 Orange Dash = Practical Limit")

        st.markdown("---")
        # Restored Arrival Pattern, Parameter Bar, and Gender Pie
        st.write("#### 🕒 24-Hour Sample Arrival Pattern (Entry into Lab)")
        p_df = df[df['Discrimination'].str.contains("Patient", na=False)].copy()
        if not p_df.empty:
            p_df['Hour'] = p_df['Arrived_Date_Time'].dt.hour
            p_df['Date'] = p_df['Arrived_Date_Time'].dt.strftime('%Y-%m-%d')
            h_counts = p_df.groupby(['Date', 'Hour'])['Sample_ID'].nunique().reset_index(name='Samples')
            st.plotly_chart(px.line(h_counts, x='Hour', y='Samples', color='Date', markers=True, text='Samples').update_layout(xaxis=dict(tickmode='linear', range=[0, 23])), use_container_width=True)

        c1, c2 = st.columns(2)
        with c1:
            st.plotly_chart(px.bar(df['Parameter'].value_counts().reset_index(), x='Parameter', y='count', title="Test Volume", color='Parameter'), use_container_width=True)
        with c2:
            st.plotly_chart(px.pie(df, names='Gender', hole=0.4, title="Gender Distribution"), use_container_width=True)

    with t3:
        st.subheader("Quality Control Precision")
        q_df = df[df['Discrimination'].str.contains("QC", na=False)].copy()
        if not q_df.empty:
            q_df['HourFloat'] = q_df['Arrived_Date_Time'].dt.hour + q_df['Arrived_Date_Time'].dt.minute/60
            st.plotly_chart(px.scatter(q_df, x='HourFloat', y='Parameter', color='Parameter', title="Execution Timing").update_layout(xaxis=dict(tickmode='linear', range=[0, 24])), use_container_width=True)
            q_df['Date'] = q_df['Arrived_Date_Time'].dt.date
            qc_stats = q_df.groupby(['Date', 'Parameter', 'Sample_ID'])['Result_Numeric'].agg(Runs='count', Mean='mean', SD='std').reset_index()
            qc_stats['CV%'] = ((qc_stats['SD'] / qc_stats['Mean']) * 100).round(2).map("{:.2f}%".format)
            st.dataframe(qc_stats, use_container_width=True)
            st.plotly_chart(px.box(q_df, x='Parameter', y='Result_Numeric', color='Parameter', title="QC Stability Plot"), use_container_width=True)

    with t4:
        st.subheader("Error Analytics")
        if 'Data_Alarm' in df.columns:
            error_df = df[df['Data_Alarm'].str.strip() != ""].copy()
            if not error_df.empty:
                top_alarms = error_df.groupby(['Module', 'Data_Alarm']).size().reset_index(name='Count').sort_values('Count', ascending=False).head(20)
                st.plotly_chart(px.bar(top_alarms, x='Data_Alarm', y='Count', color='Module', text='Count', title="Top 20 Data Alarms"), use_container_width=True)
                st.dataframe(error_df[['Arrived_Date_Time', 'Sample_ID', 'Parameter', 'Module', 'Data_Alarm']], use_container_width=True)
else:
    st.title("Welcome to converterPRO")
    st.info("System Ready. Please upload a file to begin.")
