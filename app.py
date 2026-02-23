import streamlit as st
import pandas as pd
from sqlalchemy import create_engine, text
from datetime import datetime, date, timedelta
import calendar

# ===============================
# CONFIG & DATABASE CONNECTION
# ===============================
st.set_page_config(page_title="Ice Cream Truck Manager", layout="wide")

# Replace SQLite with Supabase Connection
# Ensure your secret is named 'url' under [database] in Streamlit
DB_URL = st.secrets["database"]["url"]

# Workaround for Streamlit/SQLAlchemy postgres prefix issue
if DB_URL.startswith("postgres://"):
    DB_URL = DB_URL.replace("postgres://", "postgresql://", 1)

engine = create_engine(DB_URL, pool_pre_ping=True)
STANDARD_HOURS = 9

# ===============================
# AUTHENTICATION
# ===============================
def check_password():
    def password_entered():
        if (st.session_state["username"] == st.secrets["credentials"]["username"]
            and st.session_state["password"] == st.secrets["credentials"]["password"]):
            st.session_state["password_correct"] = True
            del st.session_state["password"]
            del st.session_state["username"]
        else:
            st.session_state["password_correct"] = False

    if "password_correct" not in st.session_state:
        st.text_input("Username", on_change=password_entered, key="username")
        st.text_input("Password", type="password", on_change=password_entered, key="password")
        return False
    elif not st.session_state["password_correct"]:
        st.text_input("Username", on_change=password_entered, key="username")
        st.text_input("Password", type="password", on_change=password_entered, key="password")
        st.error("😕 User not known or password incorrect")
        return False
    return True

if not check_password():
    st.stop()

# ===============================
# DATABASE INITIALIZATION
# ===============================
def init_db():
    with engine.begin() as conn:
        # PostgreSQL use SERIAL for autoincrement
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS employees (
                id SERIAL PRIMARY KEY,
                name TEXT NOT NULL,
                balance_hours REAL DEFAULT 0
            )
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS attendance (
                id SERIAL PRIMARY KEY,
                employee_id INTEGER REFERENCES employees(id),
                date DATE,
                check_in TEXT,
                check_out TEXT,
                work_hours REAL,
                day_type TEXT
            )
        """))

init_db()

# ===============================
# HELPER FUNCTIONS
# ===============================
def get_employees():
    return pd.read_sql("SELECT * FROM employees", engine)

def update_balance(employee_id, new_balance):
    with engine.begin() as conn:
        conn.execute(text("UPDATE employees SET balance_hours=:bal WHERE id=:id"), 
                     {"bal": new_balance, "id": employee_id})

def calculate_week_hours(employee_id, reference_date=None):
    if reference_date is None:
        reference_date = date.today()
    start_week = reference_date - timedelta(days=reference_date.weekday())
    end_week = start_week + timedelta(days=6)

    query = text("""
        SELECT work_hours FROM attendance 
        WHERE employee_id = :id AND date BETWEEN :start AND :end
    """)
    df = pd.read_sql(query, engine, params={"id": int(employee_id), "start": start_week, "end": end_week})
    return df["work_hours"].sum() if not df.empty else 0

def get_attendance_for_month(employee_id, year, month):
    start_date = date(year, month, 1)
    num_days = calendar.monthrange(year, month)[1]
    end_date = date(year, month, num_days)
    
    query = text("""
        SELECT date, work_hours, day_type FROM attendance 
        WHERE employee_id = :id AND date BETWEEN :start AND :end
    """)
    df = pd.read_sql(query, engine, params={"id": int(employee_id), "start": start_date, "end": end_date})
    return df

# ===============================
# UI
# ===============================
st.title("🍦 Ice Cream Truck Attendance System")
menu = st.sidebar.radio("Navigation", ["Dashboard", "Add Attendance", "Reports", "Add Employee"])

if menu == "Add Employee":
    st.subheader("Add New Employee")
    name = st.text_input("Employee Name")
    if st.button("Add"):
        if name:
            with engine.begin() as conn:
                conn.execute(text("INSERT INTO employees (name) VALUES (:name)"), {"name": name})
            st.success("Employee Added!")
        else: st.warning("Enter name first")

elif menu == "Dashboard":
    st.subheader("📊 Employee Dashboard")
    employees = get_employees()
    if employees.empty:
        st.warning("Add employees first.")
    else:
        for _, emp in employees.iterrows():
            with st.expander(f"👤 {emp['name']}", expanded=True):
                week_hours = calculate_week_hours(emp["id"])
                col1, col2, col3 = st.columns(3)
                col1.metric("Current Balance", f"{round(emp['balance_hours'], 2)} hrs")
                col2.metric("This Week", f"{round(week_hours, 2)} / 54 hrs")
                col3.progress(min(week_hours / 54, 1.0))

                # Calendar Grid Logic
                today = date.today()
                year, month = today.year, today.month
                att_df = get_attendance_for_month(emp["id"], year, month)
                att_df['date'] = pd.to_datetime(att_df['date']).dt.date
                att_dict = dict(zip(att_df["date"], att_df["work_hours"]))

                cols = st.columns(7)
                for i, d in enumerate(["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]):
                    cols[i].write(f"**{d}**")
                
                cal = calendar.monthcalendar(year, month)
                for week in cal:
                    cols = st.columns(7)
                    for i, day in enumerate(week):
                        if day != 0:
                            curr_date = date(year, month, day)
                            hours = att_dict.get(curr_date, None)
                            style = "✅" if hours and hours >= 9 else "⚠️" if hours else ""
                            label = f"{day}\n{f'{hours}h {style}' if hours else ''}"
                            cols[i].info(label)

elif menu == "Add Attendance":
    st.subheader("📝 Daily Attendance Entry")
    employees = get_employees()
    if not employees.empty:
        emp_dict = dict(zip(employees["name"], employees["id"]))
        emp_name = st.selectbox("Select Employee", list(emp_dict.keys()))
        emp_id = emp_dict[emp_name]
        current_emp_balance = employees[employees["id"] == emp_id]["balance_hours"].values[0]

        selected_date = st.date_input("Date", value=date.today())
        day_type = st.selectbox("Day Type", ["Normal", "Event-Truck", "Event-Offsite", "Off"])

        if day_type != "Off":
            st.markdown("### Manual Time Entry")
            t_col1, t_col2 = st.columns(2)
            with t_col1:
                in_h = st.number_input("In Hour", 1, 12, 9)
                in_m = st.number_input("In Min", 0, 59, 0)
                in_ap = st.selectbox("In AM/PM", ["AM", "PM"])
            with t_col2:
                out_h = st.number_input("Out Hour", 1, 12, 6)
                out_m = st.number_input("Out Min", 0, 59, 0)
                out_ap = st.selectbox("Out AM/PM", ["AM", "PM"], index=1)

            def to_24h(h, m, ap):
                if ap == "PM" and h != 12: h += 12
                if ap == "AM" and h == 12: h = 0
                return f"{h:02d}:{m:02d}"

            ci_t = to_24h(in_h, in_m, in_ap)
            co_t = to_24h(out_h, out_m, out_ap)
            
            dt_in = datetime.combine(selected_date, datetime.strptime(ci_t, "%H:%M").time())
            dt_out = datetime.combine(selected_date, datetime.strptime(co_t, "%H:%M").time())
            if dt_out <= dt_in: dt_out += timedelta(days=1)
            work_hours = (dt_out - dt_in).total_seconds() / 3600
            
            st.info(f"⏱️ **Work Hours:** {round(work_hours, 2)}")
            difference = work_hours - STANDARD_HOURS
            
            if st.button("Save Attendance"):
                with engine.begin() as conn:
                    conn.execute(text("""
                        INSERT INTO attendance (employee_id, date, check_in, check_out, work_hours, day_type)
                        VALUES (:eid, :d, :ci, :co, :wh, :dt)
                    """), {"eid": emp_id, "d": selected_date, "ci": ci_t, "co": co_t, "wh": work_hours, "dt": day_type})
                update_balance(emp_id, current_emp_balance + difference)
                st.success("Saved!")
                st.balloons()
        else:
            if st.button("Save Off Day"):
                with engine.begin() as conn:
                    conn.execute(text("INSERT INTO attendance (employee_id, date, work_hours, day_type) VALUES (:eid, :d, 0, 'Off')"),
                                 {"eid": emp_id, "d": selected_date})
                st.success("Off Day Saved!")

elif menu == "Reports":
    st.subheader("Attendance Report")
    employees = get_employees()
    if not employees.empty:
        emp_dict = dict(zip(employees["name"], employees["id"]))
        name = st.selectbox("Employee", list(emp_dict.keys()))
        df = pd.read_sql(text(f"SELECT date, check_in, check_out, work_hours, day_type FROM attendance WHERE employee_id={emp_dict[name]} ORDER BY date DESC"), engine)
        st.dataframe(df)
        st.download_button("Download CSV", df.to_csv(index=False), "report.csv")
