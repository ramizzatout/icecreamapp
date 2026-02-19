import streamlit as st
import pandas as pd
from sqlalchemy import create_engine, text
# ... other imports ...

# Use the URL from Secrets
DB_URL = st.secrets["database"]["url"]

# If the URL starts with 'postgres://', SQLAlchemy might complain. 
# This fix ensures it uses 'postgresql://' which is the modern standard.
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
# DB INITIALIZATION (Cloud Version)
# ===============================
def init_db():
    with engine.begin() as conn:
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
                employee_id INTEGER,
                date TEXT,
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
        conn.execute(text("UPDATE employees SET balance_hours=:b WHERE id=:id"), 
                     {"b": new_balance, "id": employee_id})

# ===============================
# UI
# ===============================
st.title("🍦 Ice Cream Truck Attendance")
menu = st.sidebar.radio("Navigation", ["Dashboard", "Add Attendance", "Reports", "Add Employee"])

if menu == "Add Employee":
    st.subheader("Add New Employee")
    name = st.text_input("Employee Name")
    if st.button("Add"):
        if name:
            with engine.begin() as conn:
                conn.execute(text("INSERT INTO employees (name) VALUES (:n)"), {"n": name})
            st.success("Employee Added!")
        else:
            st.warning("Enter name first")

elif menu == "Dashboard":
    st.subheader("📊 Employee Dashboard")
    employees = get_employees()
    if employees.empty:
        st.warning("Add employees first.")
    else:
        for _, emp in employees.iterrows():
            with st.expander(f"👤 {emp['name']}", expanded=True):
                # Simple Weekly Logic
                col1, col2 = st.columns(2)
                col1.metric("Current Balance", f"{round(emp['balance_hours'], 2)} hrs")
                st.write("Current status for the month:")
                # Fetch month data
                month_df = pd.read_sql(text(f"SELECT date, work_hours FROM attendance WHERE employee_id={emp['id']}"), engine)
                st.dataframe(month_df, use_container_width=True)

elif menu == "Add Attendance":
    st.subheader("📝 Daily Attendance Entry")
    employees = get_employees()
    if employees.empty:
        st.warning("Add employees first.")
    else:
        emp_dict = dict(zip(employees["name"], employees["id"]))
        emp_name = st.selectbox("Select Employee", emp_dict.keys())
        emp_id = emp_dict[emp_name]
        current_emp_balance = employees[employees["id"] == emp_id]["balance_hours"].values[0]

        selected_date = st.date_input("Date", value=date.today())
        day_type = st.selectbox("Day Type", ["Normal", "Event-Truck", "Event-Offsite", "Off"])

        if day_type != "Off":
            t_col1, t_col2 = st.columns(2)
            with t_col1:
                in_h = st.number_input("In Hour", 1, 12, 9)
                in_ap = st.selectbox("In AM/PM", ["AM", "PM"])
            with t_col2:
                out_h = st.number_input("Out Hour", 1, 12, 6)
                out_ap = st.selectbox("Out AM/PM", ["AM", "PM"], index=1)

            work_hours = st.number_input("Total hours worked manually", 0.0, 24.0, 9.0)
            difference = work_hours - STANDARD_HOURS
            
            if st.button("Save Attendance"):
                new_balance = current_emp_balance + difference
                update_balance(emp_id, new_balance)
                with engine.begin() as conn:
                    conn.execute(text("""
                        INSERT INTO attendance (employee_id, date, work_hours, day_type)
                        VALUES (:id, :d, :wh, :dt)
                    """), {"id": emp_id, "d": str(selected_date), "wh": work_hours, "dt": day_type})
                st.success("Saved Successfully!")

elif menu == "Reports":
    st.subheader("Attendance Report")
    employees = get_employees()
    if not employees.empty:
        emp_dict = dict(zip(employees["name"], employees["id"]))
        emp_name = st.selectbox("Employee", emp_dict.keys())
        df = pd.read_sql(text(f"SELECT * FROM attendance WHERE employee_id={emp_dict[emp_name]}"), engine)
        st.dataframe(df)

