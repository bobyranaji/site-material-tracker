import streamlit as st
import pandas as pd
import os
import datetime
from google import generativeai as genai
from PIL import Image
import json
from pypdf import PdfReader

# ==========================================
# 1. SETUP & CONFIGURATION
# ==========================================
st.set_page_config(page_title="Interior Fitout Material Tracker", layout="wide")

UPLOAD_DIR = "stored_documents"
os.makedirs(UPLOAD_DIR, exist_ok=True)
DB_FILE = "material_ledger.csv"
TARGET_FILE = "project_targets.csv"

# Pre-defined checklist optimized for Interior Fit-out scopes
FITOUT_MATERIALS = [
    "Gypsum Board", 
    "Partition Channel", 
    "Ceiling Framing Material", 
    "Tiles", 
    "Marble", 
    "Glazing / Glass Panels", 
    "Wall Paint", 
    "Acoustic Ceiling Tiles",
    "Plywood / MDF Boards",
    "Laminates / Veneer",
    "Hardware Locks & Hinges",
    "Electrical Conduit Pipes",
    "LED Light Fixtures"
]

def load_ledger():
    if os.path.exists(DB_FILE):
        try:
            return pd.read_csv(DB_FILE)
        except Exception:
            pass
    return pd.DataFrame(columns=["Delivery Date", "Invoice No", "Supplier", "Material Type", "Quantity", "Unit", "MIR Ref No", "MIR Status", "Combined Document File"])

def load_targets():
    targets_dict = {mat: 0.0 for mat in FITOUT_MATERIALS}
    if os.path.exists(TARGET_FILE):
        try:
            stored_df = pd.read_csv(TARGET_FILE)
            for _, row in stored_df.iterrows():
                mat_name = str(row.iloc[0]).strip()
                target_val = float(row.iloc[1])
                if mat_name in targets_dict:
                    targets_dict[mat_name] = target_val
        except Exception:
            pass
    return targets_dict

ledger_df = load_ledger()
saved_targets = load_targets()

def get_pdf_text(file_buffer):
    reader = PdfReader(file_buffer)
    pdf_text = ""
    for page in reader.pages:
        pdf_text += page.extract_text() + "\n"
    return pdf_text

# ==========================================
# 2. ADVANCED AI EXTRACTION ENGINES (GEMINI)
# ==========================================
def extract_combined_document(api_key, combined_file):
    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-2.5-flash')
        
        if combined_file.name.lower().endswith('.pdf'):
            content_payload = f"Document Text Contents:\n{get_pdf_text(combined_file)}"
        else:
            content_payload = Image.open(combined_file)
        
        prompt = f"""
        Analyze this construction site document data (Invoice + MIR).
        Extract ALL unique material line items found. 
        Try to group or map them cleanly into one of these interior fit-out categories if possible: {', '.join(FITOUT_MATERIALS)}.
        
        Format your final response strictly as a JSON list of objects matching this layout. No markdown or backticks:
        [
            {{
                "Delivery Date": "YYYY-MM-DD",
                "Invoice No": "string",
                "Supplier": "string",
                "Material Type": "The mapped trade or commodity name",
                "Quantity": 0.0,
                "Unit": "string",
                "MIR Ref No": "string",
                "MIR Status": "Passed or Failed"
            }}
        ]
        """
        response = model.generate_content([prompt, content_payload])
        clean_text = response.text.replace("```json", "").replace("```python", "").replace("```", "").strip()
        return json.loads(clean_text)
    except Exception as e:
        st.error(f"AI parsing failed: {e}")
        return None

def extract_boq_document(api_key, boq_file):
    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-2.5-flash')
        
        if boq_file.name.lower().endswith('.pdf'):
            content_payload = f"BOQ Text Contents:\n{get_pdf_text(boq_file)}"
        else:
            content_payload = Image.open(boq_file)
            
        prompt = f"""
        Analyze this Interior Fit-out Project Bill of Quantities (BOQ) document.
        Extract the contract quantity required for each material item. Map them cleanly to these fit-out headings: {', '.join(FITOUT_MATERIALS)}.
        Sum up the quantities if a material appears multiple times in different rooms/floors.

        Format your final response strictly as a JSON list of objects matching this layout. No markdown or backticks:
        [
            {{
                "Material Category": "The matching fit-out category name",
                "Total Required Quantity": 0.0
            }}
        ]
        """
        response = model.generate_content([prompt, content_payload])
        clean_text = response.text.replace("```json", "").replace("```python", "").replace("```", "").strip()
        return json.loads(clean_text)
    except Exception as e:
        st.error(f"AI BOQ parsing failed: {e}")
        return None

# ==========================================
# 3. USER INTERFACE LAYOUT
# ==========================================
st.title("🏗️ Smart Interior Fitout Material Tracker")
tab1, tab2, tab3 = st.tabs(["📋 Document Inwarding", "📊 Master Ledger & Reconciliation", "📈 Project Analytics"])

# ------------------------------------------
# TAB 1: DOCUMENT INWARDING
# ------------------------------------------
with tab1:
    st.header("Scan & Upload Combined Document")
    api_key_t1 = st.text_input("Enter Gemini API Key to enable AI scanning:", type="password", key="api_key_t1")
    combined_upload = st.file_uploader("Upload Combined Invoice + MIR Document (PDF / Image)", type=["pdf", "png", "jpg", "jpeg"], key="upload_t1")
        
    if st.button("🚀 Analyze Combined Document", key="btn_t1"):
        if not api_key_t1:
            st.warning("Please provide an API Key first!")
        elif combined_upload:
            with st.spinner("AI scanning combined document sheets..."):
                extracted_list = extract_combined_document(api_key_t1, combined_upload)
                if extracted_list:
                    for item in extracted_list:
                        try:
                            item["Delivery Date"] = datetime.datetime.strptime(item["Delivery Date"], "%Y-%m-%d").date()
                        except Exception:
                            item["Delivery Date"] = datetime.date.today()
                    st.session_state['parsed_items'] = extracted_list
                    st.success(f"Successfully extracted {len(extracted_list)} material rows!")
        else:
            st.error("Please upload a file first.")

    if 'parsed_items' in st.session_state:
        st.subheader("📝 Step 2: Review and Edit Extracted Items")
        preview_df = pd.DataFrame(st.session_state['parsed_items'])
        
        edited_df = st.data_editor(
            preview_df,
            column_config={
                "Material Type": st.column_config.SelectboxColumn("Material Category", options=FITOUT_MATERIALS, required=True),
                "Delivery Date": st.column_config.DateColumn("Date", required=True),
                "Quantity": st.column_config.NumberColumn("Qty", min_value=0.0, format="%.2f")
            },
            num_rows="dynamic",
            key="items_editor"
        )
        
        if st.button("💾 Save All Rows to Ledger"):
            if combined_upload:
                timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
                doc_path = os.path.join(UPLOAD_DIR, f"{timestamp}_COMBINED_{combined_upload.name}")
                with open(doc_path, "wb") as f: 
                    f.write(combined_upload.getbuffer())
                
                edited_df["Delivery Date"] = edited_df["Delivery Date"].astype(str)
                edited_df["Combined Document File"] = doc_path
                
                updated_df = pd.concat([ledger_df, edited_df], ignore_index=True)
                updated_df.to_csv(DB_FILE, index=False)
                st.success("All line items committed to master ledger database successfully!")
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
            f_mat = st.multiselect("Filter by Material Category", FITOUT_MATERIALS, default=FITOUT_MATERIALS)
        with col_f2:
            unique_suppliers = ledger_df["Supplier"].dropna().unique().tolist()
            f_vendor = st.multiselect("Filter by Supplier Vendor", unique_suppliers, default=unique_suppliers)
            
        filtered_df = ledger_df[(ledger_df["Material Type"].isin(f_mat)) & (ledger_df["Supplier"].isin(f_vendor))]
        st.subheader("Active Records View")
        for index, row in filtered_df.iterrows():
            with st.expander(f"📅 {row['Delivery Date']} | {row['Material Type']} - {row['Quantity']} {row['Unit']} (Inv: {row['Invoice No']})"):
                c1, c2, c3 = st.columns(3)
                c1.write(f"**Supplier:** {row['Supplier']}")
                c2.write(f"**MIR Status:** {row['MIR Status']} ({row['MIR Ref No']})")
                
                doc_file_str = str(row["Combined Document File"]) if "Combined Document File" in row and pd.notna(row["Combined Document File"]) else ""
                if os.path.exists(doc_file_str):
                    file_data = open(doc_file_str, "rb").read()
                    c3.download_button(label="📥 Download Combined Doc", data=file_data, file_name=os.path.basename(doc_file_str), key=f"doc_{index}")
                    
        st.download_button(label="📊 Export Full Ledger Log to CSV", data=filtered_df.to_csv(index=False), file_name="site_reconciliation_report.csv", mime="text/csv")
    else:
