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
                    "Discrimination": {"1": "Patient (Routine)", "2": "Patient (STAT)", "3": "QC (Control)"},
                    "Run": {"1": "1st run", "2": "Rerun"}}
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
    st.sidebar.markdown("© 2026 **LabMesh.com** | v4.6")

# --- Main App ---
if uploaded_file and raw_df is not None:
    mask = (raw_df['Arrived_Date_Time'].dt.date >= sel_range[0]) & (raw_df['Arrived_Date_Time'].dt.date <= sel_range[1]) & (raw_df['Discrimination'].isin(sel_cats))
    df = raw_df.loc[mask]

    tabs = st.tabs(["📄 Raw Data", "📊 Test Analytics", "🧪 Quality Control", "⚠️ Error Detection", "🧠 Operational Insights"])
    
    with tabs[0]:
        st.dataframe(df, use_container_width=True)
        st.download_button("📥 Export CSV", df.to_csv(index=False), "export.csv")

    with tabs[1]:
        st.subheader("Module Throughput & Peak Capacity")
        if 'Module' in df.columns and 'Sampling_Date_Time' in df.columns:
            caps = {"c 503": (1000, 800), "ISE": (900, 850), "e 801": (300, 275)}
            util_df = df.copy().dropna(subset=['Sampling_Date_Time'])
            util_df['Norm_Mod'] = util_df['Module'].apply(lambda x: next((k for k in caps if k in str(x)), "Other"))
            util_df['S_Hour'] = util_df['Sampling_Date_Time'].dt.hour
            util_df['S_Date'] = util_df['Sampling_Date_Time'].dt.strftime('%Y-%m-%d')
            hourly_util = util_df.groupby(['S_Date', 'S_Hour', 'Norm_Mod']).size().reset_index(name='Tests')
            
            cols = st.columns(len(caps))
            peak_stats = []
            for idx, (m_type, values) in enumerate(caps.items()):
                m_max, m_prac = values
                peak_val = hourly_util[hourly_util['Norm_Mod'] == m_type]['Tests'].max() if m_type in hourly_util['Norm_Mod'].values else 0
                cols[idx].metric(f"{m_type} Peak", f"{peak_val} T/Hr", f"{((peak_val/m_prac)*100):.1f}% Capacity" if m_prac > 0 else "0%")
                peak_stats.append({'Module': m_type, 'Peak': peak_val, 'Practical': m_prac, 'Theoretical': m_max})

            st.write("#### 📈 Module Throughput Trends (Line Graph)")
            sel_mod_view = st.selectbox("Select Module to View Hourly Performance", hourly_util['Norm_Mod'].unique().tolist())
            st.plotly_chart(px.line(hourly_util[hourly_util['Norm_Mod'] == sel_mod_view], x='S_Hour', y='Tests', color='S_Date', markers=True, text='Tests').update_layout(xaxis=dict(tickmode='linear', range=[0, 23])), use_container_width=True)

            fig_peak = go.Figure()
            fig_peak.add_trace(go.Bar(x=[d['Module'] for d in peak_stats], y=[d['Peak'] for d in peak_stats], marker_color='#0b41cd', text=[d['Peak'] for d in peak_stats], textposition='auto'))
            for i, d in enumerate(peak_stats):
                fig_peak.add_shape(type="line", x0=i-0.4, y0=d['Practical'], x1=i+0.4, y1=d['Practical'], line=dict(color="orange", width=3, dash="dash"))
                fig_peak.add_shape(type="line", x0=i-0.4, y0=d['Theoretical'], x1=i+0.4, y1=d['Theoretical'], line=dict(color="red", width=3))
            st.plotly_chart(fig_peak, use_container_width=True)

        st.markdown("---")
        p_df = df[df['Discrimination'].str.contains("Patient", na=False)].copy()
        if not p_df.empty:
            st.write("#### 🕒 24-Hour Sample Arrival Pattern")
            p_df['Hour'] = p_df['Arrived_Date_Time'].dt.hour
            p_df['Date'] = p_df['Arrived_Date_Time'].dt.strftime('%Y-%m-%d')
            h_counts = p_df.groupby(['Date', 'Hour'])['Sample_ID'].nunique().reset_index(name='Samples')
            st.plotly_chart(px.line(h_counts, x='Hour', y='Samples', color='Date', markers=True, text='Samples').update_layout(xaxis=dict(tickmode='linear', range=[0, 23])), use_container_width=True)

        c1, c2 = st.columns(2)
        with c1: st.plotly_chart(px.bar(df['Parameter'].value_counts().reset_index(), x='Parameter', y='count', title="Test Volume"), use_container_width=True)
        with c2: st.plotly_chart(px.pie(df, names='Gender', hole=0.4, title="Demographics"), use_container_width=True)

    with tabs[4]:
        st.subheader("🧠 Prescriptive Performance Insights")
        i_col1, i_col2 = st.columns(2)
        with i_col1:
            st.info("📊 **Throughput Strategy**")
            for d in peak_stats:
                peak, prac, m_name = d['Peak'], d['Practical'], d['Module']
                if peak > d['Theoretical']:
                    st.error(f"⚠️ **Critical Overload ({m_name}):** Peak exceeded hardware max. Immediate review required.")
                elif peak > prac:
                    st.warning(f"🟠 **Peak Stress ({m_name}):** Exceeded practical limit. **Suggestion:** Optimize sample distribution by loading smaller, consistent batches.")
                elif peak > (prac * 0.85):
                    st.write(f"✅ **{m_name} Efficient Usage:** High utilization detected.")

        with i_col2:
            st.info("⚖️ **Assay Mapping & Load Balancing**")
            if 'Module' in df.columns:
                mod_counts = df['Module'].value_counts()
                # Search for twin sub-modules (e.g., e 801-1 and e 801-2)
                for base in ["e 801", "c 503"]:
                    twins = [m for m in mod_counts.index if base in str(m)]
                    if len(twins) > 1:
                        v1, v2 = mod_counts[twins[0]], mod_counts[twins[1]]
                        if (max(v1,v2) / min(v1,v2)) > 1.25:
                            st.warning(f"⚖️ **Internal Skew ({base}):** Uneven workload between sub-modules. **Suggestion:** Review **Assay Mapping** in instrument settings. Ensure high-volume assays are assigned to both modules for automatic distribution.")
                        else:
                            st.write(f"✅ **{base} Balancing:** Internal assay distribution is well-optimized.")

        st.markdown("---")
        st.write("#### 🔄 Quality & Rerun Analysis")
        r_rate = (len(df[df['Run'] == 'Rerun']) / len(df) * 100) if len(df) > 0 else 0
        if r_rate > 5: st.error(f"🔄 **High Rerun Rate ({r_rate:.1f}%):** Suggests reagent or calibration drift.")
        else: st.write(f"✅ **Rerun Rate:** Healthy at {r_rate:.1f}%.")

    with tabs[2]:
        st.subheader("QC Timing & Precision")
        q_df = df[df['Discrimination'].str.contains("QC", na=False)].copy()
        if not q_df.empty:
            q_df['HourFloat'] = q_df['Arrived_Date_Time'].dt.hour + q_df['Arrived_Date_Time'].dt.minute/60
            st.plotly_chart(px.scatter(q_df, x='HourFloat', y='Parameter', color='Parameter').update_layout(xaxis=dict(tickmode='linear', range=[0, 24])), use_container_width=True)
            q_df['Date'] = q_df['Arrived_Date_Time'].dt.date
            qc_stats = q_df.groupby(['Date', 'Parameter', 'Sample_ID'])['Result_Numeric'].agg(Runs='count', Mean='mean', SD='std').reset_index()
            qc_stats['CV%'] = ((qc_stats['SD'] / qc_stats['Mean']) * 100).round(2).map("{:.2f}%".format)
            st.dataframe(qc_stats, use_container_width=True)
            sel_qc_mod = st.multiselect("Filter Stability Plot by Module", q_df['Module'].unique().tolist(), default=q_df['Module'].unique().tolist())
            st.plotly_chart(px.box(q_df[q_df['Module'].isin(sel_qc_mod)], x='Parameter', y='Result_Numeric', color='Parameter', title="Filtered Stability Plot"), use_container_width=True)

    with tabs[3]:
        st.subheader("Error Analytics")
        if 'Data_Alarm' in df.columns:
            error_df = df[df['Data_Alarm'].str.strip() != ""].copy()
            if not error_df.empty:
                top_alarms = error_df.groupby(['Module', 'Data_Alarm']).size().reset_index(name='Count').sort_values('Count', ascending=False).head(20)
                st.plotly_chart(px.bar(top_alarms, x='Data_Alarm', y='Count', color='Module', text='Count'), use_container_width=True)

else:
    st.title("Welcome to converterPRO")
    st.info("System Ready. Please upload a file in the sidebar.")
