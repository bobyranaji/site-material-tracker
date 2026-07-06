import streamlit as st
import pandas as pd
import os
import datetime
from google import generativeai as genai
from PIL import Image

# ==========================================
# 1. SETUP & CONFIGURATION
# ==========================================
st.set_page_config(page_title="Site Material Tracker", layout="wide")

# Create folders to store database and uploaded documents
UPLOAD_DIR = "stored_documents"
os.makedirs(UPLOAD_DIR, exist_ok=True)
DB_FILE = "material_ledger.csv"
TARGET_FILE = "project_targets.csv"

# Material Choices Layout
MATERIAL_LIST = ["Cement", "Gypsum Board", "Partition Channel", "Ceiling Framing Material", "Tiles", "Marble", "Glazing", "Other"]

# Load Data Helpers
def load_ledger():
    if os.path.exists(DB_FILE):
        return pd.read_csv(DB_FILE)
    return pd.DataFrame(columns=["Delivery Date", "Invoice No", "Supplier", "Material Type", "Quantity", "Unit", "MIR Ref No", "MIR Status", "Invoice File", "MIR File"])

def load_targets():
    if os.path.exists(TARGET_FILE):
        return pd.read_csv(TARGET_FILE).set_index("Material Type")["Target"].to_dict()
    return {mat: 0.0 for mat in MATERIAL_LIST if mat != "Other"}

# Initialize Data
ledger_df = load_ledger()
targets = load_targets()

# ==========================================
# 2. AI EXTRACTION ENGINE (GEMINI)
# ==========================================
def extract_document_data(api_key, invoice_file, mir_file):
    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-2.5-flash')
        
        # Load images for Gemini processing
        inv_img = Image.open(invoice_file)
        mir_img = Image.open(mir_file)
        
        prompt = f"""
        Analyze these two construction site documents: 
        Document 1 is a Material Delivery Invoice.
        Document 2 is a Material Inspection Report (MIR).
        
        Extract the following fields accurately. Pick the Material Type strictly from this list: {', '.join(MATERIAL_LIST)}.
        Format your response EXACTLY as a Python dictionary, matching this format precisely:
        {{
            "Delivery Date": "YYYY-MM-DD",
            "Invoice No": "string",
            "Supplier": "string",
            "Material Type": "string",
            "Quantity": float_number,
            "Unit": "string",
            "MIR Ref No": "string",
            "MIR Status": "Passed or Failed"
        }}
        Provide only the clean dictionary structure, no markdown markdown formatting.
        """
        
        response = model.generate_content([prompt, inv_img, mir_img])
        # Clean up response string to evaluate cleanly
        clean_text = response.text.replace("```python", "").replace("```json", "").replace("```", "").strip()
        return eval(clean_text)
    except Exception as e:
        st.error(f"AI parsing failed: {e}. Please fill out details manually below.")
        return None

# ==========================================
# 3. USER INTERFACE NAVIGATION
# ==========================================
st.title("🏗️ Smart Site Material Tracker & Reconciler")
tab1, tab2, tab3 = st.tabs(["📋 Document Inwarding", "📊 Master Ledger & Reconciliation", "📈 Project Analytics"])

# ------------------------------------------
# TAB 1: DOCUMENT INWARDING
# ------------------------------------------
with tab1:
    st.header("Scan & Upload Site Documents")
    
    # API key input field
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
            with st.spinner("AI parsing documents..."):
                extracted_data = extract_document_data(api_key, inv_upload, mir_upload)
                if extracted_data:
                    st.session_state['parsed_data'] = extracted_data
                    st.success("Documents successfully parsed! Review data details below.")
        else:
            st.error("Please upload both the Invoice and the MIR file.")

    # Verification / Manual Adjustment Form
    st.subheader("Verify & Confirm Extracted Entry")
    with st.form("manual_entry_form"):
        p = st.session_state.get('parsed_data', {})
        
        col_a, col_b, col_c = st.columns(3)
        with col_a:
            v_date = st.date_input("Delivery Date", datetime.datetime.strptime(p.get("Delivery Date", datetime.date.today().strftime("%Y-%m-%d")), "%Y-%m-%d"))
            v_inv = st.text_input("Invoice Number", p.get("Invoice No", ""))
            v_sup = st.text_input("Supplier / Vendor Name", p.get("Supplier", ""))
        with col_b:
            v_mat = st.selectbox("Material Type", MATERIAL_LIST, index=MATERIAL_LIST.index(p.get("Material Type", "Cement")) if p.get("Material Type") in MATERIAL_LIST else 0)
            v_qty = st.number_input("Delivered Quantity", value=float(p.get("Quantity", 0.0)), step=0.1)
            v_unit = st.text_input("Unit (e.g., Tons, Bags, Cum)", p.get("Unit", ""))
        with col_c:
            v_mir = st.text_input("MIR Reference Number", p.get("MIR Ref No", ""))
            v_status = st.selectbox("Inspection Status", ["Passed", "Failed"], index=0 if p.get("MIR Status") == "Passed" else 1)
            
        if st.form_submit_with_clear_on_submit("💾 Confirm & Save to Ledger"):
            if inv_upload and mir_upload:
                # Generate reliable file names to prevent naming collisions
                timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
                inv_path = os.path.join(UPLOAD_DIR, f"{timestamp}_INV_{inv_upload.name}")
                mir_path = os.path.join(UPLOAD_DIR, f"{timestamp}_MIR_{mir_upload.name}")
                
                # Write files out to local directory
                with open(inv_path, "wb") as f: f.write(inv_upload.getbuffer())
                with open(mir_path, "wb") as f: f.write(mir_upload.getbuffer())
                
                # Structure the new log entry
                new_entry = {
                    "Delivery Date": str(v_date), "Invoice No": v_inv, "Supplier": v_sup,
                    "Material Type": v_mat, "Quantity": v_qty, "Unit": v_unit,
                    "MIR Ref No": v_mir, "MIR Status": v_status,
                    "Invoice File": inv_path, "MIR File": mir_path
                }
                
                # Commit to CSV database
                updated_df = pd.concat([ledger_df, pd.DataFrame([new_entry])], ignore_index=True)
                updated_df.to_csv(DB_FILE, index=False)
                st.success("Entry saved and document archive links secured!")
                st.rerun()
            else:
                st.error("Cannot save without active file uploads attached.")

# ------------------------------------------
# TAB 2: MASTER LEDGER & RECONCILIATION
# ------------------------------------------
with tab2:
    st.header("Site Material Inventory Ledger Log")
    
    if not ledger_df.empty:
        # Filtering Tools Interface Layout
        col_f1, col_f2 = st.columns(2)
        with col_f1:
            f_mat = st.multiselect("Filter by Material Category", MATERIAL_LIST, default=MATERIAL_LIST)
        with col_f2:
            f_vendor = st.multiselect("Filter by Supplier Vendor", ledger_df["Supplier"].unique(), default=ledger_df["Supplier"].unique())
            
        filtered_df = ledger_df[(ledger_df["Material Type"].isin(f_mat)) & (ledger_df["Supplier"].isin(f_vendor))]
        
        # Displaying table data elements with download links via standard loops
        st.subheader("Active Records View")
        for index, row in filtered_df.iterrows():
            with st.expander(f"📅 {row['Delivery Date']} | {row['Material Type']} - {row['Quantity']} {row['Unit']} (Inv: {row['Invoice No']})"):
                c1, c2, c3, c4 = st.columns(4)
                c1.write(**f"Supplier:** {row['Supplier']}")
                c2.write(**f"MIR Status:** {row['MIR Status']} ({row['MIR Ref No']})")
                
                # Read local documents to build download capabilities securely
                with open(row["Invoice File"], "rb") as file_inv:
                    c3.download_button(label="📥 Download Invoice File", data=file_inv.read(), file_name=os.path.basename(row["Invoice File"]))
                with open(row["MIR File"], "rb") as file_mir:
                    c4.download_button(label="📥 Download MIR File", data=file_mir.read(), file_name=os.path.basename(row["MIR File"]))
                    
        # Master Export Feature for Excel compatibility
        st.download_button(label="📊 Export Full Ledger Log to CSV Excel", data=filtered_df.to_csv(index=False), file_name="site_reconciliation_report.csv", mime="text/csv")
    else:
        st.info("No delivery records compiled inside storage records yet.")

# ------------------------------------------
# TAB 3: PROJECT ANALYTICS
# ------------------------------------------
with tab3:
    st.header("Material Procurement Target Tracking Matrix")
    
    # Form layout setting goals values
    with st.form("targets_setup_form"):
        st.subheader("Configure Project Structural Requirements Estimations")
        inputs = {}
        cols = st.columns(3)
        for idx, mat in enumerate([m for m in MATERIAL_LIST if m != "Other"]):
            with cols[idx % 3]:
                inputs[mat] = st.number_input(f"Total {mat} Required Quantity:", min_value=0.0, value=float(targets.get(mat, 0.0)))
        
        if st.form_submit_button("Update Contract Targets Data"):
