from langchain_core.tools import tool
from app.core.database import SessionLocal

@tool
async def db_read_tool(sql_query: str) -> str:
    """
    Execute a raw SQL read (SELECT) query against the application's database.

    Args:
        sql_query (str): A SQL SELECT query string to execute. 
            Only read-only queries (SELECT statements) are allowed.

    Returns:
        str: The result of the query as a string (tabular format or raw output).

    Example:
        result = await db_read_tool("SELECT * FROM receipt LIMIT 5;")
    """
    
    db = SessionLocal()
    try:
        result = db.execute(sql_query)
        rows = result.fetchall()
        columns = result.keys()
        
        # Format as list of dicts
        output = [dict(zip(columns, row)) for row in rows]
        return output
    finally:
        db.close()