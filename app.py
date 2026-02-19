import streamlit as st
import sqlite3
from datetime import datetime, date, timedelta
import pandas as pd

# ===============================
# CONFIG
# ===============================
st.set_page_config(page_title="Ice Cream Truck Manager", layout="wide")

DB_NAME = "icecream_attendance.db"
STANDARD_HOURS = 9

# ===============================
# AUTHENTICATION
# ===============================
def check_password():
    """Returns `True` if the user had the correct password."""

    def password_entered():
        """Checks whether a password entered by the user is correct."""
        if (
            st.session_state["username"] == st.secrets["credentials"]["username"]
            and st.session_state["password"] == st.secrets["credentials"]["password"]
        ):
            st.session_state["password_correct"] = True
            del st.session_state["password"]  # don't store password
            del st.session_state["username"]
        else:
            st.session_state["password_correct"] = False

    if "password_correct" not in st.session_state:
        # First run, show inputs for username + password.
        st.text_input("Username", on_change=password_entered, key="username")
        st.text_input(
            "Password", type="password", on_change=password_entered, key="password"
        )
        return False
    elif not st.session_state["password_correct"]:
        # Password not correct, show input + error.
        st.text_input("Username", on_change=password_entered, key="username")
        st.text_input(
            "Password", type="password", on_change=password_entered, key="password"
        )
        st.error("😕 User not known or password incorrect")
        return False
    else:
        # Password correct.
        return True

if not check_password():
    st.stop()

# ===============================
# DATABASE
# ===============================
def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()

    # Employees
    c.execute("""
        CREATE TABLE IF NOT EXISTS employees (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            balance_hours REAL DEFAULT 0
        )
    """)

    # Attendance
    c.execute("""
        CREATE TABLE IF NOT EXISTS attendance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            employee_id INTEGER,
            date TEXT,
            check_in TEXT,
            check_out TEXT,
            work_hours REAL,
            day_type TEXT,
            FOREIGN KEY (employee_id) REFERENCES employees (id)
        )
    """)

    conn.commit()
    conn.close()

def get_connection():
    return sqlite3.connect(DB_NAME)

init_db()

# ===============================
# HELPER FUNCTIONS
# ===============================
def get_employees():
    conn = get_connection()
    df = pd.read_sql("SELECT * FROM employees", conn)
    conn.close()
    return df

def update_balance(employee_id, new_balance):
    conn = get_connection()
    conn.execute("UPDATE employees SET balance_hours=? WHERE id=?",
                 (new_balance, employee_id))
    conn.commit()
    conn.close()

def calculate_week_hours(employee_id, reference_date=None):
    if reference_date is None:
        reference_date = date.today()
    conn = get_connection()
    # Find start of week (Monday)
    start_week = reference_date - timedelta(days=reference_date.weekday())
    end_week = start_week + timedelta(days=6)

    df = pd.read_sql(f"""
        SELECT work_hours FROM attendance
        WHERE employee_id={employee_id}
        AND date BETWEEN '{start_week}' AND '{end_week}'
    """, conn)

    conn.close()
    return df["work_hours"].sum() if not df.empty else 0

def get_attendance_for_month(employee_id, year, month):
    conn = get_connection()
    start_date = date(year, month, 1)
    if month == 12:
        end_date = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        end_date = date(year, month + 1, 1) - timedelta(days=1)
    
    df = pd.read_sql(f"""
        SELECT date, work_hours, day_type FROM attendance
        WHERE employee_id={employee_id}
        AND date BETWEEN '{start_date}' AND '{end_date}'
    """, conn)
    conn.close()
    return df

# ===============================
# UI
# ===============================
st.title("🍦 Ice Cream Truck Attendance System")

menu = st.sidebar.radio("Navigation", ["Dashboard", "Add Attendance", "Reports", "Add Employee"])

# ===============================
# ADD EMPLOYEE
# ===============================
if menu == "Add Employee":
    st.subheader("Add New Employee")
    name = st.text_input("Employee Name")

    if st.button("Add"):
        if name:
            conn = get_connection()
            conn.execute("INSERT INTO employees (name) VALUES (?)", (name,))
            conn.commit()
            conn.close()
            st.success("Employee Added!")
        else:
            st.warning("Enter name first")

# ===============================
# DASHBOARD
# ===============================
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
                progress = min(week_hours / 54, 1.0)
                col3.write("Weekly Progress")
                col3.progress(progress)

                st.markdown("#### 📅 Attendance Calendar")
                
                # Simple Calendar Grid
                today = date.today()
                year, month = today.year, today.month
                
                # Get attendance data
                att_df = get_attendance_for_month(emp["id"], year, month)
                att_dict = dict(zip(att_df["date"], att_df["work_hours"]))
                
                # Calendar Header
                cols = st.columns(7)
                days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
                for i, d in enumerate(days):
                    cols[i].write(f"**{d}**")
                
                # Calendar Days
                first_day = date(year, month, 1)
                start_pad = first_day.weekday() # 0 = Mon
                
                import calendar
                num_days = calendar.monthrange(year, month)[1]
                
                current_day = 1
                for week in range(6):
                    cols = st.columns(7)
                    for day_idx in range(7):
                        if (week == 0 and day_idx < start_pad) or current_day > num_days:
                            cols[day_idx].write("")
                        else:
                            d_str = str(date(year, month, current_day))
                            hours = att_dict.get(d_str, None)
                            
                            style = ""
                            if hours is not None:
                                if hours >= 9:
                                    style = "✅"
                                else:
                                    style = "⚠️"
                            
                            label = f"{current_day}"
                            if hours is not None:
                                label += f"\n{hours}h {style}"
                            
                            cols[day_idx].info(label)
                            current_day += 1
                    if current_day > num_days:
                        break
            st.divider()

# ===============================
# ADD ATTENDANCE
# ===============================
elif menu == "Add Attendance":
    st.subheader("📝 Daily Attendance Entry")

    employees = get_employees()
    if employees.empty:
        st.warning("Add employees first.")
    else:
        emp_dict = dict(zip(employees["name"], employees["id"]))
        emp_name = st.selectbox("Select Employee", emp_dict.keys())
        # Use a key to prevent form reset issues logic if needed, but selectbox is usually fine
        emp_id = emp_dict[emp_name]
        current_emp_balance = employees[employees["id"] == emp_id]["balance_hours"].values[0]

        selected_date = st.date_input("Date", value=date.today())
        day_type = st.selectbox("Day Type",
                                ["Normal", "Event-Truck", "Event-Offsite", "Off"])

        if day_type != "Off":
            st.markdown("### Manual Time Entry")
            t_col1, t_col2 = st.columns(2)
            
            with t_col1:
                st.write("**Check In**")
                in_h = st.number_input("In Hour", 1, 12, 9, key="in_h")
                in_m = st.number_input("In Min", 0, 59, 0, key="in_m")
                in_ap = st.selectbox("In AM/PM", ["AM", "PM"], key="in_ap")
            
            with t_col2:
                st.write("**Check Out**")
                out_h = st.number_input("Out Hour", 1, 12, 6, key="out_h")
                out_m = st.number_input("Out Min", 0, 59, 0, key="out_m")
                out_ap = st.selectbox("Out AM/PM", ["AM", "PM"], index=1, key="out_ap")

            # Helper to convert to 24h
            def to_24h(h, m, ap):
                if ap == "PM" and h != 12: h += 12
                if ap == "AM" and h == 12: h = 0
                return h, m

            h_in, m_in = to_24h(in_h, in_m, in_ap)
            h_out, m_out = to_24h(out_h, out_m, out_ap)
            
            check_in_time = f"{h_in:02d}:{m_in:02d}"
            check_out_time = f"{h_out:02d}:{m_out:02d}"
            
            dt_in = datetime.combine(selected_date, datetime.strptime(check_in_time, "%H:%M").time())
            dt_out = datetime.combine(selected_date, datetime.strptime(check_out_time, "%H:%M").time())
            
            if dt_out <= dt_in:
                dt_out += timedelta(days=1)
                
            work_hours = (dt_out - dt_in).total_seconds() / 3600
            
            st.info(f"⏱️ **Hours to be submitted:** {round(work_hours, 2)} hours")
            
            difference = work_hours - STANDARD_HOURS
            can_submit = True
            
            if difference < 0:
                shortage = abs(difference)
                st.warning(f"⚠️ Shortage: {round(shortage, 2)} hours. Current Balance: {round(current_emp_balance, 2)} hours.")
                if current_emp_balance < shortage:
                    st.error("🚨 Cannot submit: Insufficient balance hours to cover the shortage.")
                    can_submit = False
                else:
                    st.success(f"✅ Balance is sufficient. {round(shortage, 2)} hours will be deducted.")
            elif difference > 0:
                excess = difference
                st.success(f"✨ Excess: {round(excess, 2)} hours will be added to balance.")
            else:
                st.write("Target of 9 hours met exactly.")

            if st.button("Save Attendance", disabled=not can_submit):
                conn = get_connection()
                new_balance = current_emp_balance + difference
                
                update_balance(emp_id, new_balance)

                conn.execute("""
                    INSERT INTO attendance (employee_id, date, check_in, check_out, work_hours, day_type)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (emp_id, str(selected_date), check_in_time,
                      check_out_time, work_hours, day_type))

                conn.commit()
                conn.close()
                st.success("Attendance Saved Successfully!")
                st.balloons()
        else:
            if st.button("Save Off Day"):
                conn = get_connection()
                conn.execute("""
                    INSERT INTO attendance (employee_id, date, check_in, check_out, work_hours, day_type)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (emp_id, str(selected_date), "00:00", "00:00", 0, "Off"))
                conn.commit()
                conn.close()
                st.success("Off Day Saved!")

# ===============================
# REPORTS
# ===============================
elif menu == "Reports":
    st.subheader("Attendance Report")

    employees = get_employees()
    if employees.empty:
        st.warning("Add employees first.")
    else:
        emp_dict = dict(zip(employees["name"], employees["id"]))
        emp_name = st.selectbox("Employee", emp_dict.keys())
        emp_id = emp_dict[emp_name]

        conn = get_connection()
        df = pd.read_sql(f"""
            SELECT date, check_in, check_out, work_hours, day_type
            FROM attendance
            WHERE employee_id={emp_id}
            ORDER BY date DESC
        """, conn)
        conn.close()

        st.dataframe(df)

        csv = df.to_csv(index=False).encode("utf-8")
        st.download_button("Download CSV", csv, "report.csv", "text/csv")
