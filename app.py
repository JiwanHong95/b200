import streamlit as st
import pandas as pd
import datetime
import os
import calendar

# CSV 파일 경로 설정 및 초기화
CSV_FILE = "reservations.csv"
ADMIN_PASSWORD = "25susehvkdlxld!"

if not os.path.exists(CSV_FILE):
    df = pd.DataFrame(columns=["name", "email", "phone", "date", "tickets", "reservation_time"])
    df.to_csv(CSV_FILE, index=False)

def load_reservations():
    """CSV 파일에서 예약 데이터를 불러오는 함수"""
    return pd.read_csv(CSV_FILE)

def save_reservation(new_reservation):
    """새로운 예약을 CSV 파일에 추가하는 함수"""
    df = load_reservations()
    new_df = pd.DataFrame([new_reservation])
    df = pd.concat([df, new_df], ignore_index=True)
    df.to_csv(CSV_FILE, index=False)
    
def show_user_interface():
    st.title("엘리스 클라우드 B200 예약 서비스")
    st.write("원하시는 날짜와 개수를 선택하고 정보를 남겨주세요.")

    # 8월 31일까지는 예약을 할 수 없도록 min_value 설정
    min_selectable_date = datetime.date(2025, 9, 1)
    max_date = datetime.date(2026, 12, 31)

    # 날짜 선택 (시작일과 종료일)
    reservation_dates = st.date_input(
        "예약 날짜를 선택하세요. (2025년 9월 1일부터 예약 가능)",
        (min_selectable_date, min_selectable_date + datetime.timedelta(days=1)),
        min_value=min_selectable_date,
        max_value=max_date,
        key="date_selector"
    )

    if len(reservation_dates) == 2:
        start_date, end_date = reservation_dates
        st.write(f"선택하신 예약 기간: **{start_date}** 부터 **{end_date}** 까지")
        
        st.subheader("예약자 정보 입력")
        name = st.text_input("이름")
        email = st.text_input("이메일")
        phone = st.text_input("핸드폰 번호")
        
        # 예약 개수 입력 필드
        tickets = st.number_input("예약할 B200 장수를 입력하세요.", min_value=1, step=1, value=1)
        
        # 예약금 확인 체크박스
        deposit_paid = st.checkbox("예약금을 입금했습니까? (입금해야 B200 수량을 확정할 수 있으며, 일정별로 선착순 마감됩니다.)")

        if st.button("예약하기"):
            if name and email and phone and deposit_paid:
                delta = end_date - start_date
                for i in range(delta.days + 1):
                    day = start_date + datetime.timedelta(days=i)
                    
                    new_reservation = {
                        "name": name,
                        "email": email,
                        "phone": phone,
                        "date": day.strftime("%Y-%m-%d"),
                        "tickets": tickets,
                        "reservation_time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    }
                    save_reservation(new_reservation)
                
                st.success(f"**{name}** 님, {start_date}부터 {end_date}까지 총 {tickets}장 예약이 완료되었습니다!")
            else:
                st.warning("모든 정보를 입력하고 예약금 입금을 확인해주세요.")

def show_admin_interface():
    st.title("관리자 페이지")
    
    password = st.text_input("비밀번호를 입력하세요.", type="password")

    if password == ADMIN_PASSWORD:
        df = load_reservations()

        if df.empty:
            st.info("아직 예약된 내역이 없습니다.")
            return

        reservation_counts = df.groupby("date")["tickets"].sum().reset_index()
        reservation_counts["date"] = pd.to_datetime(reservation_counts["date"]).dt.date
        
        st.subheader("일자별 총 예약 개수 (달력뷰)")

        today = datetime.date.today()
        current_year = today.year
        current_month = today.month
        
        year = st.selectbox("연도 선택", range(current_year, 2027), index=current_year - current_year)
        month = st.selectbox("월 선택", range(1, 13), index=current_month - 1)
        
        cal = calendar.Calendar(firstweekday=6) # 일요일부터 시작
        month_days = cal.monthdatescalendar(year, month)

        st.markdown(f"### {year}년 {month}월")

        cols = st.columns(7)
        weekdays = ["일", "월", "화", "수", "목", "금", "토"]
        for col, weekday in zip(cols, weekdays):
            col.write(f"**{weekday}**")

        for week in month_days:
            cols = st.columns(7)
            for col, day in zip(cols, week):
                if day.month == month:
                    day_str = day.strftime("%Y-%m-%d")
                    
                    count = reservation_counts[reservation_counts["date"] == day]["tickets"].sum()
                    
                    if count >= 64:
                        # 64장 이상일 경우 빨간색 배경
                        bg_color = "#ffcccc" 
                        font_color = "red"
                        markdown_text = f"<div style='background-color:{bg_color}; border-radius:5px; padding:5px;'><b>{day.day}</b><br><small><span style='color:{font_color};'>({count}장)</span></small></div>"
                        col.markdown(markdown_text, unsafe_allow_html=True)
                    elif count > 0:
                        # 예약이 있는 날짜는 연두색 배경
                        bg_color = "#c8e6c9"
                        markdown_text = f"<div style='background-color:{bg_color}; border-radius:5px; padding:5px;'><b>{day.day}</b><br><small>({count}장)</small></div>"
                        col.markdown(markdown_text, unsafe_allow_html=True)
                    else:
                        col.write(f"{day.day}")
                else:
                    col.write("")
        
        st.subheader("날짜별 상세 예약 정보")
        if not df.empty:
            sorted_dates = sorted(df['date'].unique())
            selected_date = st.selectbox("상세 정보를 보고 싶은 날짜를 선택하세요.", sorted_dates)
            
            if selected_date:
                st.write(f"**{selected_date}** 예약자 목록")
                reservations_on_date = df[df['date'] == selected_date]
                
                for index, row in reservations_on_date.iterrows():
                    st.write(f"---")
                    st.write(f"**이름**: {row['name']}")
                    st.write(f"**이메일**: {row['email']}")
                    st.write(f"**핸드폰**: {row['phone']}")
                    st.write(f"**예약 개수**: {row['tickets']}장")
                    st.write(f"**예약 시각**: {row['reservation_time']}")

    elif password:
        st.error("비밀번호가 올바르지 않습니다.")

# 메인 앱 로직
st.sidebar.title("메뉴")
app_mode = st.sidebar.radio("모드 선택", ["사용자", "관리자"])

if app_mode == "사용자":
    show_user_interface()
else:
    show_admin_interface()
