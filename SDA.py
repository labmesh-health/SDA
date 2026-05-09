import streamlit as st
import pandas as pd
import csv
import io
import plotly.express as px
import numpy as np

# --- Page Configuration ---
st.set_page_config(page_title="converterPRO", page_icon="💡", layout="wide")

# --- Adaptive Processing Engine ---
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
        fixed_before = header_row[:draw_idx + 1]
        comment_cols = header_row[draw_idx + 1 : cup_idx]
        fixed_after = header_row[cup_idx : start_col]
        block_headers = header_row[start_col : start_col + block_size]
        final_headers = fixed_before + comment_cols + fixed_after + ["ACN code", "Parameter"] + block_headers
        
        blocks = []
        for col in range(start_col, len(header_row), block_size):
            if col + block_size <= len(header_row):
                acn, param = (row0[col], row0[col+1]) if col+1 < len(row0) else ("", "")
                for row_vals in raw_data[2:]:
                    if len(row_vals) > col and any(val.strip() for val in row_vals[col:col+block_size]):
                        blocks.append(row_vals[:draw_idx+1] + row_vals[draw_idx+1:cup_idx] + row_vals[cup_idx:start_col] + [acn, param] + row_vals[col:col+block_size])
        
        df = pd.DataFrame(blocks, columns=final_headers)
        df['Arrived_Date_Time'] = pd.to_datetime(df['Arrived_Date_Time'], errors='coerce')
        df['Result_Numeric'] = pd.to_numeric(df['Result'], errors='coerce')
        
        mappings = {"Gender": {"0": "Not entered", "1": "Male", "2": "Female"},
                    "Discrimination": {"1": "Patient (Routine)", "2": "Patient (STAT)", "3": "QC (Control)"}}
        for col, m in mappings.items():
            if col in df.columns: df[col] = df[col].astype(str).map(m).fillna(df[col])
        return df
    except Exception as e:
        st.error(f"Processing Error: {e}")
        return None

# --- Sidebar UI ---
with st.sidebar:
    st.title("💡 converterPRO")
    st.markdown("### 📁 Data Upload")
    uploaded_file = st.file_uploader("Upload Instrument CSV", type=["csv"])
    if uploaded_file:
        raw_df = process_data(uploaded_file.getvalue())
        if raw_df is not None:
            st.markdown("---")
            st.subheader("📅 Global Filters")
            min_date, max_date = raw_df['Arrived_Date_Time'].min().date(), raw_df['Arrived_Date_Time'].max().date()
            sel_range = st.date_input("Date Range", [min_date, max_date])
            categories = raw_df['Discrimination'].unique().tolist()
            sel_cats = st.multiselect("Data Categories", categories, default=categories)

    st.sidebar.markdown("---")
    st.sidebar.caption("⚙️ **Engine Details**")
    st.sidebar.markdown("- **Adaptive Engine:** v3.4\n- **Compatibility:** cobas pro\n- **Status:** Validated")
    st.sidebar.markdown("---")
    st.sidebar.markdown("© 2026 **LabMesh.com**")

# --- Main App Area ---
if uploaded_file and raw_df is not None:
    mask = (raw_df['Arrived_Date_Time'].dt.date >= sel_range[0]) & (raw_df['Arrived_Date_Time'].dt.date <= sel_range[1]) & (raw_df['Discrimination'].isin(sel_cats))
    df = raw_df.loc[mask]

    tab_data, tab_analytics, tab_qc = st.tabs(["📄 Data View", "📊 Test Analytics", "🧪 Quality Control"])
    
    with tab_analytics:
        st.subheader("Instrument & Module Utilization")
        
        # 1. Module Logic and Capacity Metrics
        # Throughput mapping: (Max, Practical) per hour
        throughput_map = {"c 503": (1000, 800), "ISE": (900, 850), "e 801": (300, 275)}
        
        module_counts = df['Module'].value_counts().reset_index()
        module_counts.columns = ['Module_Name', 'Test_Count']
        
        st.markdown("#### ⚡ Module Efficiency Widgets")
        cols = st.columns(len(module_counts) if not module_counts.empty else 1)
        
        for i, row in module_counts.iterrows():
            m_name = row['Module_Name']
            count = row['Test_Count']
            
            # Identify core module type
            m_type = "Unknown"
            if "c 503" in m_name: m_type = "c 503"
            elif "ISE" in m_name: m_type = "ISE"
            elif "e 801" in m_name: m_type = "e 801"
            
            if m_type in throughput_map:
                t_max, t_prac = throughput_map[m_type]
                # Calculate utilization vs practical (assuming a 1-hour peak snapshot or scaled usage)
                util_prac = (count / t_prac) * 100
                cols[i].metric(label=f"Module: {m_name}", value=f"{count} Tests", delta=f"{util_prac:.1f}% Capacity Used", delta_color="inverse" if util_prac > 90 else "normal")
                cols[i].caption(f"Type: {m_type} | Max: {t_max}/hr")
            else:
                cols[i].metric(label=f"Module: {m_name}", value=f"{count} Tests")

        st.markdown("---")

        # 2. Arrival Patterns and Restored Charts
        st.write("#### 🕒 24-Hour Sample Arrival Pattern")
        pattern_df = df[df['Discrimination'].str.contains("Patient", na=False)].copy()
        if not pattern_df.empty:
            pattern_df['Hour'] = pattern_df['Arrived_Date_Time'].dt.hour
            pattern_df['Date'] = pattern_df['Arrived_Date_Time'].dt.strftime('%Y-%m-%d')
            h_counts = pattern_df.groupby(['Date', 'Hour'])['Sample_ID'].nunique().reset_index(name='Sample Count')
            fig_trend = px.line(h_counts, x='Hour', y='Sample Count', color='Date', markers=True, text='Sample Count')
            fig_trend.update_traces(textposition="top center")
            fig_trend.update_layout(xaxis=dict(tickmode='linear', range=[0, 23]))
            st.plotly_chart(fig_trend, use_container_width=True)

        st.markdown("---")
        c1, c2 = st.columns(2)
        with c1:
            st.write("#### 🧪 Test Volume by Parameter")
            st.plotly_chart(px.bar(df['Parameter'].value_counts().reset_index(), x='Parameter', y='count', color='Parameter'), use_container_width=True)
        with c2:
            st.write("#### 🚻 Gender Distribution")
            st.plotly_chart(px.pie(df, names='Gender', hole=0.4), use_container_width=True)

    # ... [Rest of tab_data and tab_qc code remains as previous version] ...
    with tab_data:
        st.dataframe(df, use_container_width=True)
    
    with tab_qc:
        q_df = df[df['Discrimination'].str.contains("QC", na=False)].copy()
        if not q_df.empty:
            st.write("#### 🕒 QC Run Matrix (24-Hour Scale)")
            q_df['HourFloat'] = q_df['Arrived_Date_Time'].dt.hour + q_df['Arrived_Date_Time'].dt.minute/60
            fig_qc_time = px.scatter(q_df, x='HourFloat', y='Parameter', color='Parameter')
            fig_qc_time.update_layout(xaxis=dict(tickmode='linear', range=[0, 24]))
            st.plotly_chart(fig_qc_time, use_container_width=True)
            st.write("#### 📋 QC Precision Statistics")
            q_df['Date'] = q_df['Arrived_Date_Time'].dt.date
            qc_stats = q_df.groupby(['Date', 'Parameter', 'Sample_ID'])['Result_Numeric'].agg(Runs='count', Mean='mean', SD='std').reset_index()
            qc_stats['CV%'] = ((qc_stats['SD'] / qc_stats['Mean']) * 100).round(2).map("{:.2f}%".format)
            st.dataframe(qc_stats, use_container_width=True)

else:
    st.title("Welcome to converterPRO")
    st.info("Please upload a cobas pro CSV file in the sidebar to view Module Utilization.")
