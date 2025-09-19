import streamlit as st
import pandas as pd
import datetime
import calendar

import gspread
from google.oauth2.service_account import Credentials

# ---------------- 설정 ----------------
ADMIN_PASSWORD = st.secrets.get("admin_password", "")
SHEET_URL = st.secrets["sheet_url"]
# 시트 컬럼(시간 컬럼 추가!)
COLUMNS = ["name", "email", "phone", "date", "tickets", "start_time", "end_time", "reservation_time"]

# 예약 오픈일(이전 날짜는 사용자 달력에서 회색 처리)
OPEN_DATE = datetime.date(2025, 10, 1)

# 색 기준(공통)
# - 초록: 0~22장 (여유)
# - 주황: 23~32장 (마감 임박)
# - 빨강: 32장 초과 (예약 불가)
LOW_MAX = 22
MID_MAX = 32
GREY_BG = "#e5e7eb"  # 오픈 전 회색

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
        ws = sh.add_worksheet(title="reservations", rows="1000", cols=str(len(COLUMNS)))
        ws.update("A1", [COLUMNS])  # 헤더 생성
        return ws
    # 헤더 보정(새 컬럼 반영)
    try:
        header = ws.row_values(1)
    except Exception:
        header = []
    if header != COLUMNS:
        ws.update("A1", [COLUMNS])
    return ws

def _normalize_df(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame(columns=COLUMNS)
    # 누락 컬럼 채우기
    for c in COLUMNS:
        if c not in df.columns:
            df[c] = ""
    # 타입 보정
    df["tickets"] = pd.to_numeric(df["tickets"], errors="coerce").fillna(0).astype(int)
    df["date"] = pd.to_datetime(df["date"], errors="coerce").dt.strftime("%Y-%m-%d")
    # 예약시각: 비면 현재시간
    rt = pd.to_datetime(df["reservation_time"], errors="coerce")
    df["reservation_time"] = rt.fillna(pd.Timestamp.now()).dt.strftime("%Y-%m-%d %H:%M:%S")
    return df[COLUMNS]

def load_reservations() -> pd.DataFrame:
    ws = get_ws()
    rows = ws.get_all_records()
    df = pd.DataFrame(rows)
    return _normalize_df(df)

def save_reservation(new_reservation: dict) -> None:
    ws = get_ws()
    values = [
        new_reservation.get("name", ""),
        new_reservation.get("email", ""),
        new_reservation.get("phone", ""),
        new_reservation.get("date", ""),
        int(new_reservation.get("tickets", 0)),
        new_reservation.get("start_time", ""),
        new_reservation.get("end_time", ""),
        new_reservation.get("reservation_time", ""),
    ]
    ws.append_row(values, value_input_option="USER_ENTERED")

# ---- 집계/색상 도우미 ----
def get_counts_by_date(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    if out.empty:
        return pd.DataFrame(columns=["date", "tickets"])
    out["tickets"] = pd.to_numeric(out["tickets"], errors="coerce").fillna(0).astype(int)
    out["date"] = pd.to_datetime(out["date"], errors="coerce").dt.date
    return out.groupby("date", as_index=False)["tickets"].sum()

def color_for_count(n: int) -> str:
    # 요청: 0건도 초록색(여유)
    if n <= LOW_MAX:
        return "#c8e6c9"   # 초록
    if n <= MID_MAX:
        return "#ffe6b3"   # 주황
    return "#ffcccc"       # 빨강

def normalize_phone(s) -> str:
    return "".join(ch for ch in str(s) if ch.isdigit())

# ---- 사용자: 예약 현황 안내(달력) ----
def page_calendar():
    st.title("예약 현황 안내")

    try:
        df = load_reservations()
        counts_df = get_counts_by_date(df)
    except Exception as e:
        counts_df = pd.DataFrame(columns=["date", "tickets"])
        st.warning(f"달력 데이터를 불러오지 못했습니다: {e}")

    # 범례
    st.markdown(
        """
        <div style="display:flex;gap:12px;align-items:center;flex-wrap:wrap;margin-bottom:8px;">
          <span style="display:inline-flex;align-items:center;gap:6px;">
            <span style="display:inline-block;width:14px;height:14px;background:#c8e6c9;border:1px solid #b3dcb6;border-radius:3px;"></span>
            <small>여유</small>
          </span>
          <span style="display:inline-flex;align-items:center;gap:6px;">
            <span style="display:inline-block;width:14px;height:14px;background:#ffe6b3;border:1px solid #f4d28e;border-radius:3px;"></span>
            <small>마감 임박</small>
          </span>
          <span style="display:inline-flex;align-items:center;gap:6px;">
            <span style="display:inline-block;width:14px;height:14px;background:#ffcccc;border:1px solid #f3a7a7;border-radius:3px;"></span>
            <small>예약 불가</small>
          </span>
          <span style="display:inline-flex;align-items:center;gap:6px;">
            <span style="display:inline-block;width:14px;height:14px;background:#e5e7eb;border:1px solid #d1d5db;border-radius:3px;"></span>
            <small>예약 오픈 전 (9/21 이전)</small>
          </span>
        </div>
        """,
        unsafe_allow_html=True
    )

    today = datetime.date.today()
    year = st.selectbox("연도 선택", range(today.year, today.year + 2), index=0, key="user_year")
    month = st.selectbox("월 선택", range(1, 13), index=today.month - 1, key="user_month")

    cal = calendar.Calendar(firstweekday=6)  # 일요일 시작
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

            # 오픈 이전 날짜는 무조건 회색
            if day < OPEN_DATE:
                bg = GREY_BG
            else:
                row = counts_df.loc[counts_df["date"] == day, "tickets"]
                count = int(row.iloc[0]) if not row.empty else 0
                bg = color_for_count(count)

            html = (
                f"<div style='background:{bg};border-radius:8px;padding:10px;text-align:center;"
                f"border:1px solid rgba(0,0,0,0.06);'><b>{day.day}</b></div>"
            )
            col.markdown(html, unsafe_allow_html=True)


# ---- 사용자: B200 예약하기(폼) ----
def page_booking():
    st.title("B200 예약하기")
    st.write("원하시는 날짜와 **시간** 및 개수를 선택하고 정보를 남겨주세요.")

    min_selectable_date = OPEN_DATE
    max_date = datetime.date(2025, 10, 29)

    reservation_dates = st.date_input(
        "예약 날짜를 선택하세요. (2025년 10월 1일부터 예약 가능)",
        (min_selectable_date, min_selectable_date + datetime.timedelta(days=1)),
        min_value=min_selectable_date,
        max_value=max_date,
        key="date_selector"
    )

    # 시간 선택 추가
    st.subheader("사용 시간 선택")
    start_time = st.time_input("시작 시간", value=datetime.time(9, 0), key="use_start")
    end_time = st.time_input("종료 시간", value=datetime.time(18, 0), key="use_end")

    if isinstance(reservation_dates, tuple) and len(reservation_dates) == 2:
        start_date, end_date = reservation_dates
        st.write(f"선택하신 예약 기간: **{start_date}** 부터 **{end_date}** 까지")
        if end_time <= start_time:
            st.warning("종료 시간이 시작 시간보다 커야 합니다.")

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
            if name and email and phone and deposit_paid and end_time > start_time:
                try:
                    delta = end_date - start_date
                    stime = start_time.strftime("%H:%M")
                    etime = end_time.strftime("%H:%M")
                    nowstr = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    for i in range(delta.days + 1):
                        day = start_date + datetime.timedelta(days=i)
                        save_reservation({
                            "name": name,
                            "email": email,
                            "phone": phone,
                            "date": day.strftime("%Y-%m-%d"),
                            "tickets": int(tickets),
                            "start_time": stime,
                            "end_time": etime,
                            "reservation_time": nowstr,
                        })
                    st.success(f"**{name}** 님, {start_date}~{end_date} / {stime}–{etime}에 {tickets}장 예약이 완료되었습니다!")
                except Exception as e:
                    st.error(f"저장 실패: {e}")
            else:
                st.warning("모든 정보를 입력하고, 예약금 입금 및 시간 선택을 확인해 주세요.")

# ---- 사용자: 내 예약 확인(휴대폰 번호로 조회) ----
def page_my_reservations():
    st.title("내 예약 확인")
    st.write("예약 신청 시 입력한 **휴대폰 번호**로 본인 예약 내역을 확인합니다.")

    phone_input = st.text_input("휴대폰 번호를 입력하세요 (예: 010-1234-5678 또는 숫자만)")
    if st.button("내 예약 조회"):
        try:
            df = load_reservations()
            if df.empty:
                st.info("등록된 예약이 없습니다.")
                return

            # 번호 정규화 후 비교
            df["phone_norm"] = df["phone"].apply(normalize_phone)
            target = normalize_phone(phone_input)

            mine = df[df["phone_norm"] == target].copy()
            if mine.empty:
                st.warning("해당 번호로 등록된 예약을 찾지 못했습니다. 번호를 다시 확인해 주세요.")
                return

            mine["date"] = pd.to_datetime(mine["date"]).dt.date

            # 동일한 신청 시각(=한 번에 신청한 건)을 하나로 묶어 기간 계산
            grouped = (mine
                       .groupby(["reservation_time", "tickets"], as_index=False)
                       .agg(start_date=("date", "min"), end_date=("date", "max"))
                       .sort_values("start_date"))

            st.success(f"총 {len(grouped)}건의 예약을 찾았습니다.")
            for _, row in grouped.iterrows():
                st.write("---")
                st.write(f"**사용 기간**: {row['start_date']} ~ {row['end_date']}")
                st.write(f"**장수**: {int(row['tickets'])}장")

        except Exception as e:
            st.error(f"조회 실패: {e}")

# --------------- 관리자 UI ---------------
def show_admin_interface():
    st.title("관리자 페이지")
    try:
        df = load_reservations()
    except Exception as e:
        st.error(f"시트 읽기 실패: {e}")
        return

    if df.empty:
        st.info("아직 예약된 내역이 없습니다.")
        return

    df["tickets"] = pd.to_numeric(df["tickets"], errors="coerce").fillna(0).astype(int)
    df["date"] = pd.to_datetime(df["date"], errors="coerce").dt.date
    reservation_counts = df.groupby("date", as_index=False)["tickets"].sum()

    st.subheader("일자별 총 예약 개수 (달력뷰)")
    today = datetime.date.today()
    current_year = today.year
    current_month = today.month

    year = st.selectbox("연도 선택", range(current_year, 2027), index=0)
    month = st.selectbox("월 선택", range(1, 13), index=current_month - 1)

    cal = calendar.Calendar(firstweekday=6)
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
            st.write(f"**시간**: {row.get('start_time','')} ~ {row.get('end_time','')}")
            st.write(f"**예약 시각**: {row['reservation_time']}")

# --------------- 사이드바 / 라우팅 ---------------
st.sidebar.title("메뉴")

# 사용자 메뉴(세 페이지) + 내 예약 확인
page = st.sidebar.radio("원하는 기능을 선택하세요", ["예약 현황 안내", "B200 예약하기", "내 예약 확인"], index=0)

# 좌측 하단: 관리자 모드(별도)
st.sidebar.divider()
with st.sidebar.expander("관리자 모드", expanded=False):
    pw = st.text_input("비밀번호", type="password", key="admin_pw_sidebar")
    go_admin = st.button("접속하기", key="admin_login_btn")
    if go_admin and pw == ADMIN_PASSWORD:
        st.session_state["admin_authenticated"] = True
    elif go_admin and pw != ADMIN_PASSWORD:
        st.session_state["admin_authenticated"] = False
        st.sidebar.error("비밀번호가 올바르지 않습니다.")

if st.session_state.get("admin_authenticated"):
    show_admin_interface()
else:
    if page == "예약 현황 안내":
        page_calendar()
    elif page == "B200 예약하기":
        page_booking()
    else:
        page_my_reservations()
