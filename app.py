import streamlit as st
import pandas as pd
import re
from datetime import timedelta
import itertools

st.set_page_config(page_title="Auto Reconcile", layout="wide")
st.title("ระบบจับคู่ Bank Reconciliation อัตโนมัติ")

date_window = st.number_input("จำนวนวันที่อนุโลม (บวกลบ ไม่เกิน X วัน)", min_value=0, value=3)

col1, col2 = st.columns(2)
with col1:
    stmt_text = st.text_area("1. วางข้อมูล Statement", height=200, key="s1")
with col2:
    jv_text = st.text_area("2. วางข้อมูล JV", height=200, key="j1")

def parse_data(text):
    data = []
    thai_months = {'ม.ค.': '01', 'ก.พ.': '02', 'มี.ค.': '03', 'เม.ย.': '04', 'พ.ค.': '05', 'มิ.ย.': '06', 
                   'ก.ค.': '07', 'ส.ค.': '08', 'ก.ย.': '09', 'ต.ค.': '10', 'พ.ย.': '11', 'ธ.ค.': '12'}
    for row in text.strip().split('\n'):
        match = re.search(r'(-?[\d,]+\.?\d*)$', row.strip())
        if not match: continue
        amt = abs(float(re.sub(r'[^\d.]', '', match.group(1))))
        date_str = row.replace(match.group(1), '').strip()
        for th, en in thai_months.items(): date_str = date_str.replace(th, en)
        d_m = re.search(r'(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})', date_str)
        if d_m:
            d, m, y = d_m.groups()
            y = int(y)
            y = y + 2500 - 543 if y < 100 else (y - 543 if y > 2500 else y)
            data.append({"Date": pd.to_datetime(f"{y}-{m}-{d}"), "Amount": amt, "Raw": row})
    return pd.DataFrame(data)

if st.button("ประมวลผล"):
    try:
        df_s = parse_data(stmt_text)
        df_j = parse_data(jv_text)
        matched = []
        
        for i, s in df_s.iterrows():
            cand = df_j[(df_j.Date >= s.Date - timedelta(days=date_window)) & (df_j.Date <= s.Date + timedelta(days=date_window))]
            # 1-to-1
            found = False
            for j_i, j in cand.iterrows():
                if abs(s.Amount - j.Amount) < 0.01:
                    matched.append({"S_Date": s.Date, "S_Amt": s.Amount, "J_Date": j.Date, "J_Amt": j.Amount})
                    df_j = df_j.drop(j_i)
                    found = True; break
            # Many-to-1
            if not found:
                jv_map = {idx: r.Amount for idx, r in cand[cand.Amount <= s.Amount].iterrows()}
                for r in range(2, 4):
                    for combo in itertools.combinations(jv_map.keys(), r):
                        if abs(s.Amount - sum(jv_map[i] for i in combo)) < 0.01:
                            for idx in combo:
                                matched.append({"S_Date": s.Date, "S_Amt": s.Amount, "J_Date": df_j.loc[idx].Date, "J_Amt": df_j.loc[idx].Amount})
                            df_j = df_j.drop(list(combo))
                            found = True; break
                    if found: break
        
        st.subheader("ผลลัพธ์")
        st.dataframe(pd.DataFrame(matched))
        st.subheader("Statement ที่เหลือ")
        st.dataframe(df_s[~df_s.index.isin([i for i in df_s.index if any(m['S_Date'] == df_s.loc[i].Date for m in matched)])])
        st.subheader("JV ที่เหลือ (Diff)")
        st.dataframe(df_j)
    except Exception as e:
        st.error(f"เกิดข้อผิดพลาด: {e}")
