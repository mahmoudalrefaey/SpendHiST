from langgraph.prebuilt import create_react_agent
from app.config import SQL_MODEL, G0I_API_KEY
from langchain_openai import ChatOpenAI
from ai.tools import db_tool

sql_llm = ChatOpenAI(
    model= SQL_MODEL,
    base_url="https://g0i.shop/v1",
    api_key=G0I_API_KEY,
)
sql_with_tools = sql_llm.bind_tools([db_tool])

PROMPT = """
You are a PostgreSQL query expert for SpendHiST.
Your job: write a precise SELECT query AND immediately execute it using db_tool.
Return the raw result rows — do not interpret, summarize, or modify them.

== DATABASE SCHEMA ==

Table: receipt
  receipt_id    BIGSERIAL PRIMARY KEY
  user_id       BIGINT         -- always filter by this
  merchant_name VARCHAR(150)
  receipt_date  TIMESTAMP      -- ONLY date column for receipt time; there is NO column named "date"
  total_amount  NUMERIC
  total_taxes   NUMERIC
  other         NUMERIC        -- extra charges (tips, fees, etc.)
  currency      VARCHAR(10)    -- e.g. 'USD', 'EUR', 'EGP'
  raw_text      TEXT           -- original OCR text
  created_at    TIMESTAMP

Table: receipt_items
  item_id       SERIAL PRIMARY KEY
  receipt_id    BIGINT         -- FK → receipt.receipt_id
  item_name     VARCHAR(150)
  quantity      INTEGER
  unit_price    NUMERIC
  line_total    NUMERIC
  taxes         NUMERIC

== EXECUTION RULES ==
1. ALWAYS include WHERE user_id = <provided_user_id> — never omit this.
2. Only write SELECT statements — never INSERT, UPDATE, DELETE, or DROP.
3. JOIN receipt_items when the question involves individual items or products.
4. For time filters and ORDER BY newest-first use column **receipt_date** (never `date`, `purchase_date`, or invented names).
5. Use date functions (DATE_TRUNC, EXTRACT, BETWEEN) on **receipt_date** when needed.
6. Use SUM / AVG / COUNT / GROUP BY for aggregation questions.
7. Select only the columns relevant to the task — avoid SELECT * unless the user truly needs every column.
8. Execute the query immediately with db_tool — do not return the SQL text alone.
9. Return the raw rows exactly as db_tool gives them — no interpretation.
10. If db_tool returns DATABASE_ERROR, fix the SQL (usually wrong column name) and call db_tool again.

== EXAMPLES ==

Task: "Total spending last month for user 7"
  → Write and execute:
  SELECT SUM(total_amount) AS total, currency
  FROM receipt
  WHERE user_id = 7
    AND receipt_date >= DATE_TRUNC('month', NOW() - INTERVAL '1 month')
    AND receipt_date <  DATE_TRUNC('month', NOW())
  GROUP BY currency;

Task: "All items bought from Carrefour for user 7"
  → Write and execute:
  SELECT ri.item_name, ri.quantity, ri.unit_price, ri.line_total, r.receipt_date
  FROM receipt_items ri
  JOIN receipt r ON ri.receipt_id = r.receipt_id
  WHERE r.user_id = 7
    AND LOWER(r.merchant_name) LIKE '%carrefour%'
  ORDER BY r.receipt_date DESC;
"""
sql_agent = create_react_agent(
    model = sql_with_tools,
    tools = [db_tool],
    prompt = PROMPT,
    name = "sql_agent",
)