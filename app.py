import streamlit as st
import pandas as pd
import datetime
import calendar

import gspread
from google.oauth2.service_account import Credentials

# ---------------- 설정 ----------------
ADMIN_PASSWORD = st.secrets.get("admin_password", "")
SHEET_URL = st.secrets["sheet_url"]
COLUMNS = ["name", "email", "phone", "date", "tickets", "reservation_time"]

# --------- Google Sheets 연결/유틸 ---------
@st.cache_resource
def get_ws():
    scopes = ["https://www.googleapis.com/auth/spreadsheets"]
    creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scopes)
    gc = gspread.authorize(creds)
    sh = gc.open_by_url(SHEET_URL)
    try:
        ws = sh.worksheet("reservations")
    except gspread.WorksheetNotFound:
        # 탭이 없으면 만들어주고 헤더를 채움
        ws = sh.add_worksheet(title="reservations", rows="1000", cols=str(len(COLUMNS)))
        ws.update("A1:F1", [COLUMNS])
    return ws

def _normalize_df(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame(columns=COLUMNS)
    # 타입 보정
    df["tickets"] = pd.to_numeric(df.get("tickets", 0), errors="coerce").fillna(0).astype(int)
    # 날짜: 문자열(YYYY-MM-DD)로 보관
    df["date"] = pd.to_datetime(df.get("date"), errors="coerce").dt.strftime("%Y-%m-%d")
    # 예약시각: 비면 현재시간
    rt = pd.to_datetime(df.get("reservation_time"), errors="coerce")
    df["reservation_time"] = rt.fillna(pd.Timestamp.now()).dt.strftime("%Y-%m-%d %H:%M:%S")
    # 컬럼 순서 정리
    for c in COLUMNS:
        if c not in df.columns:
            df[c] = ""
    return df[COLUMNS]

def load_reservations() -> pd.DataFrame:
    ws = get_ws()
    # 첫 행을 헤더로 읽기
    rows = ws.get_all_records()
    df = pd.DataFrame(rows)
    return _normalize_df(df)

def save_reservation(new_reservation: dict) -> None:
    ws = get_ws()
    # 헤더 보장
    if ws.row_count == 0:
        ws.update("A1:F1", [COLUMNS])
    values = [
        new_reservation.get("name", ""),
        new_reservation.get("email", ""),
        new_reservation.g_
