import streamlit as st
import pandas as pd
import re
from datetime import timedelta
import io
import itertools

st.set_page_config(page_title="Auto Reconcile App", layout="wide")
st.title("ระบบจับคู่ Bank Reconciliation อัตโนมัติ")

# --- 1. ตั้งค่าเงื่อนไข (Parameters) ---
col1, col2 = st.columns(2)
with col1:
    date_window = st.number_input("จำนวนวันที่อนุโลม (บวกลบ ไม่เกิน X วัน)", min_value=0, value=3)
with col2:
    tolerance = st.number_input("ยอด Diff ที่ยอมรับได้ (บาท)", min_value=0.0, value=0.0, format="%.2f")

# --- 2. กล่องรับข้อมูล (Input Data) ---
col_stmt, col_jv = st.columns(2)
with col_stmt:
    st.subheader("1. วางข้อมูล Statement")
    stmt_text = st.text_area("Copy วันที่ และ ยอดเงิน มาวางที่นี่", height=200, key="stmt_box")

with col_jv:
    st.subheader("2. วางข้อมูล JV")
    jv_text = st.text_area("Copy วันที่ และ ยอดเงิน มาวางที่นี่", height=200, key="jv_box")

# ฟังก์ชันทำความสะอาดข้อมูล (Data Cleaning & Parsing) แบบอัปเกรด
def parse_data(text_data):
    if not text_data.strip(): return pd.DataFrame()
    rows = text_data.strip().split('\n')
    data = []
    
    # ดิกชันนารีสอนระบบให้รู้จักเดือนไทย
    thai_months = {'ม.ค.': '01', 'ก.พ.': '02', 'มี.ค.': '03', 'เม.ย.': '04', 
                   'พ.ค.': '05', 'มิ.ย.': '06', 'ก.ค.': '07', 'ส.ค.': '08', 
                   'ก.ย.': '09', 'ต.ค.': '10', 'พ.ย.': '11', 'ธ.ค.': '12'}

    for row in rows:
        row = row.strip()
        if not row: continue
        
        # 1. เล็งหา "ยอดเงิน" ที่อยู่ท้ายประโยคเสมอ (รองรับค่าติดลบ และคอมมา)
        match = re.search(r'(-?[\d,]+\.?\d*)$', row)
        if not match: continue
        
        amount_str = match.group(1)
        date_str = row.replace(amount_str, '').strip()
        
        # แปลงยอดเงินให้เป็นตัวเลขค่าบวก
        amount_clean = re.sub(r'[^\d.]', '', amount_str)
        if not amount_clean: continue
        amount_val = abs(float(amount_clean))
        
        # 2. ทำความสะอาดวันที่
        # แปลงเดือนไทย เป็นตัวเลข
        for th, en in thai_months.items():
            if th in date_str:
                date_str = date_str.replace(th, en)
        
        # กวาดสายตาหาเฉพาะ "วัน/เดือน/ปี" (ตัดเวลาทิ้ง)
        date_match = re.search(r'(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})', date_str)
        if date_match:
            d, m, y = date_match.groups()
            
            # แปลงปี พ.ศ. (69 หรือ 2569) ให้เป็น ค.ศ. (2026)
            y_int = int(y)
            if y_int < 100:
                y_int = y_int + 2500 - 543
            elif y_int > 2500:
                y_int = y_int - 543
            
            clean_date = f"{y_int}-{m.zfill(2)}-{d.zfill(2)}"
            
            try:
                parsed_date = pd.to_datetime(clean_date)
                data.append({"Date": parsed_date, "Amount": amount_val})
            except:
                continue

    return pd.DataFrame(data)

# --- 3. ประมวลผลเมื่อกดปุ่ม RUN ---
if st.button("เริ่มประมวลผล (RUN)", type="primary"):
    if stmt_text and jv_text:
        df_stmt = parse_data(stmt_text)
        df_jv = parse_data(jv_text)
        
        if not df_stmt.empty and not df_jv.empty:
            matched_records = []
            
            # วนลูปหายอด Statement ทีละบรรทัด
            for s_idx, s_row in df_stmt.iterrows():
                s_date = s_row['Date']
                s_amount = s_row['Amount']
                
                # กรอง JV ที่อยู่ในกรอบเวลา +/– 3 วัน
                date_min = s_date - timedelta(days=date_window)
                date_max = s_date + timedelta(days=date_window)
                mask_date = (df_jv['Date'] >= date_min) & (df_jv['Date'] <= date_max)
                candidate_jv = df_jv[mask_date]
                
                match_found = False
                
                # Step 1: One-to-One Match (หายอดชนเป๊ะ หรือ ยอดรวม Diff)
                for j_idx, j_row in candidate_jv.iterrows():
                    diff = abs(s_amount - j_row['Amount'])
                    if diff <= tolerance:
                        matched_records.append({
                            "Statement_Date": s_date.strftime('%Y-%m-%d'),
                            "Statement_Amount": s_amount,
                            "JV_Date": j_row['Date'].strftime('%Y-%m-%d'),
                            "JV_Amount": j_row['Amount'],
                            "Diff": diff
                        })
                        df_jv = df_jv.drop(j_idx) # ตัด JV ทิ้ง
                        match_found = True
                        break
                
                # Step 2: Subset Sum (Many-to-One) - จับกลุ่มสูงสุด 3 รายการเพื่อกันระบบค้าง
                if not match_found and len(candidate_jv) >= 2:
                    jv_indices = candidate_jv.index.tolist()
                    for r in range(2, 4): # ลองจับคู่ 2 ถึง 3 รายการ
                        if match_found: break
                        for combo in itertools.combinations(jv_indices, r):
                            combo_sum = df_jv.loc[list(combo), 'Amount'].sum()
                            diff = abs(s_amount - combo_sum)
                            if diff <= tolerance:
                                for j_idx in combo:
                                    matched_records.append({
                                        "Statement_Date": s_date.strftime('%Y-%m-%d'),
                                        "Statement_Amount": s_amount,
                                        "JV_Date": df_jv.loc[j_idx, 'Date'].strftime('%Y-%m-%d'),
                                        "JV_Amount": df_jv.loc[j_idx, 'Amount'],
                                        "Diff": diff if j_idx == combo[0] else 0 # โชว์ Diff แค่บรรทัดแรกของกลุ่ม
                                    })
                                df_jv = df_jv.drop(list(combo)) # ตัด JV กลุ่มนี้ทิ้ง
                                match_found = True
                                break

            # --- 4. สร้างไฟล์ Excel สำหรับ Download ---
            df_matched = pd.DataFrame(matched_records)
            df_unmatched_stmt = df_stmt[~df_stmt['Amount'].isin(df_matched['Statement_Amount'] if not df_matched.empty else [])]
            df_unmatched_jv = df_jv # ส่วนที่เหลือใน df_jv คือ Unmatched

            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                df_matched.to_excel(writer, sheet_name='Matched_Success', index=False)
                df_unmatched_stmt.to_excel(writer, sheet_name='Unmatched_Statement', index=False)
                df_unmatched_jv.to_excel(writer, sheet_name='Unmatched_JV', index=False)
            
            st.success("ประมวลผลสำเร็จ!")
            st.download_button(
                label="📥 ดาวน์โหลดไฟล์รายงาน (Excel)",
                data=output.getvalue(),
                file_name="Reconcile_Report.xlsx",
                mime="application/vnd.ms-excel"
            )
        else:
            st.error("ไม่สามารถอ่านข้อมูลได้ โปรดตรวจสอบว่าลาก Copy มาถูกคอลัมน์ (วันที่ และ ตัวเลข)")
