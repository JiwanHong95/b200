import streamlit as st
import pandas as pd
import datetime
import calendar

import gspread
from google.oauth2.service_account import Credentials

import traceback
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
        new_reservation.get("phone", ""),
        new_reservation.get("date", ""),
        int(new_reservation.get("tickets", 0)),
        new_reservation.get("reservation_time", ""),
    ]
    ws.append_row(values, value_input_option="USER_ENTERED")

# --------------- 사용자 UI ---------------
def show_user_interface():
    st.title("엘리스 클라우드 B200 예약 서비스")
    st.write("원하시는 날짜와 개수를 선택하고 정보를 남겨주세요.")

    # 2025-09-22부터 신청 가능
    min_selectable_date = datetime.date(2025, 9, 22)   # ← 9/22부터
    max_date = datetime.date(2026, 12, 31)             # ← 이 줄이 꼭 필요!
    
    reservation_dates = st.date_input(
        "예약 날짜를 선택하세요. (2025년 9월 22일부터 예약 가능)",
        (min_selectable_date, min_selectable_date + datetime.timedelta(days=1)),
        min_value=min_selectable_date,
        max_value=max_date,
        key="date_selector"
    )



    if isinstance(reservation_dates, tuple) and len(reservation_dates) == 2:
        start_date, end_date = reservation_dates
        st.write(f"선택하신 예약 기간: **{start_date}** 부터 **{end_date}** 까지")

        st.subheader("예약자 정보 입력")
        name = st.text_input("이름")
        email = st.text_input("이메일")
        phone = st.text_input("핸드폰 번호")
        tickets = st.number_input("예약할 B200 장수를 입력하세요.", min_value=1, step=1, value=1)
        deposit_paid = st.checkbox("예약금을 입금했습니까? (입금해야 B200 수량을 확정할 수 있으며, 일정별로 선착순 마감됩니다.)")
        if not deposit_paid:
            st.info(
                "아직 예약금을 입금하지 않으셨다면 **세금계산서 발행 및 입금 안내**를 위해 "
                "**jiwan.hong@elicer.com** 으로 연락해주세요.\n\n"
                "입금 계좌: **기업은행 065-151413-04-079 (예금주: (주)엘리스그룹)**"
            )

        if st.button("예약하기"):
            if name and email and phone and deposit_paid:
                try:
                    delta = end_date - start_date
                    for i in range(delta.days + 1):
                        day = start_date + datetime.timedelta(days=i)
                        save_reservation({
                            "name": name,
                            "email": email,
                            "phone": phone,
                            "date": day.strftime("%Y-%m-%d"),
                            "tickets": int(tickets),
                            "reservation_time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        })
                    st.success(f"**{name}** 님, {start_date}부터 {end_date}까지 총 {tickets}장 예약이 완료되었습니다!")
                except Exception as e:
                    st.error(f"저장 실패: {e}")
            else:
                st.warning("모든 정보를 입력하고 예약금 입금을 확인해주세요.")

# --------------- 관리자 UI ---------------
def show_admin_interface():
    st.title("관리자 페이지")
    password = st.text_input("비밀번호를 입력하세요.", type="password")

    if password == ADMIN_PASSWORD:
        try:
            df = load_reservations()
        except Exception as e:
            st.error(f"시트 읽기 실패: {e}")
            return

        if df.empty:
            st.info("아직 예약된 내역이 없습니다.")
            return

        # 집계용 변환
        df["tickets"] = pd.to_numeric(df["tickets"], errors="coerce").fillna(0).astype(int)
        df["date"] = pd.to_datetime(df["date"], errors="coerce").dt.date
        reservation_counts = df.groupby("date", as_index=False)["tickets"].sum()

        st.subheader("일자별 총 예약 개수 (달력뷰)")
        today = datetime.date.today()
        current_year = today.year
        current_month = today.month

        year = st.selectbox("연도 선택", range(current_year, 2027), index=0)
        month = st.selectbox("월 선택", range(1, 13), index=current_month - 1)

        cal = calendar.Calendar(firstweekday=6)  # 일요일부터
        month_days = cal.monthdatescalendar(year, month)

        st.markdown(f"### {year}년 {month}월")

        cols = st.columns(7)
        for col, weekday in zip(cols, ["일", "월", "화", "수", "목", "금", "토"]):
            col.write(f"**{weekday}**")

        for week in month_days:
            cols = st.columns(7)
            for col, day in zip(cols, week):
                if day.month != month:
                    col.write("")
                    continue

                day_count = reservation_counts.loc[reservation_counts["date"] == day, "tickets"]
                count = int(day_count.iloc[0]) if not day_count.empty else 0

                if count >= 64:
                    bg_color = "#ffcccc"; font_color = "red"
                    html = f"<div style='background-color:{bg_color}; border-radius:5px; padding:5px;'><b>{day.day}</b><br><small><span style='color:{font_color};'>({count}장)</span></small></div>"
                    col.markdown(html, unsafe_allow_html=True)
                elif count > 0:
                    bg_color = "#c8e6c9"
                    html = f"<div style='background-color:{bg_color}; border-radius:5px; padding:5px;'><b>{day.day}</b><br><small>({count}장)</small></div>"
                    col.markdown(html, unsafe_allow_html=True)
                else:
                    col.write(f"{day.day}")

        st.subheader("날짜별 상세 예약 정보")
        sorted_dates = sorted({d.strftime("%Y-%m-%d") for d in df["date"]})
        selected_date = st.selectbox("상세 정보를 보고 싶은 날짜를 선택하세요.", sorted_dates)
        if selected_date:
            st.write(f"**{selected_date}** 예약자 목록")
            target = pd.to_datetime(selected_date).date()
            for _, row in df[df["date"] == target].iterrows():
                st.write("---")
                st.write(f"**이름**: {row['name']}")
                st.write(f"**이메일**: {row['email']}")
                st.write(f"**핸드폰**: {row['phone']}")
                st.write(f"**예약 개수**: {int(row['tickets'])}장")
                st.write(f"**예약 시각**: {row['reservation_time']}")

    elif password:
        st.error("비밀번호가 올바르지 않습니다.")

# --------------- 메인 ---------------
st.sidebar.title("메뉴")
mode = st.sidebar.radio("모드 선택", ["사용자", "관리자"])
if mode == "사용자":
    show_user_interface()
else:
    show_admin_interface()
