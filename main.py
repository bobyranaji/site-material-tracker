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

MATERIAL_LIST = ["Cement", "Gypsum Board", "Partition Channel", "Ceiling Framing Material", "Tiles", "Marble", "Glazing", "Other"]

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
    return {"Cement": 0.0, "Gypsum Board": 0.0, "Partition Channel": 0.0, "Ceiling Framing Material": 0.0, "Tiles": 0.0, "Marble": 0.0, "Glazing": 0.0}

ledger_df = load_ledger()
targets = load_targets()

# ==========================================
# 2. AI EXTRACTION ENGINE (GEMINI)
# ==========================================
def extract_document_data(api_key, invoice_file, mir_file):
    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-2.5-flash')
        inv_img = Image.open(invoice_file)
        mir_img = Image.open(mir_file)
        
        prompt = f"""
        Analyze these two construction site documents: 
        Document 1 is a Material Delivery Invoice.
        Document 2 is a Material Inspection Report (MIR).
        Extract fields accurately. Pick Material Type strictly from: {', '.join(MATERIAL_LIST)}.
        Format your response EXACTLY as a clean JSON object matching this format precisely:
        {{
            "Delivery Date": "YYYY-MM-DD",
            "Invoice No": "string",
            "Supplier": "string",
            "Material Type": "string",
            "Quantity": 0.0,
            "Unit": "string",
            "MIR Ref No": "string",
            "MIR Status": "Passed"
        }}
        Provide only clean JSON string. No markdown formatting.
        """
        response = model.generate_content([prompt, inv_img, mir_img])
        clean_text = response.text.replace("```json", "").replace("```python", "").replace("```", "").strip()
        return json.loads(clean_text)
    except Exception as e:
        st.error(f"AI parsing failed: {e}. Please fill out details manually below.")
        return None

# ==========================================
# 3. USER INTERFACE LAYOUT
# ==========================================
st.title("🏗️ Smart Site Material Tracker & Reconciler")
tab1, tab2, tab3 = st.tabs(["📋 Document Inwarding", "📊 Master Ledger & Reconciliation", "📈 Project Analytics"])

# ------------------------------------------
# TAB 1: DOCUMENT INWARDING
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
            with st.spinner("AI parsing documents..."):
                extracted_data = extract_document_data(api_key, inv_upload, mir_upload)
                if extracted_data:
                    st.session_state['parsed_data'] = extracted_data
                    st.success("Documents successfully parsed! Review details below.")
        else:
            st.error("Please upload both the Invoice and the MIR file.")

    st.subheader("Verify & Confirm Extracted Entry")
    with st.form("manual_entry_form"):
        p = st.session_state.get('parsed_data', {})
        col_a, col_b, col_c = st.columns(3)
        
        with col_a:
            try:
                default_date = datetime.datetime.strptime(p.get("Delivery Date", ""), "%Y-%m-%d").date()
            except ValueError:
                default_date = datetime.date.today()
            v_date = st.date_input("Delivery Date", default_date)
            v_inv = st.text_input("Invoice Number", p.get("Invoice No", ""))
            v_sup = st.text_input("Supplier / Vendor Name", p.get("Supplier", ""))
            
        with col_b:
            v_mat = st.selectbox("Material Type", MATERIAL_LIST, index=MATERIAL_LIST.index(p.get("Material Type")) if p.get("Material Type") in MATERIAL_LIST else 0)
            try:
                default_qty = float(p.get("Quantity", 0.0))
            except ValueError:
                default_qty = 0.0
            v_qty = st.number_input("Delivered Quantity", value=default_qty, step=0.1)
            v_unit = st.text_input("Unit (e.g., Tons, Bags, Cum)", p.get("Unit", ""))
            
        with col_c:
            v_mir = st.text_input("MIR Reference Number", p.get("MIR Ref No", ""))
            v_status = st.selectbox("Inspection Status", ["Passed", "Failed"], index=0 if p.get("MIR Status") == "Passed" else 1)
            
        if st.form_submit_button("💾 Confirm & Save to Ledger"):
            if inv_upload and mir_upload:
                timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
                inv_path = os.path.join(UPLOAD_DIR, f"{timestamp}_INV_{inv_upload.name}")
                mir_path = os.path.join(UPLOAD_DIR, f"{timestamp}_MIR_{mir_upload.name}")
                with open(inv_path, "wb") as f: 
                    f.write(inv_upload.getbuffer())
                with open(mir_path, "wb") as f: 
                    f.write(mir_upload.getbuffer())
                
                new_entry = {
                    "Delivery Date": str(v_date), "Invoice No": v_inv, "Supplier": v_sup,
                    "Material Type": v_mat, "Quantity": v_qty, "Unit": v_unit,
                    "MIR Ref No": v_mir, "MIR Status": v_status,
                    "Invoice File": inv_path, "MIR File": mir_path
                }
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
# TAB 3: PROJECT ANALYTICS (FLATTENED & FIXED)
# ------------------------------------------
with tab3:
    st.header("Material Procurement Target Tracking Matrix")
    st.subheader("Configure Project Structural Requirements Estimations")
    
    inputs = {}
    
    # Using straight stacked layout to remove all layout column indentation risks completely
    inputs["Cement"] = st.number_input("Total Cement Required:", min_value=0.0, value=float(targets.get("Cement", 0.0)), key="in_cement")
    inputs["Gypsum Board"] = st.number_input("Total Gypsum Board Required:", min_value=0.0, value=float(targets.get("Gypsum Board", 0.0)), key="in_gypsum")
    inputs["Partition Channel"] = st.number_input("Total Partition Channel Required:", min_value=0.0, value=float(targets.get("Partition Channel", 0.0)), key="in_partition")
