import streamlit as st
import pandas as pd
import os
import datetime
from google import generativeai as genai
from PIL import Image
import json
from pypdf import PdfReader

# ==========================================
# 1. SETUP & CORE CONFIGURATION
# ==========================================
st.set_page_config(page_title="Interior Fitout Tracker", layout="wide")

UPLOAD_DIR = "stored_documents"
os.makedirs(UPLOAD_DIR, exist_ok=True)
DB_FILE = "material_ledger.csv"
TARGET_FILE = "project_targets.csv"

# Shared master checklist optimized for Interior Fit-out scopes
FITOUT_MATERIALS = [
    "Gypsum Board", "Partition Channel", "Ceiling Framing Material", 
    "Tiles", "Marble", "Glazing / Glass Panels", "Wall Paint", 
    "Acoustic Ceiling Tiles", "Plywood / MDF Boards", "Laminates / Veneer",
    "Hardware Locks & Hinges", "Electrical Conduit Pipes", "LED Light Fixtures"
]

def load_ledger():
    if os.path.exists(DB_FILE):
        try: return pd.read_csv(DB_FILE)
        except Exception: pass
    return pd.DataFrame(columns=["Delivery Date", "Invoice No", "Supplier", "Material Type", "Quantity", "Unit", "MIR Ref No", "MIR Status", "Combined Document File"])

def load_targets():
    targets_dict = {mat: 0.0 for mat in FITOUT_MATERIALS}
    if os.path.exists(TARGET_FILE):
        try:
            stored_df = pd.read_csv(TARGET_FILE)
            for _, row in stored_df.iterrows():
                mat_name = str(row.iloc[0]).strip()
                if mat_name in targets_dict:
                    targets_dict[mat_name] = float(row.iloc[1])
        except Exception: pass
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
# 2. CORE AI EXTRACTION ENGINES (GEMINI)
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
        Analyze this document (Invoice + MIR). Extract ALL unique material line items found. 
        Map them cleanly into one of these categories if possible: {', '.join(FITOUT_MATERIALS)}.
        Format response strictly as a clean JSON list, no markdown formatting or backticks:
        [
            {{
                "Delivery Date": "YYYY-MM-DD", "Invoice No": "string", "Supplier": "string",
                "Material Type": "The mapped category name", "Quantity": 0.0, "Unit": "string",
                "MIR Ref No": "string", "MIR Status": "Passed or Failed"
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
        Extract the contract quantity required for each material item. Map them cleanly to these headings: {', '.join(FITOUT_MATERIALS)}.
        Sum up the quantities if a material appears multiple times in different rooms/floors.
        Format response strictly as a clean JSON list of objects, no markdown formatting or backticks:
        [
            {{ "Material Category": "Category name", "Total Required Quantity": 0.0 }}
        ]
        """
        response = model.generate_content([prompt, content_payload])
        clean_text = response.text.replace("```json", "").replace("```python", "").replace("```", "").strip()
        return json.loads(clean_text)
    except Exception as e:
        st.error(f"AI BOQ parsing failed: {e}")
        return None

# ==========================================
# 3. INTERFACE APP MODULE TABS
# ==========================================
st.title("🏗️ Smart Interior Fitout Material Tracker")
tab1, tab2, tab3 = st.tabs(["📋 Document Inwarding", "📊 Master Ledger & Reconciliation", "📈 Project Analytics"])

# --- TAB 1: DOCUMENT INWARDING ---
with tab1:
    st.header("Scan & Upload Combined Document")
    st.info("💡 Attach a single scanned PDF or Image file that contains both the invoice and the inspection report (MIR) together.")
    api_key_t1 = st.text_input("Enter Gemini API Key to enable AI scanning:", type="password", key="api_key_t1")
    combined_upload = st.file_uploader("Upload Combined Invoice + MIR Document (PDF / Image)", type=["pdf", "png", "jpg", "jpeg"], key="upload_t1")
        
    if st.button("🚀 Analyze Combined Document", key="btn_t1"):
        if not api_key_t1: st.warning("Please provide an API Key first!")
        elif combined_upload:
            with st.spinner("AI scanning combined document sheets..."):
                extracted_list = extract_combined_document(api_key_t1, combined_upload)
                if extracted_list:
                    for item in extracted_list:
                        try: item["Delivery Date"] = datetime.datetime.strptime(item["Delivery Date"], "%Y-%m-%d").date()
                        except Exception: item["Delivery Date"] = datetime.date.today()
                    st.session_state['parsed_items'] = extracted_list
                    st.success(f"Successfully extracted {len(extracted_list)} rows!")
        else: st.error("Please upload a file first.")

    if 'parsed_items' in st.session_state:
        st.subheader("📝 Step 2: Review and Edit Extracted Items")
        preview_df = pd.DataFrame(st.session_state['parsed_items'])
        edited_df = st.data_editor(preview_df, column_config={
            "Material Type": st.column_config.SelectboxColumn("Material Category", options=FITOUT_MATERIALS, required=True),
            "Delivery Date": st.column_config.DateColumn("Date", required=True),
            "Quantity": st.column_config.NumberColumn("Qty", min_value=0.0, format="%.2f")
        }, num_rows="dynamic", key="items_editor")
        
        if st.button("💾 Save All Rows to Ledger"):
            if combined_upload:
                timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
                doc_path = os.path.join(UPLOAD_DIR, f"{timestamp}_COMBINED_{combined_upload.name}")
                with open(doc_path, "wb") as f: f.write(combined_upload.getbuffer())
                edited_df["Delivery Date"] = edited_df["Delivery Date"].astype(str)
                edited_df["Combined Document File"] = doc_path
                updated_df = pd.concat([ledger_df, edited_df], ignore_index=True)
                updated_df.to_csv(DB_FILE, index=False)
                st.success("All items saved successfully!")
                del st.session_state['parsed_items']
                st.rerun()

# --- TAB 2: MASTER LOGISTICS LEDGER ---
with tab2:
    st.header("Site Material Inventory Ledger Log")
    if not ledger_df.empty:
        col_f1, col_f2 = st.columns(2)
        with col_f1: f_mat = st.multiselect("Filter by Material Category", FITOUT_MATERIALS, default=FITOUT_MATERIALS)
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
                    c3.download_button(label="📥 Download File", data=file_data, file_name=os.path.basename(doc_file_str), key=f"doc_{index}")
        st.download_button(label="📊 Export Ledger to CSV", data=filtered_df.to_csv(index=False), file_name="site_reconciliation_report.csv", mime="text/csv")
    else: st.info("No delivery records compiled inside storage records yet.")

# --- TAB 3: PROJECT ANALYTICS ---
with tab3:
    st.header("📈 Dynamic Material Procurement Summary")
    st.subheader("🗂️ Step 1: Upload Project Estimation sheet (BOQ)")
    st.info("Attach your project BOQ sheet (Excel, PDF, or Image scan). The AI reads it or extracts the values automatically.")
    
    api_key_t3 = st.text_input("Enter Gemini API Key to enable BOQ scanning (Only needed for PDF/Images):", type="password", key="api_key_t3")
    
    # UNLOCKED: Accepts excel formats (.xlsx, .xls) alongside standard media types
    boq_upload = st.file_uploader("Upload Project BOQ File (Excel / PDF / Image)", type=["xlsx", "xls", "pdf", "png", "jpg", "jpeg"], key="upload_t3")
    
    if st.button("🤖 Analyze & Extract Quantities from BOQ"):
        if boq_upload:
            file_name = boq_upload.name.lower()
            
            # AUTOMATED EXCEL PARSING: If it is an Excel sheet, read it directly via pandas instantly
            if file_name.endswith('.xlsx') or file_name.endswith('.xls'):
                with st.spinner("Reading Excel file lines directly..."):
                    try:
                        excel_df = pd.read_excel(boq_upload)
                        # Ask Gemini to map the column descriptions from the clean spreadsheet structure
                        genai.configure(api_key=api_key_t3 if api_key_t3 else "dummy_key")
                        model = genai.GenerativeModel('gemini-2.5-flash')
                        
                        excel_sample = excel_df.head(40).to_string()
                        prompt_excel = f"""
                        Analyze this construction sheet column data data:
                        {excel_sample}
                        
                        Map the matching item categories and total volume quantities to these headings: {', '.join(FITOUT_MATERIALS)}.
                        Format response strictly as a clean JSON list, no markdown or backticks:
                        [
                            {{ "Material Category": "Category name", "Total Required Quantity": 0.0 }}
                        ]
                        """
                        response = model.generate_content(prompt_excel)
                        clean_text = response.text.replace("```json", "").replace("```python", "").replace("```", "").strip()
                        parsed_boq = json.loads(clean_text)
                    except Exception as e:
                        st.error(f"Failed to parse Excel file rows: {e}. If this persists, ensure your columns are formatted clearly.")
                        parsed_boq = None
            else:
                # Standard scan fallback for PDFs or Image captures
                if not api_key_t3:
                    st.warning("Please provide your Gemini API key first to parse PDF/Image files!")
                    parsed_boq = None
                else:
                    with st.spinner("AI parsing item codes and quantities from document layout..."):
                        parsed_boq = extract_boq_document(api_key_t3, boq_upload)
            
            # Commit the structured arrays to database disk profiles
            if parsed_boq:
                clean_save_dict = {mat: 0.0 for mat in FITOUT_MATERIALS}
                for entry in parsed_boq:
                    m_cat = str(entry.get("Material Category", "")).strip()
                    m_qty = float(entry.get("Total Required Quantity", 0.0))
                    if m_cat in clean_save_dict:
                        clean_save_dict[m_cat] = m_qty
                
                save_targets_df = pd.DataFrame(list(clean_save_dict.items()), columns=["Material Type", "Target"])
                save_targets_df.to_csv(TARGET_FILE, index=False)
                st.success("Successfully generated and saved requirements from BOQ document!")
                st.rerun()
        else:
            st.error("Please select a BOQ spreadsheet or document file first.")
            
    st.subheader("📊 Step 2: Interior Fit-out Requirements & Progress Matrix")
    st.info("💡 Instructions: View material categories below. Click the 'Total Required Quantity' cells to adjust goals manually. Fulfillment percentage updates instantly.")

    analytics_rows = []
    for mat in FITOUT_MATERIALS:
        total_delivered = 0.0
        unit_label = "Units"
        if not ledger_df.empty:
            match_rows = ledger_df[(ledger_df["Material Type"] == mat) & (ledger_df["MIR Status"] == "Passed")]
            total_delivered = float(match_rows["Quantity"].sum())
            if not match_rows.empty and "Unit" in match_rows.columns:
                unit_label = str(match_rows["Unit"].dropna().iloc[0])
                
        target_qty = float(saved_targets.get(mat, 0.0))
        progress_ratio = min(total_delivered / target_qty, 1.0) if target_qty > 0 else 0.0
            
        analytics_rows.append({
            "Interior Material Category": mat,
            "Total Delivered Qty": total_delivered,
            "Unit": unit_label,
            "Total Required Quantity": target_qty,
            "Fulfillment Progress": progress_ratio
        })
        
    summary_df = pd.DataFrame(analytics_rows)
    edited_summary_df = st.data_editor(
        summary_df, 
        column_config={
            "Interior Material Category": st.column_config.TextColumn("Interior Material Category", disabled=True),
            "Total Delivered Qty": st.column_config.NumberColumn("Total Delivered Qty", disabled=True, format="%.1f"),
            "Unit": st.column_config.TextColumn("Unit", disabled=True),
            "Total Required Quantity": st.column_config.NumberColumn("Total Required Quantity", min_value=0.0, format="%.1f", step=1.0),
            "Fulfillment Progress": st.column_config.ProgressColumn("Fulfillment % Plan", min_value=0.0, max_value=1.0, format="%f")
        }, 
        num_rows="fixed", 
        use_container_width=True, 
        key="summary_matrix_editor"
    )
    
    if st.button("💾 Save Manual Material Adjustments"):
        save_targets_df = edited_summary_df[["Interior Material Category", "Total Required Quantity"]].copy()
        save_targets_df.columns = ["Material Type", "Target"]
        save_targets_df.to_csv(TARGET_FILE, index=False)
        st.success("Interior fit-out project targets updated successfully!")
        st.rerun()
