import streamlit as st
import pandas as pd
import csv
import io
import plotly.express as px

# --- Adaptive Core Processing Function ---
@st.cache_data
def process_roche_csv_adaptive(file_bytes):
    content = file_bytes.decode("utf-8", errors="replace")
    reader = csv.reader(io.StringIO(content))
    raw_data = list(reader)

    if len(raw_data) < 2:
        raise ValueError("CSV format invalid: Missing headers.")

    row0 = raw_data[0]
    header_row = raw_data[1]

    # --- DYNAMIC ANCHOR DETECTION ---
    try:
        # Find critical markers
        draw_idx = header_row.index("Drawing_Date_Time")
        cup_idx = header_row.index("Sample_Cup")
        start_col = header_row.index("Result") # First result block starts here
        
        # Determine block size (8 vs 11)
        is_11_col = "EMF1" in header_row
        block_size = 11 if is_11_col else 8
        
        # Determine columns names for the block
        # We take the column names from the first block to be safe
        block_columns = header_row[start_col : start_col + block_size]
    except ValueError as e:
        raise ValueError(f"Missing required column in CSV: {e}")

    # --- COMPOSE HEADERS ---
    # Everything before comments
    fixed_before = header_row[:draw_idx + 1]
    # Comments (everything between date and cup)
    comment_cols = header_row[draw_idx + 1 : cup_idx]
    # Metadata between cup and results (Operator, Pre-dilution, etc.)
    fixed_after = header_row[cup_idx : start_col]
    
    final_headers = fixed_before + comment_cols + fixed_after + ["ACN code", "Parameter"] + block_columns

    # --- TRANSFORMATION LOGIC ---
    blocks = []
    # Loop through columns in increments of block_size
    for col in range(start_col, len(header_row), block_size):
        if col + block_size <= len(header_row):
            # Extract ACN and Parameter from Row 0
            # Usually row0[col] is ACN, row0[col+1] is Name
            acn = row0[col] if col < len(row0) else ""
            param = row0[col+1] if col+1 < len(row0) else ""
            
            for row_idx in range(2, len(raw_data)):
                row_vals = raw_data[row_idx]
                if len(row_vals) <= col: continue
                
                assay_slice = row_vals[col : col + block_size]
                
                # Only keep rows where a result actually exists in this block
                if any(val.strip() for val in assay_slice):
                    # Combine static metadata + assay specific data
                    meta_before = row_vals[:draw_idx + 1]
                    meta_cmts = row_vals[draw_idx + 1 : cup_idx]
                    meta_after = row_vals[cup_idx : start_col]
                    
                    # Pad slices if row is short
                    meta_cmts += [""] * (len(comment_cols) - len(meta_cmts))
                    meta_after += [""] * (len(fixed_after) - len(meta_after))
                    assay_slice += [""] * (block_size - len(assay_slice))
                    
                    new_row = meta_before + meta_cmts + meta_after + [acn, param] + assay_slice
                    blocks.append(new_row)
    
    df = pd.DataFrame(blocks, columns=final_headers)
    
    # Cleaning and Mapping (Adaptive to presence of columns)
    if 'Arrived_Date_Time' in df.columns:
        df['Arrived_Date_Time'] = pd.to_datetime(df['Arrived_Date_Time'], errors='coerce')
    
    df['Result_Numeric'] = pd.to_numeric(df['Result'], errors='coerce') if 'Result' in df.columns else None

    # Mappings
    map_dict = {
        "Gender": {"0": "Not entered", "1": "Male", "2": "Female"},
        "Discrimination": {"1": "Patient (Routine)", "2": "Patient (STAT)", "3": "QC (Control)"}
    }
    for col, mapping in map_dict.items():
        if col in df.columns:
            df[col] = df[col].astype(str).map(mapping).fillna(df[col])
            
    return df
