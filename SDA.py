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
        
        mappings = {
            "Gender": {"0": "Not entered", "1": "Male", "2": "Female"},
            "Discrimination": {"1": "Patient (Routine)", "2": "Patient (STAT)", "3": "QC (Control)"}
        }
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
            min_date = raw_df['Arrived_Date_Time'].min().date()
            max_date = raw_df['Arrived_Date_Time'].max().date()
            sel_range = st.date_input("Date Range", [min_date, max_date])
            
            categories = raw_df['Discrimination'].unique().tolist()
            sel_cats = st.multiselect("Visible Categories", categories, default=categories)

# --- Main App Area ---
if uploaded_file and raw_df is not None:
    # Applying Global Filters
    mask = (raw_df['Arrived_Date_Time'].dt.date >= sel_range[0]) & \
           (raw_df['Arrived_Date_Time'].dt.date <= sel_range[1]) & \
           (raw_df['Discrimination'].isin(sel_cats))
    df = raw_df.loc[mask]

    tab_data, tab_analytics, tab_qc = st.tabs(["📄 Data View", "📊 Test Analytics", "🧪 Quality Control"])
    
    with tab_data:
        st.subheader("Filtered Instrument Data")
        st.dataframe(df, use_container_width=True)
        st.download_button("📥 Export CSV", df.to_csv(index=False), "converted_data.csv")
            
    with tab_analytics:
        st.subheader("Instrument Workload Analytics")
        p_df = df[df['Discrimination'].str.contains("Patient", na=False)]
        
        if not p_df.empty:
            st.write("#### 🕒 24-Hour Sample Arrival Pattern")
            pattern_df = p_df.copy()
            pattern_df['Hour'] = pattern_df['Arrived_Date_Time'].dt.hour
            pattern_df['Date'] = pattern_df['Arrived_Date_Time'].dt.strftime('%Y-%m-%d')
            
            hourly_counts = pattern_df.groupby(['Date', 'Hour'])['Sample_ID'].nunique().reset_index(name='Sample Count')
            
            fig_trend = px.line(hourly_counts, x='Hour', y='Sample Count', color='Date',
                                markers=True, text='Sample Count', 
                                title="Daily Arrival Volume by Hour")
            fig_trend.update_traces(textposition="top center")
            fig_trend.update_layout(xaxis=dict(tickmode='linear', tick0=0, dtick=1, range=[0, 23]))
            st.plotly_chart(fig_trend, use_container_width=True)
            
            st.markdown("---")
            c1, c2 = st.columns(2)
            with c1:
                st.write("#### 🧪 Total Test Volume")
                st.plotly_chart(px.bar(p_df['Parameter'].value_counts().reset_index(), x='Parameter', y='count', color='Parameter'), use_container_width=True)
            with c2:
                st.write("#### 🚻 Gender Demographics")
                st.plotly_chart(px.pie(p_df, names='Gender', hole=0.4), use_container_width=True)
        else:
            st.warning("No Patient data selected.")

    with tab_qc:
        st.subheader("Quality Control Precision & Timing")
        q_df = df[df['Discrimination'].str.contains("QC", na=False)].copy()
        
        if not q_df.empty:
            # 1. QC Run Matrix (Timeline)
            st.write("#### 🕒 QC Run Matrix (24-Hour Scale)")
            q_df['Time'] = q_df['Arrived_Date_Time'].dt.strftime('%H:%M')
            q_df['HourFloat'] = q_df['Arrived_Date_Time'].dt.hour + q_df['Arrived_Date_Time'].dt.minute/60
            
            fig_qc_time = px.scatter(q_df, x='HourFloat', y='Parameter', color='Parameter',
                                     hover_data={'Time': True, 'HourFloat': False},
                                     title="Daily QC Execution Schedule",
                                     labels={'HourFloat': 'Time of Day (Hour)'})
            fig_qc_time.update_layout(xaxis=dict(tickmode='linear', tick0=0, dtick=1, range=[0, 24]))
            st.plotly_chart(fig_qc_time, use_container_width=True)

            st.markdown("---")
            
            # 2. QC Precision Statistics Table
            st.write("#### 📋 QC Precision Spread (Daily Summary)")
            q_df['Date'] = q_df['Arrived_Date_Time'].dt.date
            
            # Grouping and Aggregation
            qc_stats = q_df.groupby(['Date', 'Parameter', 'Sample_ID'])['Result_Numeric'].agg(
                Count='count',
                Mean='mean',
                SD='std'
            ).reset_index()
            
            # Calculate CV% (Coefficient of Variation)
            qc_stats['CV%'] = (qc_stats['SD'] / qc_stats['Mean']) * 100
            
            # Formatting for display
            qc_stats['Mean'] = qc_stats['Mean'].round(3)
            qc_stats['SD'] = qc_stats['SD'].round(3)
            qc_stats['CV%'] = qc_stats['CV%'].round(2).map("{:.2f}%".format)
            
            st.dataframe(qc_stats.sort_values(by=['Date', 'Parameter']), use_container_width=True)
            
            st.markdown("---")
            
            # 3. Precision Box Plot
            st.write("#### 📊 QC Result Distribution")
            st.plotly_chart(px.box(q_df, x='Parameter', y='Result_Numeric', color='Parameter', points="all"), use_container_width=True)
        else:
            st.warning("No QC data found.")

else:
    st.title("Welcome to converterPRO")
    st.info("System Ready. Please upload a cobas pro CSV file in the sidebar.")
