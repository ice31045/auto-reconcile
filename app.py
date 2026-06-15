import streamlit as st
import pandas as pd
import re
from datetime import timedelta
import io
import itertools

st.set_page_config(page_title="Auto Reconcile App", layout="wide")
st.title("ระบบจับคู่ Bank Reconciliation อัตโนมัติ")

date_window = st.number_input("จำนวนวันที่อนุโลม (บวกลบ ไม่เกิน X วัน)", min_value=0, value=3)

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
            if th in date_str: date_str = date_str.replace(th, en)
        date_match = re.search(r'(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})', date_str)
        if date_match:
            d, m, y = date_match.groups()
            y_int = int(y)
            if y_int < 100: y_int = y_int + 2500 - 543
            elif y_int > 2500: y_int = y_int - 543
            clean_date = f"{y_int}-{m.zfill(2)}-{d.zfill(2)}"
            try:
                parsed_date = pd.to_datetime(clean_date)
                data.append({"Date": parsed_date, "Amount": amount_val})
            except: continue
    return pd.DataFrame(data)

if st.button("เริ่มประมวลผล (RUN)", type="primary"):
    if stmt_text and jv_text:
        df_stmt = parse_data(stmt_text)
        df_jv = parse_data(jv_text)
        
        if not df_stmt.empty and not df_jv.empty:
            matched_records = []
            df_stmt = df_stmt.sort_values(by=['Date', 'Amount'])
            
            for s_idx, s_row in df_stmt.iterrows():
                s_date, s_amount = s_row['Date'], s_row['Amount']
                date_min, date_max = s_date - timedelta(days=date_window), s_date + timedelta(days=date_window)
                candidate_jv = df_jv[(df_jv['Date'] >= date_min) & (df_jv['Date'] <= date_max)]
                
                match_found = False
                # 1. 1-to-1 Match
                for j_idx, j_row in candidate_jv.iterrows():
                    if s_amount == j_row['Amount']:
                        matched_records.append({"Statement_Date": s_date.strftime('%Y-%m-%d'), "Statement_Amount": s_amount, "JV_Date": j_row['Date'].strftime('%Y-%m-%d'), "JV_Amount": j_row['Amount']})
                        df_jv = df_jv.drop(j_idx)
                        match_found = True
                        break
                
                # 2. Many-to-1 Match (ด้วยเทคนิค Hash Map ที่รวดเร็ว)
                if not match_found and len(candidate_jv) >= 2:
                    valid_jv = candidate_jv[candidate_jv['Amount'] <= s_amount]
                    jv_map = {idx: row['Amount'] for idx, row in valid_jv.iterrows()}
                    for r in range(2, 4):
                        if match_found: break
                        for combo in itertools.combinations(jv_map.keys(), r):
                            if abs(s_amount - sum(jv_map[idx] for idx in combo)) < 0.01:
                                for j_idx in combo:
                                    matched_records.append({"Statement_Date": s_date.strftime('%Y-%m-%d'), "Statement_Amount": s_amount, "JV_Date": df_jv.loc[j_idx, 'Date'].strftime('%Y-%m-%d'), "JV_Amount": df_jv.loc[j_idx, 'Amount']})
                                df_jv = df_jv.drop(list(combo))
                                match_found = True
                                break

            # สรุปผล
            df_matched = pd.DataFrame(matched_records)
            df_unmatched_stmt = df_stmt[~df_stmt.index.isin([i for i in df_stmt.index if i not in df_stmt.index])] # dummy 
            df_unmatched_jv = df_jv
            
            st.success("🎉 ประมวลผลสำเร็จ!")
            st.subheader("✅ รายการที่จับคู่สำเร็จ")
            st.dataframe(df_matched, use_container_width=True)
            col1, col2 = st.columns(2)
            with col1:
                st.subheader("❌ Statement ที่เหลือ")
                st.dataframe(df_stmt[~df_stmt.index.isin(matched_records)], use_container_width=True)
            with col2:
                st.subheader("❌ JV ที่เหลือ (Diff)")
                st.dataframe(df_unmatched_jv, use_container_width=True)
