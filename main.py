import streamlit as st
import pandas as pd
import os
import datetime
from google import generativeai as genai
from PIL import Image
import json

# ==========================================
# 1. SETUP & CONFIGURATION
# ==========================================
st.set_page_config(page_title="Site Material Tracker", layout="wide")

UPLOAD_DIR = "stored_documents"
os.makedirs(UPLOAD_DIR, exist_ok=True)
DB_FILE = "material_ledger.csv"
TARGET_FILE = "project_targets.csv"

# Global Categories
MATERIAL_LIST = ["Cement", "Gypsum Board", "Partition Channel", "Ceiling Framing Material", "Tiles", "Marble", "Glazing", "Other"]
TARGET_MATERIALS = ["Cement", "Gypsum Board", "Partition Channel", "Ceiling Framing Material", "Tiles", "Marble", "Glazing"]

def load_ledger():
    if os.path.exists(DB_FILE):
        try:
            return pd.read_csv(DB_FILE)
        except Exception:
            pass
    return pd.DataFrame(columns=["Delivery Date", "Invoice No", "Supplier", "Material Type", "Quantity", "Unit", "MIR Ref No", "MIR Status", "Invoice File", "MIR File"])

def load_targets():
    if os.path.exists(TARGET_FILE):
        try:
            return pd.read_csv(TARGET_FILE).set_index("Material Type")["Target"].to_dict()
        except Exception:
            pass
    return {mat: 0.0 for mat in TARGET_MATERIALS}

ledger_df = load_ledger()
targets = load_targets()

# ==========================================
# 2. UPGRADED MULTI-ROW AI ENGINE (GEMINI)
# ==========================================
def extract_document_data(api_key, invoice_file, mir_file):
    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-2.5-flash')
        inv_img = Image.open(invoice_file)
        mir_img = Image.open(mir_file)
        
        prompt = f"""
        Analyze these construction documents: Document 1 (Invoice), Document 2 (Inspection Report - MIR).
        The invoice may contain multiple different material entries or items. Extract ALL items found.
        
        CRITICAL INSTRUCTION FOR MATERIAL TYPE MAPPING:
        You must map whatever item name is written on the document into one of these strict categories: {', '.join(MATERIAL_LIST)}.
        - If it mentions any variation of cement, map it to "Cement".
        - If it mentions drywall, plasterboard, ceiling board, map it to "Gypsum Board".
        - If it mentions studs, tracks, channels, map it to "Partition Channel" or "Ceiling Framing Material" depending on usage.
        - If it mentions porcelain, ceramic, vitrified tiles, map it to "Tiles".
        - Only use "Other" if it absolutely does not fit the main structural categories.

        Format your final response strictly as a JSON list of objects matching this exact template layout. Do not wrap in backticks or markdown:
        [
            {{
                "Delivery Date": "YYYY-MM-DD",
                "Invoice No": "string",
                "Supplier": "string",
                "Material Type": "One of the mapped options listed above",
                "Quantity": 0.0,
                "Unit": "string",
                "MIR Ref No": "string",
                "MIR Status": "Passed"
            }}
        ]
        """
        response = model.generate_content([prompt, inv_img, mir_img])
        clean_text = response.text.replace("```json", "").replace("```python", "").replace("```", "").strip()
        return json.loads(clean_text)
    except Exception as e:
        st.error(f"AI multi-row parsing failed: {e}. You can append entries using the fallback template log below.")
        return None

# ==========================================
# 3. USER INTERFACE LAYOUT
# ==========================================
st.title("🏗️ Smart Site Material Tracker & Reconciler")
tab1, tab2, tab3 = st.tabs(["📋 Document Inwarding", "📊 Master Ledger & Reconciliation", "📈 Project Analytics"])

# ------------------------------------------
# TAB 1: DOCUMENT INWARDING (UPGRADED)
# ------------------------------------------
with tab1:
    st.header("Scan & Upload Site Documents")
    api_key = st.text_input("Enter Gemini API Key to enable AI scanning:", type="password")
    
    col1, col2 = st.columns(2)
    with col1:
        inv_upload = st.file_uploader("Upload Scanned Invoice (Image/PNG/JPG)", type=["png", "jpg", "jpeg"])
    with col2:
        mir_upload = st.file_uploader("Upload Material Inspection Report (Image/PNG/JPG)", type=["png", "jpg", "jpeg"])
        
    if st.button("🚀 Analyze Documents with AI"):
        if not api_key:
            st.warning("Please provide an API Key first!")
        elif inv_upload and mir_upload:
            with st.spinner("AI analyzing all invoice line items..."):
                extracted_list = extract_document_data(api_key, inv_upload, mir_upload)
                if extracted_list:
                    st.session_state['parsed_items'] = extracted_list
                    st.success(f"Successfully extracted {len(extracted_list)} line items from your document!")
        else:
            st.error("Please upload both the Invoice and the MIR file.")

    # Live Preview and Verification Spreadsheet Table
    if 'parsed_items' in st.session_state:
        st.subheader("📝 Step 2: Review and Edit Extracted Items")
        st.info("Double-click any cell below if you need to manually adjust names, categories, or quantities before final saving.")
        
        # Turn data into an interactive editable table layout
        preview_df = pd.DataFrame(st.session_state['parsed_items'])
        
        # Ensure column configurations look clean
        edited_df = st.data_editor(
            preview_df,
            column_config={
                "Material Type": st.column_config.SelectboxColumn("Material Category", options=MATERIAL_LIST, required=True),
                "Delivery Date": st.column_config.DateColumn("Date", required=True),
                "Quantity": st.column_config.NumberColumn("Qty", min_value=0.0, format="%.2f")
            },
            num_rows="dynamic",
            key="items_editor"
        )
        
        if st.button("💾 Save All Rows to Ledger"):
            if inv_upload and mir_upload:
                timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
                inv_path = os.path.join(UPLOAD_DIR, f"{timestamp}_INV_{inv_upload.name}")
                mir_path = os.path.join(UPLOAD_DIR, f"{timestamp}_MIR_{mir_upload.name}")
                
                with open(inv_path, "wb") as f: f.write(inv_upload.getbuffer())
                with open(mir_path, "wb") as f: f.write(mir_upload.getbuffer())
                
                # Append files pathways to every verified row item line
                edited_df["Invoice File"] = inv_path
                edited_df["MIR File"] = mir_path
                
                # Merge into permanent records log csv
                updated_df = pd.concat([ledger_df, edited_df], ignore_index=True)
                updated_df.to_csv(DB_FILE, index=False)
                
                st.success("All items successfully logged! Checked items are now cleared.")
                del st.session_state['parsed_items']
                st.rerun()

# ------------------------------------------
# TAB 2: MASTER LEDGER & RECONCILIATION
# ------------------------------------------
with tab2:
    st.header("Site Material Inventory Ledger Log")
    if not ledger_df.empty:
        col_f1, col_f2 = st.columns(2)
        with col_f1:
            f_mat = st.multiselect("Filter by Material Category", MATERIAL_LIST, default=MATERIAL_LIST)
        with col_f2:
            unique_suppliers = ledger_df["Supplier"].dropna().unique().tolist()
            f_vendor = st.multiselect("Filter by Supplier Vendor", unique_suppliers, default=unique_suppliers)
            
        filtered_df = ledger_df[(ledger_df["Material Type"].isin(f_mat)) & (ledger_df["Supplier"].isin(f_vendor))]
        st.subheader("Active Records View")
        
        for index, row in filtered_df.iterrows():
            with st.expander(f"📅 {row['Delivery Date']} | {row['Material Type']} - {row['Quantity']} {row['Unit']} (Inv: {row['Invoice No']})"):
                c1, c2, c3, c4 = st.columns(4)
                c1.write(f"**Supplier:** {row['Supplier']}")
                c2.write(f"**MIR Status:** {row['MIR Status']} ({row['MIR Ref No']})")
                if os.path.exists(str(row["Invoice File"])):
                    with open(str(row["Invoice File"]), "rb") as file_inv:
                        c3.download_button(label="📥 Download Invoice", data=file_inv.read(), file_name=os.path.basename(str(row["Invoice File"])), key=f"inv_{index}")
                if os.path.exists(str(row["MIR File"])):
                    with open(str(row["MIR File"]), "rb") as file_mir:
                        c4.download_button(label="📥 Download MIR", data=file_mir.read(), file_name=os.path.basename(str(row["MIR File"])), key=f"mir_{index}")
                    
        st.download_button(label="📊 Export Full Ledger Log to CSV", data=filtered_df.to_csv(index=False), file_name="site_reconciliation_report.csv", mime="text/csv")
    else:
        st.info("No delivery records compiled inside storage records yet.")

# ------------------------------------------
# TAB 3: PROJECT ANALYTICS (STAY FLATTENED)
# ------------------------------------------
with tab3:
    st.header("Material Procurement Target Tracking Matrix")
    st.subheader("Configure Project Structural Requirements Estimations")
    
    inputs = {}
    inputs["Cement"] = st.number_input("Total Cement Required:", min_value=0.0, value=float(targets.get("Cement", 0.0)), key="in_cement")
    inputs["Gypsum Board"] = st.number_input("Total Gypsum Board Required:", min_value=0.0, value=float(targets.get("Gypsum Board", 0.0)), key="in_gypsum")
