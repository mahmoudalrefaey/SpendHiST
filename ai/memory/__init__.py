"""
memory/ — Agent memory backends.

Provides short-term (conversation context) and long-term (persistent)
memory so agents can recall previous interactions and decisions.

Planned modules:
    - short_term.py  — in-process message history buffer
    - long_term.py   — vector-store or DB-backed persistent memory
    - context.py     — shared context object passed between agent steps
"""
