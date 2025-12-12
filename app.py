import sqlite3
import pandas as pd
import streamlit as st
import ollama

# ===================== DB CONFIG =====================
DB_PATH = "students.db"


# ===================== SCHEMA HELPERS =====================
def get_tables():
    """Return list of table names in the SQLite DB."""
    try:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = [row[0] for row in cur.fetchall()]
        conn.close()
        return tables
    except Exception:
        return []


def get_table_schema(table_name: str):
    """Return a DataFrame of columns for a given table."""
    try:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute(f"PRAGMA table_info({table_name});")
        rows = cur.fetchall()
        conn.close()
        df = pd.DataFrame(rows, columns=["cid", "name", "type", "notnull", "dflt_value", "pk"])
        return df[["name", "type", "pk"]]  # only show main info
    except Exception:
        return pd.DataFrame(columns=["name", "type", "pk"])


# ===================== SCHEMA DESCRIPTION FOR LLM =====================
SCHEMA_DESCRIPTION = """
You are an expert SQL assistant for a SQLite database.

Current database details:
- There is one main table named 'students'.

Table: students
Columns:
- id (INTEGER, primary key)
- name (TEXT): student name
- dept (TEXT): department, e.g., 'CSE', 'ECE', 'EEE', 'IT', 'MECH'
- year (INTEGER): year of study, 1 to 4
- city (TEXT): city name, e.g., 'Chennai', 'Coimbatore', 'Madurai'
- cgpa (REAL): CGPA out of 10

Instructions:
- Your job is to convert the user's natural language request into ONE valid SQL statement.
- The SQL must be compatible with SQLite.
- You MAY generate:
  - SELECT statements (to read data)
  - INSERT, UPDATE, DELETE (to modify data)
  - CREATE TABLE and ALTER TABLE (to change schema)
- Prefer single-statement queries (no multiple statements separated by semicolons).
- Use existing tables and columns unless the user clearly asks you to create/alter them.
- Be careful with destructive operations like DROP TABLE or DELETE; only use them if the user explicitly asks.
- Do NOT include explanations, comments, or extra text.
- Do NOT wrap the SQL in markdown or ``` fences.
- Output ONLY the raw SQL statement as plain text.
"""


# ===================== SQL EXECUTION =====================
def run_sql(query: str):
    """
    Runs the given SQL statement on students.db.

    Returns:
        (df, error_message, kind)

        kind == "select"  -> df contains rows (SELECT or other returning statement)
        kind == "other"   -> non-SELECT (INSERT/UPDATE/DELETE/DDL) successfully executed, df is None
        kind is None      -> error occurred, error_message contains details
    """
    try:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()

        sql = query.strip().rstrip(";")
        cur.execute(sql)

        # If statement returns rows (SELECT or PRAGMA etc.), cur.description is not None
        if cur.description is not None:
            rows = cur.fetchall()
            cols = [d[0] for d in cur.description]
            df = pd.DataFrame(rows, columns=cols)
            conn.close()
            return df, None, "select"
        else:
            # DDL / DML – just commit
            conn.commit()
            conn.close()
            return None, None, "other"

    except Exception as e:
        return None, str(e), None


# ===================== LLM: NATURAL LANGUAGE -> SQL =====================
def nl_to_sql(text: str):
    """
    Uses local Ollama LLM (mistral) to convert natural language to SQL.
    Now supports SELECT + DML + DDL (based on user's request).
    Returns (sql_query, error_message).
    """
    if not text or not text.strip():
        return None, "Please type a question or command."

    user_question = text.strip()

    prompt = f"""{SCHEMA_DESCRIPTION}

User request: {user_question}

SQL statement:
"""

    try:
        response = ollama.chat(
            model="mistral",  # ensure 'mistral' model is pulled in Ollama
            messages=[
                {
                    "role": "system",
                    "content": "You convert natural language requests into single SQL statements for a SQLite database."
                },
                {
                    "role": "user",
                    "content": prompt
                },
            ],
        )

        raw = response["message"]["content"].strip()

        # Clean markdown fences if any
        if "```" in raw:
            parts = raw.split("```")
            # pick the part that looks most like SQL
            candidates = [p.strip() for p in parts if "select" in p.lower()
                          or "insert" in p.lower()
                          or "update" in p.lower()
                          or "delete" in p.lower()
                          or "create" in p.lower()
                          or "alter" in p.lower()
                          or "drop" in p.lower()]
            if candidates:
                raw = candidates[0]

        sql = raw.strip()

        # Remove trailing semicolon (optional)
        if sql.endswith(";"):
            sql = sql[:-1]

        # Basic sanity check
        first_word = sql.split()[0].lower() if sql else ""
        if first_word not in ["select", "insert", "update", "delete", "create", "alter", "drop", "pragma"]:
            return None, f"Model did not return a valid SQL statement. It returned:\n{sql}"

        return sql, None

    except Exception as e:
        return None, f"Error from LLM: {e}"


# ===================== LLM: SQL FIXER =====================
def fix_sql(original_sql: str, db_error: str, user_request: str):
    """
    Ask the LLM to fix an invalid SQL statement based on DB error.
    Works for SELECT + DML + DDL.
    Returns (fixed_sql, error_message).
    """
    fix_prompt = f"""
You previously generated this SQL for a user request:

User request:
{user_request}

Original SQL:
{original_sql}

When executing this SQL on SQLite, the following error occurred:
{db_error}

Database schema:
{SCHEMA_DESCRIPTION}

Your task:
- Return a corrected SQL statement that is valid for this schema and SQLite.
- Keep the query as close as possible to the user's intent.
- You may use SELECT, INSERT, UPDATE, DELETE, CREATE TABLE or ALTER TABLE.
- Do NOT modify or delete data unless the user clearly requested it.
- Do NOT include explanations or comments.
- Do NOT wrap the SQL in markdown or ``` fences.
- Output ONLY the fixed SQL statement.
"""

    try:
        response = ollama.chat(
            model="mistral",
            messages=[
                {
                    "role": "system",
                    "content": "You fix invalid SQL statements for a SQLite database."
                },
                {
                    "role": "user",
                    "content": fix_prompt
                },
            ],
        )

        raw = response["message"]["content"].strip()

        if "```" in raw:
            parts = raw.split("```")
            candidates = [p.strip() for p in parts if "select" in p.lower()
                          or "insert" in p.lower()
                          or "update" in p.lower()
                          or "delete" in p.lower()
                          or "create" in p.lower()
                          or "alter" in p.lower()
                          or "drop" in p.lower()]
            if candidates:
                raw = candidates[0]

        sql = raw.strip()
        if sql.endswith(";"):
            sql = sql[:-1]

        first_word = sql.split()[0].lower() if sql else ""
        if first_word not in ["select", "insert", "update", "delete", "create", "alter", "drop", "pragma"]:
            return None, f"Fixed SQL is not a valid statement. It returned:\n{sql}"

        return sql, None

    except Exception as e:
        return None, f"Error from LLM during fix: {e}"


# ===================== STREAMLIT APP =====================
def main():
    st.set_page_config(page_title="NL → SQL DB Worker", layout="wide")

    # ----- Sidebar: Schema Viewer -----
    with st.sidebar:
        st.header("📘 Schema Viewer")
        tables = get_tables()
        if not tables:
            st.info("No tables found. Make sure 'students.db' is created.")
        else:
            for t in tables:
                with st.expander(f"Table: {t}", expanded=(t == "students")):
                    schema_df = get_table_schema(t)
                    if schema_df.empty:
                        st.write("No schema info available.")
                    else:
                        st.dataframe(schema_df, use_container_width=True)

        st.markdown("---")
        st.caption("This panel only shows DB structure. All SQL is generated from natural language by the AI model.")

    # ----- Main area: Chat Interface -----
    st.title("Natural Language → SQL Database Worker")
    st.write("Ask anything or give commands about the database in plain English. "
             "The system can read and modify the database using SQL generated by the local LLM.")


    #st.markdown("**Example requests:**")
    #st.code(
       # "show all students\n"
        #"add age column to students table\n"
        #"set age of all students to 20\n"
        #"show students from chennai with cgpa above 8\n"
        #"delete students with cgpa below 5 (be careful!)\n"
        #"create a new table called alumni\n"
   # )'''

    # Initialize chat history
    if "messages" not in st.session_state:
        st.session_state.messages = []

    # Display previous messages
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    # Chat input
    user_input = st.chat_input("Type your question or command about the database...")

    if user_input:
        # Store and display user message
        st.session_state.messages.append({"role": "user", "content": user_input})
        with st.chat_message("user"):
            st.markdown(user_input)

        # Assistant response block
        with st.chat_message("assistant"):
            # Step 1: NL -> SQL
            sql, err = nl_to_sql(user_input)
            if err:
                st.error(err)
                st.session_state.messages.append({"role": "assistant", "content": f"❌ {err}"})
                return

            st.markdown("**Generated SQL:**")
            st.code(sql, language="sql")

            # Step 2: Execute SQL
            df, db_err, kind = run_sql(sql)

            # Step 3: If DB error, try to fix SQL
            if db_err:
                st.warning(f"Database error: {db_err}")
                st.markdown("Trying to fix the SQL using the model...")

                fixed_sql, fix_err = fix_sql(sql, db_err, user_input)
                if fix_err:
                    st.error(fix_err)
                    st.session_state.messages.append(
                        {"role": "assistant",
                         "content": f"❌ DB error: {db_err}\n\nAnd fix also failed: {fix_err}"}
                    )
                    return

                st.markdown("**Fixed SQL:**")
                st.code(fixed_sql, language="sql")

                df, db_err2, kind2 = run_sql(fixed_sql)
                if db_err2:
                    st.error(f"Database error even after fix: {db_err2}")
                    st.session_state.messages.append(
                        {"role": "assistant", "content": f"❌ DB error after fix: {db_err2}"}
                    )
                    return
                else:
                    if kind2 == "select":
                        if df is None or df.empty:
                            st.info("No rows found for this query (after fix).")
                            st.session_state.messages.append(
                                {"role": "assistant",
                                 "content": "✅ Query ran (after fix), but no rows matched."}
                            )
                        else:
                            st.dataframe(df, use_container_width=True)
                            st.session_state.messages.append(
                                {"role": "assistant",
                                 "content": "✅ Query ran successfully (after fix) and returned rows."}
                            )
                    else:
                        st.success("✅ Command executed successfully (after fix).")
                        st.session_state.messages.append(
                            {"role": "assistant",
                             "content": "✅ Command executed successfully on the database (after fix)."}
                        )
            else:
                # No DB error
                if kind == "select":
                    if df is None or df.empty:
                        st.info("No rows found for this query.")
                        st.session_state.messages.append(
                            {"role": "assistant",
                             "content": "✅ Query ran successfully, but no rows matched."}
                        )
                    else:
                        st.dataframe(df, use_container_width=True)
                        st.session_state.messages.append(
                            {"role": "assistant",
                             "content": "✅ Query ran successfully and returned rows."}
                        )
                else:
                    st.success("✅ Command executed successfully.")
                    st.session_state.messages.append(
                        {"role": "assistant",
                         "content": "✅ Command executed successfully on the database."}
                    )


if __name__ == "__main__":
    main()
