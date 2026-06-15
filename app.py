import streamlit as st
import pandas as pd
import re
from datetime import timedelta

st.set_page_config(layout="wide")
st.title("ระบบจับคู่ Bank Reconciliation (โหมดละเอียดสูง + สรุปยอด)")

date_window = st.number_input("ช่วงเวลาอนุโลม (วัน)", min_value=0, value=3)

col1, col2 = st.columns(2)
with col1:
    stmt_text = st.text_area("1. Statement", height=200, key="stmt_input")
with col2:
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

def find_best_match(target, candidates, max_depth=15):
    candidates = sorted(candidates, key=lambda x: x[1], reverse=True)
    def backtrack(remaining, start_idx, path, depth):
        if abs(remaining) < 0.01: return path
        if depth >= max_depth or start_idx >= len(candidates): return None
        for i in range(start_idx, len(candidates)):
            amt = candidates[i][1]
            if amt <= remaining + 0.01:
                res = backtrack(remaining - amt, i + 1, path + [candidates[i]], depth + 1)
                if res: return res
        return None
    return backtrack(target, 0, [], 0)

if st.button("เริ่มประมวลผล (โหมดละเอียด)"):
    try:
        with st.spinner('กำลังโหลดข้อมูล...'):
            df_s = parse_data(stmt_text)
            df_j = parse_data(jv_text)
        
        if df_s.empty or df_j.empty:
            st.error("ข้อมูลไม่ครบถ้วน")
        else:
            matched = []
            progress_bar = st.progress(0)
            status_text = st.empty()
            total = len(df_s)
            
            for i, (idx, s) in enumerate(df_s.iterrows()):
                percent = int(((i + 1) / total) * 100)
                progress_bar.progress(percent)
                status_text.text(f"กำลังจับคู่รายการที่ {i+1} / {total} ({percent}%)")
                
                cand = df_j[(df_j.Date >= s.Date - timedelta(days=date_window)) & 
                            (df_j.Date <= s.Date + timedelta(days=date_window))]
                
                jv_list = [(idx, row.Amount) for idx, row in cand.iterrows()]
                result = find_best_match(s.Amount, jv_list)
                
                if result:
                    for idx, amt in result:
                        matched.append({"S_Date": s.Date.strftime('%Y-%m-%d'), "S_Amt": s.Amount, 
                                        "J_Date": df_j.loc[idx].Date.strftime('%Y-%m-%d'), "J_Amt": amt})
                        df_j = df_j.drop(idx)
            
            progress_bar.empty()
            status_text.empty()
            st.success("ประมวลผลเสร็จสิ้น!")
            
            # สรุปยอด
            col_a, col_b = st.columns(2)
            with col_a:
                st.subheader("✅ รายการที่จับคู่สำเร็จ")
                df_match = pd.DataFrame(matched)
                st.write(f"**รวมยอดที่จับคู่ได้:** {df_match['J_Amt'].sum():,.2f} บาท")
                st.dataframe(df_match, use_container_width=True)
            with col_b:
                st.subheader("❌ ยอด JV ที่เหลือ (Diff)")
                st.write(f"**รวมยอดคงเหลือ:** {df_j['Amount'].sum():,.2f} บาท")
                st.dataframe(df_j, use_container_width=True)
            
    except Exception as e:
        st.error(f"เกิดข้อผิดพลาด: {e}")
