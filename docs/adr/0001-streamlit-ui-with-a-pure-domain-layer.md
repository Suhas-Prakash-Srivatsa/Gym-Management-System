# Streamlit UI with a pure domain layer

We chose Streamlit for V1 because it gives a gym owner a one-command local dashboard with no frontend code, but a hosted multi-tenant version would need FastAPI plus a real frontend later. To keep that migration cheap, all domain logic (balances, due dates, overdue rules, validation) lives in pure functions under `src/`, and `app.py` is a dumb shell that only uploads files, calls those functions, renders results and collects input.

**Consequences**: no arithmetic or business rules may be written inside `app.py`, even when it is more convenient — that convenience is the entire cost of the eventual migration. A future reader who finds the Streamlit layer suspiciously thin should leave it that way.
