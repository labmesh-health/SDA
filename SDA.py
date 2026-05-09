import streamlit as st
import pandas as pd
import csv
import io
import plotly.express as px

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
            st.subheader("📅 Filters")
            min_date = raw_df['Arrived_Date_Time'].min().date()
            max_date = raw_df['Arrived_Date_Time'].max().date()
            sel_range = st.date_input("Date Range", [min_date, max_date])
            
            # Global toggle for Routine vs STAT vs QC
            categories = raw_df['Discrimination'].unique().tolist()
            sel_cats = st.multiselect("Visible Categories", categories, default=categories)

# --- Main App Area ---
if uploaded_file and raw_df is not None:
    # Filter Data
    mask = (raw_df['Arrived_Date_Time'].dt.date >= sel_range[0]) & \
           (raw_df['Arrived_Date_Time'].dt.date <= sel_range[1]) & \
           (raw_df['Discrimination'].isin(sel_cats))
    df = raw_df.loc[mask]

    # TAB STRUCTURE
    tab_data, tab_analytics, tab_qc = st.tabs(["📄 Data View", "📊 Test Analytics", "🧪 Quality Control"])
    
    with tab_data:
        st.subheader("Filtered Instrument Data")
        st.dataframe(df, use_container_width=True)
        st.download_button("📥 Export CSV", df.to_csv(index=False), "converted_data.csv")
            
    with tab_analytics:
        st.subheader("Instrument Workload Analytics")
        p_df = df[df['Discrimination'].str.contains("Patient", na=False)]
        
        # 24-Hour Arrival Pattern (Multiple Days)
        if not p_df.empty:
            st.write("#### 🕒 24-Hour Sample Arrival Pattern")
            # Prepare data for line chart
            pattern_df = p_df.copy()
            pattern_df['Hour'] = pattern_df['Arrived_Date_Time'].dt.hour
            pattern_df['Date'] = pattern_df['Arrived_Date_Time'].dt.strftime('%Y-%m-%d')
            
            # Group by Date and Hour to count unique Sample_IDs
            hourly_counts = pattern_df.groupby(['Date', 'Hour'])['Sample_ID'].nunique().reset_index(name='Sample Count')
            
            fig_trend = px.line(hourly_counts, x='Hour', y='Sample Count', color='Date',
                                markers=True, line_shape='spline',
                                labels={'Hour': 'Hour of Day (0-23)', 'Sample Count': 'Number of Samples'},
                                title="Arrival Volume by Hour")
            fig_trend.update_layout(xaxis=dict(tickmode='linear', tick0=0, dtick=1))
            st.plotly_chart(fig_trend, use_container_width=True)
            
            # Distribution of Tests
            st.markdown("---")
            c1, c2 = st.columns(2)
            with c1:
                st.write("#### 🧪 Test Volume by Parameter")
                st.plotly_chart(px.bar(p_df['Parameter'].value_counts().reset_index(), x='Parameter', y='count', color='Parameter'), use_container_width=True)
            with c2:
                st.write("#### 🚻 Gender Distribution")
                st.plotly_chart(px.pie(p_df, names='Gender', hole=0.4), use_container_width=True)
        else:
            st.warning("No Patient data available for the selected filters.")

    with tab_qc:
        st.subheader("Quality Control Monitoring")
        q_df = df[df['Discrimination'].str.contains("QC", na=False)]
        
        if not q_df.empty:
            k1, k2 = st.columns(2)
            k1.metric("Total QC Tests", len(q_df))
            k2.metric("Unique Controls", q_df['Sample_ID'].nunique())
            
            st.write("#### 📊 QC Result Distribution (Precision)")
            # Box plot to show stability/outliers for each parameter
            fig_qc = px.box(q_df, x='Parameter', y='Result_Numeric', color='Parameter',
                            points="all", title="QC Values Spread per Parameter")
            st.plotly_chart(fig_qc, use_container_width=True)
            
            st.write("#### 📅 QC Run Timeline")
            # Timeline of QC runs to check for frequency
            q_df['DateOnly'] = q_df['Arrived_Date_Time'].dt.date
            qc_timeline = q_df.groupby(['DateOnly', 'Parameter']).size().reset_index(name='Runs')
            fig_timeline = px.scatter(qc_timeline, x='DateOnly', y='Parameter', size='Runs', color='Parameter', title="QC Frequency Timeline")
            st.plotly_chart(fig_timeline, use_container_width=True)
        else:
            st.warning("No QC data available. Ensure 'QC (Control)' is selected in the sidebar.")

else:
    st.title("Welcome to converterPRO")
    st.info("Please upload a cobas pro CSV file in the sidebar to view Analytics and QC dashboards.")
