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
        # Dynamic indexing to support different SW versions
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
    
    st.markdown("---")
    st.subheader("⚙️ Session Details")
    st.write("**System:** Adaptive Engine v3.1")
    st.write("**Compatibility:** cobas pro (All SW Versions)")
    
    if uploaded_file:
        st.success("File uploaded successfully!")
        if st.button("Clear Session"):
            st.rerun()

# --- Main App Area ---
if uploaded_file:
    df_raw = process_data(uploaded_file.getvalue())
    
    if df_raw is not None:
        # Active Sidebar Filters
        with st.sidebar:
            st.markdown("---")
            st.subheader("📅 Data Filters")
            min_date = df_raw['Arrived_Date_Time'].min().date()
            max_date = df_raw['Arrived_Date_Time'].max().date()
            sel_range = st.date_input("Filter by Date", [min_date, max_date])
            
            categories = df_raw['Discrimination'].unique().tolist()
            sel_cats = st.multiselect("Data Categories", categories, default=categories)

        # Apply Filters
        mask = (df_raw['Arrived_Date_Time'].dt.date >= sel_range[0]) & \
               (df_raw['Arrived_Date_Time'].dt.date <= sel_range[1]) & \
               (df_raw['Discrimination'].isin(sel_cats))
        df = df_raw.loc[mask]

        tab1, tab2 = st.tabs(["📄 Raw Data View", "📊 Analytics Dashboard"])
        
        with tab1:
            st.dataframe(df, use_container_width=True)
            st.download_button("📥 Download Filtered Data", df.to_csv(index=False), "processed_data.csv")
            
        with tab2:
            st.subheader("Performance KPIs")
            k1, k2, k3 = st.columns(3)
            p_df = df[df['Discrimination'].str.contains("Patient", na=False)]
            q_df = df[df['Discrimination'].str.contains("QC", na=False)]
            
            k1.metric("Total Rows", len(df))
            k2.metric("Patient Records", len(p_df))
            k3.metric("QC Samples", len(q_df))
            
            c1, c2 = st.columns(2)
            with c1:
                st.plotly_chart(px.bar(p_df['Parameter'].value_counts().reset_index(), x='Parameter', y='count', title="Test Volume"), use_container_width=True)
            with c2:
                st.plotly_chart(px.box(q_df, x='Parameter', y='Result_Numeric', title="QC Stability"), use_container_width=True)
else:
    # --- Landing Page (Prevents Blank Screen) ---
    st.title("Welcome to converterPRO")
    st.info("System Ready. Please upload a file in the sidebar to begin analysis.")
    
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("""
        ### 🚀 How to use:
        1. **Upload:** Drag your cobas pro CSV into the sidebar.
        2. **Filter:** Use the dynamic date pickers to narrow your range.
        3. **Analyze:** Switch to the **Dashboard** tab for QC vs Patient metrics.
        4. **Export:** Download the unpivoted data for external LIS reporting.
        """)
    with col2:
        # Placeholder for visual guidance
        st.image("https://images.unsplash.com/photo-1576086213369-97a306d36557?auto=format&fit=crop&q=80&w=500", caption="Validated for Clinical Laboratory Use")
