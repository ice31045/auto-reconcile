import streamlit as st
import pandas as pd
import re
from datetime import timedelta
import itertools

st.set_page_config(layout="wide")
st.title("ระบบจับคู่ Bank Reconciliation")

date_window = st.number_input("ช่วงเวลาอนุโลม (วัน)", min_value=0, value=3)

col1, col2 = st.columns(2)
with col1:
    # ใส่ key="stmt_input" เพื่อไม่ให้ซ้ำใคร
    stmt_text = st.text_area("1. Statement", height=200, key="stmt_input")
with col2:
    # ใส่ key="jv_input" เพื่อไม่ให้ซ้ำใคร
    jv_text = st.text_area("2. JV", height=200, key="jv_input")

def parse_data(text):
    data = []
    thai_months = {'ม.ค.': '01', 'ก.พ.': '02', 'มี.ค.': '03', 'เม.ย.': '04', 'พ.ค.': '05', 'มิ.ย.': '06', 
                   'ก.ค.': '07', 'ส.ค.': '08', 'ก.ย.': '09', 'ต.ค.': '10', 'พ.ย.': '11', 'ธ.ค.': '12'}
    for row in text.strip().split('\n'):
        row = row.strip()
        if not row: continue
        match = re.search(r'(-?[\d,]+\.?\d*)$', row)
        if not match: continue
        amt = abs(float(re.sub(r'[^\d.]', '', match.group(1))))
        d_str = row.replace(match.group(1), '').strip()
        for th, en in thai_months.items(): d_str = d_str.replace(th, en)
        d_m = re.search(r'(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})', d_str)
        if d_m:
            d, m, y = d_m.groups()
            y = int(y)
            y = y + 2500 - 543 if y < 100 else (y - 543 if y > 2500 else y)
            data.append({"Date": pd.to_datetime(f"{y}-{m}-{d}"), "Amount": amt})
    return pd.DataFrame(data)

if st.button("RUN"):
    try:
        df_s = parse_data(stmt_text)
        df_j = parse_data(jv_text)
        
        matched = []
        for i, s in df_s.iterrows():
            cand = df_j[(df_j.Date >= s.Date - timedelta(days=date_window)) & 
                        (df_j.Date <= s.Date + timedelta(days=date_window))]
            
            found = False
            for j_i, j in cand.iterrows():
                if abs(s.Amount - j.Amount) < 0.01:
                    matched.append({"S_Date": s.Date.strftime('%Y-%m-%d'), "S_Amt": s.Amount, 
                                    "J_Date": j.Date.strftime('%Y-%m-%d'), "J_Amt": j.Amount})
                    df_j = df_j.drop(j_i)
                    found = True; break
            
            if not found:
                for r in range(2, 4):
                    for combo in itertools.combinations(cand.index, r):
                        if abs(s.Amount - df_j.loc[list(combo), 'Amount'].sum()) < 0.01:
                            for idx in combo:
                                matched.append({"S_Date": s.Date.strftime('%Y-%m-%d'), "S_Amt": s.Amount, 
                                                "J_Date": df_j.loc[idx].Date.strftime('%Y-%m-%d'), "J_Amt": df_j.loc[idx].Amount})
                            df_j = df_j.drop(list(combo))
                            found = True; break
                    if found: break

        st.subheader("รายการที่จับคู่ได้")
        st.dataframe(pd.DataFrame(matched), use_container_width=True)
        st.subheader("JV ที่จับคู่ไม่ได้ (Diff)")
        st.dataframe(df_j, use_container_width=True)
        
    except Exception as e:
        st.error(f"ระบบมีปัญหา: {e}")
