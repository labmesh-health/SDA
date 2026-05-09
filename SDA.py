import streamlit as st
import pandas as pd
import csv
import io
import plotly.express as px
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

        fixed_before = header_row[:draw_idx + 1]
        comment_cols = header_row[draw_idx + 1 : cup_idx]
        fixed_after = header_row[cup_idx : start_col]
        
        standard_block_headers = list(block_template)
        if module_sub_idx != -1: standard_block_headers[module_sub_idx] = "Module"
        
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
            min_date, max_date = raw_df['Arrived_Date_Time'].min().date(), raw_df['Arrived_Date_Time'].max().date()
            sel_range = st.date_input("Date Range", [min_date, max_date])
            sel_cats = st.multiselect("Categories", raw_df['Discrimination'].unique().tolist(), default=raw_df['Discrimination'].unique().tolist())
    st.sidebar.markdown("---")
    st.sidebar.markdown("© 2026 **LabMesh.com** | v3.6")

# --- Main App ---
if uploaded_file and raw_df is not None:
    mask = (raw_df['Arrived_Date_Time'].dt.date >= sel_range[0]) & (raw_df['Arrived_Date_Time'].dt.date <= sel_range[1]) & (raw_df['Discrimination'].isin(sel_cats))
    df = raw_df.loc[mask]

    tab_data, tab_analytics, tab_qc = st.tabs(["📄 Raw Data", "📊 Test Analytics", "🧪 Quality Control"])
    
    with tab_data:
        st.subheader("Raw Data Table")
        st.dataframe(df, use_container_width=True) # RESTORED TABLE
        st.download_button("📥 Download Full CSV", df.to_csv(index=False), "raw_export.csv")

    with tab_analytics:
        st.subheader("Module Peak Utilization")
        if 'Module' in df.columns:
            # Capacity Mapping (Max, Practical)
            caps = {"c 503": (1000, 800), "ISE": (900, 850), "e 801": (300, 275)}
            
            # 1. Normalize Module Names (Group e801-1, e801-2 into e 801)
            util_df = df.copy()
            util_df['Normalized_Module'] = util_df['Module'].apply(lambda x: next((k for k in caps if k in str(x)), "Other"))
            util_df['Hour'] = util_df['Arrived_Date_Time'].dt.hour
            util_df['Date'] = util_df['Arrived_Date_Time'].dt.date

            # 2. Calculate tests per hour per module
            hourly_util = util_df.groupby(['Date', 'Hour', 'Normalized_Module']).size().reset_index(name='Tests')
            
            cols = st.columns(len(caps))
            for idx, (m_type, values) in enumerate(caps.items()):
                m_max, m_prac = values
                # Get the peak hour across all days
                m_data = hourly_util[hourly_util['Normalized_Module'] == m_type]
                if not m_data.empty:
                    peak_val = m_data['Tests'].max()
                    util_pct = (peak_val / m_prac) * 100
                    cols[idx].metric(f"{m_type} Peak", f"{peak_val} T/Hr", f"{util_pct:.1f}% of Practical")
                    cols[idx].caption(f"Max: {m_max} | Practical: {m_prac}")
                else:
                    cols[idx].metric(f"{m_type} Peak", "0 T/Hr", "No Data")

        st.markdown("---")
        st.write("#### 🕒 24-Hour Arrival Pattern (Patient Samples)")
        p_df = df[df['Discrimination'].str.contains("Patient", na=False)].copy()
        if not p_df.empty:
            p_df['Hour'] = p_df['Arrived_Date_Time'].dt.hour
            p_df['Date'] = p_df['Arrived_Date_Time'].dt.strftime('%Y-%m-%d')
            h_counts = p_df.groupby(['Date', 'Hour'])['Sample_ID'].nunique().reset_index(name='Samples')
            fig = px.line(h_counts, x='Hour', y='Samples', color='Date', markers=True, text='Samples')
            fig.update_layout(xaxis=dict(tickmode='linear', range=[0, 23]))
            st.plotly_chart(fig, use_container_width=True)

        c1, c2 = st.columns(2)
        with c1:
            st.plotly_chart(px.bar(df['Parameter'].value_counts().reset_index(), x='Parameter', y='count', title="Test Volume"), use_container_width=True)
        with c2:
            st.plotly_chart(px.pie(df, names='Gender', hole=0.4, title="Demographics"), use_container_width=True)

    with tab_qc:
        q_df = df[df['Discrimination'].str.contains("QC", na=False)].copy()
        if not q_df.empty:
            st.write("#### 🕒 QC Execution Timeline")
            q_df['HourFloat'] = q_df['Arrived_Date_Time'].dt.hour + q_df['Arrived_Date_Time'].dt.minute/60
            fig_qc = px.scatter(q_df, x='HourFloat', y='Parameter', color='Parameter')
            fig_qc.update_layout(xaxis=dict(tickmode='linear', range=[0, 24]))
            st.plotly_chart(fig_qc, use_container_width=True)
            
            st.write("#### 📋 Precision Table")
            q_df['Date'] = q_df['Arrived_Date_Time'].dt.date
            qc_stats = q_df.groupby(['Date', 'Parameter', 'Sample_ID'])['Result_Numeric'].agg(Runs='count', Mean='mean', SD='std').reset_index()
            qc_stats['CV%'] = ((qc_stats['SD'] / qc_stats['Mean']) * 100).round(2).map("{:.2f}%".format)
            st.dataframe(qc_stats, use_container_width=True)
else:
    st.title("Welcome to converterPRO")
    st.info("System Ready. Please upload a file in the sidebar.")
