import streamlit as st
import psycopg2
from datetime import datetime, date, timedelta
import pandas as pd
import calendar

# ===============================
# CONFIG
# ===============================
st.set_page_config(page_title="Ice Cream Truck Manager", layout="wide")

STANDARD_HOURS = 9

# ===============================
# DATABASE CONNECTION
# ===============================
def get_connection():
    try:
        conn = psycopg2.connect(st.secrets["database"]["url"])
        st.success("✅ Database Connected Successfully")
        return conn
    except Exception as e:
        st.error(f"❌ Database connection failed: {e}")
        st.stop()

def init_db():
    conn = get_connection()
    c = conn.cursor()

    c.execute("""
        CREATE TABLE IF NOT EXISTS employees (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL,
            balance_hours REAL DEFAULT 0
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS attendance (
            id SERIAL PRIMARY KEY,
            employee_id INTEGER REFERENCES employees(id),
            date DATE,
            check_in TIME,
            check_out TIME,
            work_hours REAL,
            day_type TEXT
        )
    """)

    conn.commit()
    conn.close()

init_db()

# ===============================
# AUTHENTICATION
# ===============================
def check_password():
    def password_entered():
        if (
            st.session_state["username"] == st.secrets["credentials"]["username"]
            and st.session_state["password"] == st.secrets["credentials"]["password"]
        ):
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
        st.error("User not known or password incorrect")
        return False
    else:
        return True

if not check_password():
    st.stop()

# ===============================
# HELPER FUNCTIONS
# ===============================
def get_employees():
    conn = get_connection()
    df = pd.read_sql("SELECT * FROM employees ORDER BY name", conn)
    conn.close()
    return df

def update_balance(employee_id, new_balance):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("UPDATE employees SET balance_hours=%s WHERE id=%s",
                (new_balance, employee_id))
    conn.commit()
    conn.close()

def calculate_week_hours(employee_id):
    conn = get_connection()
    start_week = date.today() - timedelta(days=date.today().weekday())
    end_week = start_week + timedelta(days=6)

    query = """
        SELECT COALESCE(SUM(work_hours),0)
        FROM attendance
        WHERE employee_id=%s
        AND date BETWEEN %s AND %s
    """
    df = pd.read_sql(query, conn, params=(employee_id, start_week, end_week))
    conn.close()
    return float(df.iloc[0][0])

def get_attendance_for_month(employee_id, year, month):
    conn = get_connection()
    start_date = date(year, month, 1)
    end_date = date(year, month, calendar.monthrange(year, month)[1])

    query = """
        SELECT date, work_hours
        FROM attendance
        WHERE employee_id=%s
        AND date BETWEEN %s AND %s
    """
    df = pd.read_sql(query, conn, params=(employee_id, start_date, end_date))
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
            cur = conn.cursor()
            cur.execute("INSERT INTO employees (name) VALUES (%s)", (name,))
            conn.commit()
            conn.close()
            st.success("Employee Added!")
        else:
            st.warning("Enter name first")

# ===============================
# DASHBOARD
# ===============================
elif menu == "Dashboard":
    st.subheader("Employee Dashboard")
    employees = get_employees()

    if employees.empty:
        st.warning("Add employees first.")
    else:
        for _, emp in employees.iterrows():
            with st.expander(f"{emp['name']}", expanded=True):
                week_hours = calculate_week_hours(emp["id"])

                col1, col2 = st.columns(2)
                col1.metric("Current Balance", f"{round(emp['balance_hours'],2)} hrs")
                col2.metric("This Week", f"{round(week_hours,2)} / 54 hrs")

                st.markdown("### Monthly Calendar")
                today = date.today()
                att_df = get_attendance_for_month(emp["id"], today.year, today.month)
                att_dict = dict(zip(att_df["date"].astype(str), att_df["work_hours"]))

                cols = st.columns(7)
                for i, d in enumerate(["Mon","Tue","Wed","Thu","Fri","Sat","Sun"]):
                    cols[i].write(f"**{d}**")

                first_day = date(today.year, today.month, 1)
                start_pad = first_day.weekday()
                num_days = calendar.monthrange(today.year, today.month)[1]

                current_day = 1
                for week in range(6):
                    cols = st.columns(7)
                    for day_idx in range(7):
                        if (week == 0 and day_idx < start_pad) or current_day > num_days:
                            cols[day_idx].write("")
                        else:
                            d_str = str(date(today.year, today.month, current_day))
                            hours = att_dict.get(d_str)
                            label = f"{current_day}"
                            if hours:
                                label += f"\n{round(hours,1)}h"
                            cols[day_idx].info(label)
                            current_day += 1
                    if current_day > num_days:
                        break
            st.divider()

# ===============================
# ADD ATTENDANCE
# ===============================
elif menu == "Add Attendance":
    st.subheader("Daily Attendance Entry")
    employees = get_employees()

    if employees.empty:
        st.warning("Add employees first.")
    else:
        emp_dict = dict(zip(employees["name"], employees["id"]))
        emp_name = st.selectbox("Select Employee", emp_dict.keys())
        emp_id = emp_dict[emp_name]
        current_balance = float(employees[employees["id"] == emp_id]["balance_hours"].values[0])

        selected_date = st.date_input("Date", value=date.today())

        in_time = st.time_input("Check In", datetime.now().time())
        out_time = st.time_input("Check Out", datetime.now().time())

        dt_in = datetime.combine(selected_date, in_time)
        dt_out = datetime.combine(selected_date, out_time)

        if dt_out <= dt_in:
            dt_out += timedelta(days=1)

        work_hours = (dt_out - dt_in).total_seconds() / 3600
        difference = work_hours - STANDARD_HOURS

        st.info(f"Hours: {round(work_hours,2)}")

        if st.button("Save Attendance"):
            new_balance = current_balance + difference

            conn = get_connection()
            cur = conn.cursor()

            cur.execute("""
                INSERT INTO attendance (employee_id, date, check_in, check_out, work_hours, day_type)
                VALUES (%s,%s,%s,%s,%s,%s)
            """, (emp_id, selected_date, in_time, out_time, work_hours, "Normal"))

            cur.execute("UPDATE employees SET balance_hours=%s WHERE id=%s",
                        (new_balance, emp_id))

            conn.commit()
            conn.close()

            st.success("Attendance Saved!")

# ===============================
# REPORTS
# ===============================
elif menu == "Reports":
    st.subheader("Attendance Report")
    employees = get_employees()

    if not employees.empty:
        emp_dict = dict(zip(employees["name"], employees["id"]))
        emp_name = st.selectbox("Employee", emp_dict.keys())
        emp_id = emp_dict[emp_name]

        conn = get_connection()
        query = """
            SELECT date, check_in, check_out, work_hours, day_type
            FROM attendance
            WHERE employee_id=%s
            ORDER BY date DESC
        """
        df = pd.read_sql(query, conn, params=(emp_id,))
        conn.close()

        st.dataframe(df)

        csv = df.to_csv(index=False).encode("utf-8")
        st.download_button("Download CSV", csv, "report.csv", "text/csv")

