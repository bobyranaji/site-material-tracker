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

def load_ledger():
    if os.path.exists(DB_FILE):
        try:
            return pd.read_csv(DB_FILE)
        except Exception:
            pass
    return pd.DataFrame(columns=["Delivery Date", "Invoice No", "Supplier", "Material Type", "Quantity", "Unit", "MIR Ref No", "MIR Status", "Combined Document File"])

def load_targets():
    targets_dict = {}
    if os.path.exists(TARGET_FILE):
        try:
            stored_df = pd.read_csv(TARGET_FILE)
            if "Material Type" in stored_df.columns and "Target" in stored_df.columns:
                for _, row in stored_df.iterrows():
                    targets_dict[str(row["Material Type"]).strip()] = float(row["Target"])
        except Exception:
            pass
    return targets_dict

ledger_df = load_ledger()
saved_targets = load_targets()

# ==========================================
# 2. COMBINED DOCUMENT AI ENGINE (GEMINI)
# ==========================================
def extract_combined_document(api_key, combined_file):
    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-2.5-flash')
        
        # Load image or pass file data directly to Gemini
        doc_img = Image.open(combined_file)
        
        prompt = """
        Analyze this combined construction site document, which contains both a Material Delivery Invoice and its matching Material Inspection Report (MIR) attached together.
        
        Carefully scan all pages/sections of the document and extract ALL material line items found.
        
        INSTRUCTION FOR MATERIAL TYPE IDENTIFICATION:
        - Look at the item descriptions listed in the document.
        - Clean and extract its clear trade name or commodity description (e.g., "Cement", "Granite", "Paint", "Plywood", "Tiles"). Keep names short and punchy (1 to 3 words max).

        Format your final response strictly as a JSON list of objects matching this precise template layout. Do not wrap in markdown text blocks or backticks:
        [
            {
                "Delivery Date": "YYYY-MM-DD",
                "Invoice No": "string",
                "Supplier": "string",
                "Material Type": "The clean extracted commodity name",
                "Quantity": 0.0,
                "Unit": "string",
                "MIR Ref No": "string",
                "MIR Status": "Passed or Failed"
            }
        ]
        """
        response = model.generate_content([prompt, doc_img])
        clean_text = response.text.replace("```json", "").replace("```python", "").replace("```", "").strip()
        return json.loads(clean_text)
    except Exception as e:
        st.error(f"AI parsing failed: {e}. Ensure the uploaded image is clear.")
        return None

# ==========================================
# 3. USER INTERFACE LAYOUT
# ==========================================
st.title("🏗️ Smart Site Material Tracker & Reconciler")
tab1, tab2, tab3 = st.tabs(["📋 Document Inwarding", "📊 Master Ledger & Reconciliation", "📈 Project Analytics"])

# ------------------------------------------
# TAB 1: DOCUMENT INWARDING (ONE UPLOADER BOX)
# ------------------------------------------
with tab1:
    st.header("Scan & Upload Combined Document")
    st.info("💡 Attach the scanned single file that contains both the invoice and the inspection report (MIR) together.")
    
    api_key = st.text_input("Enter Gemini API Key to enable AI scanning:", type="password")
    
    # Unified uploader box
    combined_upload = st.file_uploader("Upload Combined Invoice + MIR Document (Image/PNG/JPG)", type=["png", "jpg", "jpeg"])
        
    if st.button("🚀 Analyze Combined Document"):
        if not api_key:
            st.warning("Please provide an API Key first!")
        elif combined_upload:
            with st.spinner("AI scanning combined document sheets..."):
                extracted_list = extract_combined_document(api_key, combined_upload)
                if extracted_list:
                    for item in extracted_list:
                        try:
                            item["Delivery Date"] = datetime.datetime.strptime(item["Delivery Date"], "%Y-%m-%d").date()
                        except Exception:
                            item["Delivery Date"] = datetime.date.today()
                    st.session_state['parsed_items'] = extracted_list
                    st.success(f"Successfully extracted {len(extracted_list)} material rows from the document!")
        else:
            st.error("Please upload the combined document file first.")

    if 'parsed_items' in st.session_state:
        st.subheader("📝 Step 2: Review and Edit Extracted Items")
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
            if combined_upload:
                timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
                doc_path = os.path.join(UPLOAD_DIR, f"{timestamp}_COMBINED_{combined_upload.name}")
                
                with open(doc_path, "wb") as f: 
                    f.write(combined_upload.getbuffer())
                
                edited_df["Delivery Date"] = edited_df["Delivery Date"].astype(str)
                edited_df["Combined Document File"] = doc_path
                
                # Strip out old file references if they exist from older templates
                if "Invoice File" in edited_df.columns: edited_df = edited_df.drop(columns=["Invoice File"])
                if "MIR File" in edited_df.columns: edited_df = edited_df.drop(columns=["MIR File"])
                
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
        active_mats = sorted(ledger_df["Material Type"].dropna().unique().tolist())
        col_f1, col_f2 = st.columns(2)
        with col_f1:
            f_mat = st.multiselect("Filter by Material Category", active_mats, default=active_mats)
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
                    with open(doc_file_str, "rb") as file_doc:
                        c3.download_button(label="📥 Download Combined Doc File", data=file_doc.read(), file_name=os.path.basename(doc_file_str), key=f"doc_{index}")
                    
        st.download_button(label="📊 Export Full Ledger Log to CSV", data=filtered_df.to_csv(index=False), file_name="site_reconciliation_report.csv", mime="text/csv")
    else:
        st.info("No delivery records compiled inside storage records yet.")

# ------------------------------------------
# TAB 3: PROJECT ANALYTICS
# ------------------------------------------
with tab3:
    st.header("📈 Dynamic Material Procurement Summary")
    
    if not ledger_df.empty:
        passed_df = ledger_df[ledger_df["MIR Status"] == "Passed"].copy()
        
        summary_df = passed_df.groupby("Material Type").agg(
            Total_Delivered=("Quantity", "sum"),
            Unit=("Unit", "first")
        ).reset_index()
        
        summary_df.columns = ["Material Category", "Total Delivered Till Now", "Unit"]
        summary_df["Total Required Quantity"] = summary_df["Material Category"].map(lambda x: float(saved_targets.get(str(x).strip(), 0.0)))
        
        summary_df["Fulfillment Progress Bar"] = summary_df["Total Delivered Till Now"] / summary_df["Total Required Quantity"].replace(0, 1)
        summary_df.loc[summary_df["Total Required Quantity"] <= 0, "Fulfillment Progress Bar"] = 0.0
        
