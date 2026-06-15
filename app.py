import streamlit as st
import pandas as pd
import re
from datetime import timedelta
import io
import itertools

st.set_page_config(page_title="Auto Reconcile App", layout="wide")
st.title("ระบบจับคู่ Bank Reconciliation อัตโนมัติ")

# ตั้งค่าเงื่อนไข
date_window = st.number_input("จำนวนวันที่อนุโลม (บวกลบ ไม่เกิน X วัน)", min_value=0, value=3)

# กล่องรับข้อมูล
col_stmt, col_jv = st.columns(2)
with col_stmt:
    st.subheader("1. วางข้อมูล Statement")
    stmt_text = st.text_area("Copy วันที่ และ ยอดเงิน มาวางที่นี่", height=200, key="stmt_box")

with col_jv:
    st.subheader("2. วางข้อมูล JV")
    jv_text = st.text_area("Copy วันที่ และ ยอดเงิน มาวางที่นี่", height=200, key="jv_box")

def parse_data(text_data):
    if not text_data.strip(): return pd.DataFrame()
    rows = text_data.strip().split('\n')
    data = []
    thai_months = {'ม.ค.': '01', 'ก.พ.': '02', 'มี.ค.': '03', 'เม.ย.': '04', 
                   'พ.ค.': '05', 'มิ.ย.': '06', 'ก.ค.': '07', 'ส.ค.': '08', 
                   'ก.ย.': '09', 'ต.ค.': '10', 'พ.ย.': '11', 'ธ.ค.': '12'}

    for row in rows:
        row = row.strip()
        if not row: continue
        
        match = re.search(r'(-?[\d,]+\.?\d*)$', row)
        if not match: continue
        
        amount_str = match.group(1)
        date_str = row.replace(amount_str, '').strip()
        
        amount_clean = re.sub(r'[^\d.]', '', amount_str)
        if not amount_clean: continue
        amount_val = abs(float(amount_clean))
        
        for th, en in thai_months.items():
            if th in date_str:
                date_str = date_str.replace(th, en)
        
        date_match = re.search(r'(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})', date_str)
        if date_match:
            d, m, y = date_match.groups()
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

if st.button("เริ่มประมวลผล (RUN)", type="primary"):
    if stmt_text and jv_text:
        df_stmt = parse_data(stmt_text)
        df_jv = parse_data(jv_text)
        
        if not df_stmt.empty and not df_jv.empty:
            matched_records = []
            
            df_stmt = df_stmt.sort_values(by=['Date', 'Amount'])
            
            for s_idx, s_row in df_stmt.iterrows():
                s_date = s_row['Date']
                s_amount = s_row['Amount']
                
                date_min = s_date - timedelta(days=date_window)
                date_max = s_date + timedelta(days=date_window)
                
                mask_date = (df_jv['Date'] >= date_min) & (df_jv['Date'] <= date_max)
                candidate_jv = df_jv[mask_date]
                
                match_found = False
                
                for j_idx, j_row in candidate_jv.iterrows():
                    if s_amount == j_row['Amount']:
                        matched_records.append({
                            "Statement_Date": s_date.strftime('%Y-%m-%d'),
                            "Statement_Amount": s_amount,
                            "JV_Date": j_row['Date'].strftime('%Y-%m-%d'),
                            "JV_Amount": j_row['Amount']
                        })
                        df_jv = df_jv.drop(j_idx)
                        match_found = True
                        break
                
                if not match_found and len(candidate_jv) >= 2:
                    jv_indices = candidate_jv.index.tolist()
                    for r in range(2, 5): 
                        if match_found: break
                        for combo in itertools.combinations(jv_indices, r):
                            combo_sum = df_jv.loc[list(combo), 'Amount'].sum()
                            if abs(s_amount - combo_sum) < 0.01: 
                                for j_idx in combo:
                                    matched_records.append({
                                        "Statement_Date": s_date.strftime('%Y-%m-%d'),
                                        "Statement_Amount": s_amount,
                                        "JV_Date": df_jv.loc[j_idx, 'Date'].strftime('%Y-%m-%d'),
                                        "JV_Amount": df_jv.loc[j_idx, 'Amount']
                                    })
                                df_jv = df_jv.drop(list(combo))
                                match_found = True
                                break

            # สรุปยอด
            df_matched = pd.DataFrame(matched_records)
            df_unmatched_stmt = df_stmt[~df_stmt.index.isin([s_idx for s_idx, _ in df_stmt.iterrows() if s_idx not in df_stmt.index])] 
            
            # แปลงวันที่ในตาราง Diff ให้เป็น String สวยๆ ก่อนโชว์
            if not df_unmatched_stmt.empty:
                df_unmatched_stmt['Date'] = df_unmatched_stmt['Date'].dt.strftime('%Y-%m-%d')
            if not df_jv.empty:
                df_jv['Date'] = df_jv['Date'].dt.strftime('%Y-%m-%d')
                
            df_unmatched_jv = df_jv 

            st.success("🎉 ประมวลผลสำเร็จ! ตรวจสอบผลลัพธ์ด้านล่างได้เลยครับ")

            # --- ส่วนที่เพิ่มใหม่: โชว์ตารางบนหน้าเว็บ ---
            st.divider()
            
            st.subheader("✅ รายการที่จับคู่สำเร็จ (Matched)")
            if not df_matched.empty:
                st.dataframe(df_matched, use_container_width=True)
            else:
                st.info("ไม่มีรายการที่สามารถจับคู่กันได้พอดีในรอบนี้")

            st.divider()

            col_res1, col_res2 = st.columns(2)
            with col_res1:
                st.subheader("❌ ยอด Statement ที่จับคู่ไม่ได้ (Diff)")
                if not df_unmatched_stmt.empty:
                    st.dataframe(df_unmatched_stmt, use_container_width=True)
                else:
                    st.success("ยอดเยี่ยม! ไม่มีรายการ Statement คงเหลือ")

            with col_res2:
                st.subheader("❌ ยอด JV ที่จับคู่ไม่ได้ (Diff)")
                if not df_unmatched_jv.empty:
                    st.dataframe(df_unmatched_jv, use_container_width=True)
                else:
                    st.success("ยอดเยี่ยม! ไม่มีรายการ JV คงเหลือ")

            st.divider()
            
            # --- สร้างไฟล์ Excel สำหรับ Download ---
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                if not df_matched.empty:
                    df_matched.to_excel(writer, sheet_name='Matched_Success', index=False)
                df_unmatched_stmt.to_excel(writer, sheet_name='Unmatched_Statement_Diff', index=False)
                df_unmatched_jv.to_excel(writer, sheet_name='Unmatched_JV_Diff', index=False)
            
            st.download_button(
                label="📥 ดาวน์โหลดไฟล์รายงาน (Excel) เพื่อเก็บเป็นหลักฐาน",
                data=output.getvalue(),
                file_name="Reconcile_Report.xlsx",
                mime="application/vnd.ms-excel"
            )
        else:
            st.error("ไม่สามารถอ่านข้อมูลได้ โปรดตรวจสอบว่าลาก Copy มาถูกคอลัมน์")
