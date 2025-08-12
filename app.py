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

# 사용자/관리자 공통 색 구간
# - 초록: 0~24장 (여유)
# - 주황: 25~32장 (거의 마감)  ※ 24까지는 초록으로 처리
# - 빨강: 32장 초과 (예약 불가)
LOW_MAX = 24
MID_MAX = 32

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

# ---- 집계 및 색상 도우미 ----
def get_counts_by_date(df: pd.DataFrame) -> pd.DataFrame:
    """date(날짜형)별 총 tickets를 반환"""
    out = df.copy()
    if out.empty:
        return pd.DataFrame(columns=["date", "tickets"])
    out["tickets"] = pd.to_numeric(out["tickets"], errors="coerce").fillna(0).astype(int)
    out["date"] = pd.to_datetime(out["date"], errors="coerce").dt.date
    return out.groupby("date", as_index=False)["tickets"].sum()

def color_for_count(n: int) -> str:
    """개수에 따른 배경색 반환(사용자/관리자 공통)"""
    if n == 0:
        return "#f3f4f6"  # 매우 옅은 회색(데이터 없음과 구분 용이)
    if n <= LOW_MAX:
        return "#c8e6c9"  # 초록(여유)
    if n <= MID_MAX:
        return "#ffe6b3"  # 주황(거의 마감)
    return "#ffcccc"      # 빨강(예약 불가)

# ---- 사용자용 달력(색만 표시, 숫자 미노출) ----
def render_user_calendar(counts_df: pd.DataFrame):
    st.subheader("달력 보기 (예약 현황 색상 안내)")
    # 범례
    st.markdown(
        """
        <div style="display:flex;gap:12px;align-items:center;flex-wrap:wrap;margin-bottom:8px;">
          <span style="display:inline-flex;align-items:center;gap:6px;">
            <span style="display:inline-block;width:14px;height:14px;background:#c8e6c9;border:1px solid #b3dcb6;border-radius:3px;"></span>
            <small>여유 (0–24장)</small>
          </span>
          <span style="display:inline-flex;align-items:center;gap:6px;">
            <span style="display:inline-block;width:14px;height:14px;background:#ffe6b3;border:1px solid #f4d28e;border-radius:3px;"></span>
            <small>거의 마감 (25–32장)</small>
          </span>
          <span style="display:inline-flex;align-items:center;gap:6px;">
            <span style="display:inline-block;width:14px;height:14px;background:#ffcccc;border:1px solid #f3a7a7;border-radius:3px;"></span>
            <small>예약 불가 (32장 초과)</small>
          </span>
        </div>
        """,
        unsafe_allow_html=True
    )

    # 월 선택 (기본: 이번 달)
    today = datetime.date.today()
    year = st.selectbox("연도 선택", range(today.year, today.year + 2), index=0, key="user_year")
    month = st.selectbox("월 선택", range(1, 13), index=today.month - 1, key="user_month")

    cal = calendar.Calendar(firstweekday=6)  # 일요일부터 시작
    month_days = cal.monthdatescalendar(year, month)

    st.markdown(f"### {year}년 {month}월")
    cols = st.columns(7)
    for col, weekday in zip(cols, ["일", "월", "화", "수", "목", "금", "토"]):
        col.write(f"**{weekday}**")

    for week in month_days:
        cols = st.columns(7)
        for col, day in zip(cols, week):
            if day.month != month:
                col.write("")  # 다른 달 날짜는 비움
                continue
            # 해당 날짜의 예약 수
            row = counts_df.loc[counts_df["date"] == day, "tickets"]
            count = int(row.iloc[0]) if not row.empty else 0
            bg = color_for_count(count)
            html = (
                f"<div style='background:{bg};border-radius:8px;padding:10px;text-align:center;"
                f"border:1px solid rgba(0,0,0,0.06);'><b>{day.day}</b></div>"
            )
            # 사용자 달력은 "색만" 보여주므로 숫자/상세는 표시하지 않음
            col.markdown(html, unsafe_allow_html=True)

    st.caption("※ 색상만으로 상태를 표시합니다. 초록=여유, 주황=거의 마감, 빨강=예약 불가")

# --------------- 사용자 UI ---------------
def show_user_interface():
    st.title("엘리스 클라우드 B200 예약 서비스")
    st.write("원하시는 날짜와 개수를 선택하고 정보를 남겨주세요.")

    # 상단 달력(색상만) 먼저 렌더링
    try:
        df_all = load_reservations()
        counts_df = get_counts_by_date(df_all)
    except Exception as e:
        counts_df = pd.DataFrame(columns=["date", "tickets"])
        st.warning(f"달력 데이터를 불러오지 못했습니다: {e}")
    render_user_calendar(counts_df)

    # 2025-09-22부터 신청 가능
    min_selectable_date = datetime.date(2025, 9, 22)
    max_date = datetime.date(2026, 12, 31)

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
                bg_color = color_for_count(count)
                # 관리자 화면은 숫자도 함께 표시
                if count > 0:
                    html = (
                        f"<div style='background:{bg_color}; border-radius:8px; padding:8px; "
                        f"border:1px solid rgba(0,0,0,0.06); text-align:center;'>"
                        f"<b>{day.day}</b><br><small>({count}장)</small></div>"
                    )
                else:
                    html = (
                        f"<div style='background:{bg_color}; border-radius:8px; padding:8px; "
                        f"border:1px solid rgba(0,0,0,0.06); text-align:center;'>"
                        f"<b>{day.day}</b></div>"
                    )
                col.markdown(html, unsafe_allow_html=True)

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
