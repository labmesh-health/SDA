import streamlit as st
import pandas as pd
import csv
import io

# --- Page Configuration ---
st.set_page_config(page_title="converterPRO", page_icon="💡", layout="wide")
st.title("💡 converterPRO - Instrument Data Formatter")

# --- Core Processing Function (Replicating GAS Logic) ---
@st.cache_data
def process_roche_csv(file_bytes):
    # Decode and read CSV using standard csv library to handle irregular headers securely
    content = file_bytes.decode("utf-8", errors="replace")
    reader = csv.reader(io.StringIO(content))
    raw_data = list(reader)

    if len(raw_data) < 2:
        raise ValueError("CSV must have at least two rows (one for ACN codes, one for headers).")

    row0 = raw_data[0]
    header_row = raw_data[1]

    # Find key column indices for slicing
    try:
        draw_idx = header_row.index("Drawing_Date_Time")
        cup_idx = header_row.index("Sample_Cup")
    except ValueError as e:
        raise ValueError("Missing required columns like 'Drawing_Date_Time' or 'Sample_Cup'. Please check the CSV format.")

    # 1. & 2. Fixed columns and dynamic comments
    fixed_before = header_row[:draw_idx + 1]
    comment_cols = header_row[draw_idx + 1 : cup_idx]
    fixed_after = header_row[cup_idx : cup_idx + 3]

    # 3. Block Structure Detection (8 vs 11 columns)
    is_11_col = "EMF1" in header_row and "EMF2" in header_row and "EMF3" in header_row
    block_size = 11 if is_11_col else 8
    
    block_columns_8 = ["Result", "Unit", "Data_Alarm", "Result_Message", "Sample_Volume", "AU", "Sampling_Date_Time", "Reagent_Priority"]
    block_columns = block_columns_8 + ["EMF1", "EMF2", "EMF3"] if is_11_col else block_columns_8

    # 4. Compose final headers
    final_headers = fixed_before + comment_cols + fixed_after + ["ACN code", "Parameter"] + block_columns

    blocks = []
    
    # 5. Data Transformation (Unpivoting Loop)
    start_col = cup_idx + 3
    for col in range(start_col, len(header_row), block_size):
        if col + block_size - 1 < len(header_row):
            part1 = row0[col] if col < len(row0) else ""
            part2 = row0[col + 1] if col + 1 < len(row0) else ""
            
            for row_idx in range(2, len(raw_data)):
                row_data = raw_data[row_idx]
                if len(row_data) <= col: continue # Skip short rows
                
                assay_data = row_data[col : col + block_size]
                # Pad in case the row ends prematurely
                assay_data += [""] * (block_size - len(assay_data))
                
                # If there's any data in this block, keep the row
                if any(val.strip() != "" for val in assay_data):
                    fb = row_data[:draw_idx + 1]
                    cmts = row_data[draw_idx + 1 : cup_idx]
                    fa = row_data[cup_idx : cup_idx + 3]
                    
                    new_row = fb + cmts + fa + [part1, part2] + assay_data
                    blocks.append(new_row)
                    
    df = pd.DataFrame(blocks, columns=final_headers)

    # 6. Apply Code Mappings
    mappings = {
        "Discrimination": {"1": "Routine", "2": "STAT", "3": "QC"},
        "Run": {"1": "1st run", "2": "Rerun"},
        "Sample_Type": {
            "0": "Multi-sample type", "1": "Serum/Plasma", "2": "Urine", "3": "CSF",
            "4": "Supernatant", "5": "Others", "6": "Whole blood", "7": "Oral fluid",
            "8": "Hemolysate", "9": "Amniotic Fluid", "10": "Processed Stool",
            "11": "Plasma", "12": "Serum"
        },
        "Gender": {"0": "Not entered", "1": "Male", "2": "Female"},
        "Sample_Cup": {"1": "Normal Sample cup", "2": "Micro Sample cup"},
        "Pre_Dilution": {"0": "Not selected or Off", "1": "Selected or On"}
    }
    
    for col_name, mapping in mappings.items():
        if col_name in df.columns:
            # Map values, keeping the original if it doesn't exist in the dictionary
            df[col_name] = df[col_name].astype(str).map(mapping).fillna(df[col_name])
            
    return df

# --- UI Layout ---
# Setup Tabs
tab1, tab2 = st.tabs(["📄 Raw Data", "📊 Dashboard (Phase 2)"])

with tab1:
    st.markdown("### Upload Instrument Output File")
    uploaded_file = st.file_uploader("Upload CSV File (e.g., 030526.csv)", type=["csv"])

    if uploaded_file is not None:
        try:
            with st.spinner("Processing data..."):
                file_bytes = uploaded_file.getvalue()
                processed_df = process_roche_csv(file_bytes)
            
            st.success(f"✅ Successfully processed! Found **{processed_df.shape[0]} rows** and **{processed_df.shape[1]} columns**.")
            
            # Display DataFrame
            st.dataframe(processed_df, use_container_width=True)

            # Download Button
            csv_export = processed_df.to_csv(index=False).encode('utf-8')
            st.download_button(
                label="📥 Download Formatted CSV",
                data=csv_export,
                file_name=f"Processed_{uploaded_file.name}",
                mime="text/csv",
                type="primary"
            )

        except Exception as e:
            st.error(f"Error processing file: {e}")
    else:
        st.info("Please upload a file to begin.")

with tab2:
    st.info("The Dashboard module will be built here once the Raw Data output is verified!")