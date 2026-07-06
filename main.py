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

# Foundational List
DEFAULT_MATERIALS = ["Cement", "Gypsum Board", "Partition Channel", "Ceiling Framing Material", "Tiles", "Marble", "Glazing"]

def load_ledger():
    if os.path.exists(DB_FILE):
        try:
            return pd.read_csv(DB_FILE)
        except Exception:
            pass
    return pd.DataFrame(columns=["Delivery Date", "Invoice No", "Supplier", "Material Type", "Quantity", "Unit", "MIR Ref No", "MIR Status", "Invoice File", "MIR File"])

def load_targets():
    targets_dict = {}
    if os.path.exists(TARGET_FILE):
        try:
            stored_df = pd.read_csv(TARGET_FILE)
            for _, row in stored_df.iterrows():
                targets_dict[str(row["Material Type"]).strip()] = float(row["Target"])
        except Exception:
            pass
    return targets_dict

ledger_df = load_ledger()
saved_targets = load_targets()

# Gather unique material list dynamically from database history rows
if not ledger_df.empty:
    ledger_materials = ledger_df["Material Type"].dropna().unique().tolist()
else:
    ledger_materials = []

all_active_materials = sorted(list(set(DEFAULT_MATERIALS + ledger_materials)))

# ==========================================
# 2. AI EXTRACTION ENGINE (GEMINI)
# ==========================================
def extract_document_data(api_key, invoice_file, mir_file, existing_categories):
    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-2.5-flash')
        inv_img = Image.open(invoice_file)
        mir_img = Image.open(mir_file)
        
        prompt = f"""
        Analyze these construction documents: Document 1 (Invoice), Document 2 (Inspection Report - MIR).
        Extract ALL items found on the invoice line entries.
        
        INSTRUCTION FOR MATERIAL TYPE IDENTIFICATION:
        1. Look at the item description on the invoice.
        2. First, try to match it cleanly to one of our existing site categories if relevant: {', '.join(existing_categories)}.
        3. CRITICAL: If the material found is a completely brand new type or item not mentioned in that list, DO NOT use "Other". Instead, extract and clean its actual trade or commodity name from the invoice description text (e.g., "Granite", "Paint", "Plywood", "Screws") and use that as the "Material Type". Keep names concise (1 to 4 words max).

        Format your final response strictly as a JSON list of objects matching this exact template layout. Do not wrap in markdown or code blocks:
        [
            {{
                "Delivery Date": "YYYY-MM-DD",
                "Invoice No": "string",
                "Supplier": "string",
                "Material Type": "The matched or brand new extracted category name",
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
        st.error(f"AI multi-row parsing failed: {e}.")
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
            with st.spinner("AI parsing all line items dynamically..."):
                extracted_list = extract_document_data(api_key, inv_upload, mir_upload, all_active_materials)
                if extracted_list:
                    for item in extracted_list:
                        try:
                            item["Delivery Date"] = datetime.datetime.strptime(item["Delivery Date"], "%Y-%m-%d").date()
                        except Exception:
                            item["Delivery Date"] = datetime.date.today()
                    st.session_state['parsed_items'] = extracted_list
                    st.success(f"Successfully extracted {len(extracted_list)} line items!")
        else:
            st.error("Please upload both documents first.")

    if 'parsed_items' in st.session_state:
        st.subheader("📝 Step 2: Review and Edit Extracted Items")
        st.info("You can add temporary categories or double-click to clean text strings directly in the layout grid below.")
        
        preview_df = pd.DataFrame(st.session_state['parsed_items'])
        
        edited_df = st.data_editor(
            preview_df,
            column_config={
                "Material Type": st.column_config.TextColumn("Material Category", required=True),
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
                
                edited_df["Delivery Date"] = edited_df["Delivery Date"].astype(str)
                edited_df["Invoice File"] = inv_path
                edited_df["MIR File"] = mir_path
                
                updated_df = pd.concat([ledger_df, edited_df], ignore_index=True)
                updated_df.to_csv(DB_FILE, index=False)
                
                st.success("All items successfully processed and ledger synchronized!")
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
            f_mat = st.multiselect("Filter by Material Category", all_active_materials, default=all_active_materials)
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
                
                inv_file_str = str(row["Invoice File"])
                if os.path.exists(inv_file_str):
                    with open(inv_file_str, "rb") as file_inv:
                        c3.download_button(label="📥 Download Invoice", data=file_inv.read(), file_name=os.path.basename(inv_file_str), key=f"inv_{index}")
                
                mir_file_str = str(row["MIR File"])
                if os.path.exists(mir_file_str):
                    with open(mir_file_str, "rb") as file_mir:
                        c4.download_button(label="📥 Download MIR", data=file_mir.read(), file_name=os.path.basename(mir_file_str), key=f"mir_{index}")
                    
        st.download_button(label="📊 Export Full Ledger Log to CSV", data=filtered_df.to_csv(index=False), file_name="site_reconciliation_report.csv", mime="text/csv")
    else:
        st.info("No delivery records compiled inside storage records yet.")

# ------------------------------------------
# TAB 3: PROJECT ANALYTICS (UPGRADED LAYOUT GRID)
# ------------------------------------------
with tab3:
    st.header("📈 Material Procurement Summary Matrix")
    st.info("💡 Instructions: Use the table grid below to add or adjust your 'Total Required Quantity' values. The Fulfilled Delivery % calculates automatically. Remember to click Save at the bottom to hold changes!")

    analytics_rows = []
    
