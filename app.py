import csv
import io
import sqlite3
from datetime import datetime

from flask import Flask, Response, g, jsonify, render_template, request

DB_PATH = "expenses.db"
CATEGORIES = ["Food", "Transport", "Rent", "Shopping", "Bills", "Health", "Entertainment", "Other"]

app = Flask(__name__)


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(exc):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    with sqlite3.connect(DB_PATH) as db:
        db.execute(
            """CREATE TABLE IF NOT EXISTS expenses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                amount REAL NOT NULL,
                category TEXT NOT NULL,
                description TEXT,
                spent_on TEXT NOT NULL
            )"""
        )


@app.route("/")
def index():
    return render_template("index.html", categories=CATEGORIES)


@app.route("/api/expenses", methods=["GET"])
def list_expenses():
    rows = get_db().execute(
        "SELECT * FROM expenses ORDER BY spent_on DESC, id DESC"
    ).fetchall()
    return jsonify([dict(r) for r in rows])


@app.route("/api/expenses", methods=["POST"])
def add_expense():
    data = request.get_json(silent=True) or {}
    try:
        amount = float(data.get("amount"))
        if amount <= 0:
            raise ValueError
    except (TypeError, ValueError):
        return jsonify(error="Amount must be a positive number"), 400

    category = data.get("category")
    if category not in CATEGORIES:
        return jsonify(error="Invalid category"), 400

    try:
        spent_on = datetime.strptime(data.get("spent_on", ""), "%Y-%m-%d").strftime("%Y-%m-%d")
    except ValueError:
        return jsonify(error="Date must be YYYY-MM-DD"), 400

    description = (data.get("description") or "").strip()[:200]

    db = get_db()
    cur = db.execute(
        "INSERT INTO expenses (amount, category, description, spent_on) VALUES (?, ?, ?, ?)",
        (amount, category, description, spent_on),
    )
    db.commit()
    return jsonify(id=cur.lastrowid), 201


@app.route("/api/expenses/<int:expense_id>", methods=["DELETE"])
def delete_expense(expense_id):
    db = get_db()
    cur = db.execute("DELETE FROM expenses WHERE id = ?", (expense_id,))
    db.commit()
    if cur.rowcount == 0:
        return jsonify(error="Not found"), 404
    return "", 204


@app.route("/api/summary")
def summary():
    db = get_db()
    total = db.execute("SELECT COALESCE(SUM(amount), 0) FROM expenses").fetchone()[0]
    by_category = db.execute(
        "SELECT category, SUM(amount) AS total FROM expenses GROUP BY category ORDER BY total DESC"
    ).fetchall()
    by_month = db.execute(
        "SELECT substr(spent_on, 1, 7) AS month, SUM(amount) AS total "
        "FROM expenses GROUP BY month ORDER BY month"
    ).fetchall()
    return jsonify(
        total=total,
        by_category=[dict(r) for r in by_category],
        by_month=[dict(r) for r in by_month],
    )


@app.route("/export.csv")
def export_csv():
    rows = get_db().execute(
        "SELECT spent_on, category, description, amount FROM expenses ORDER BY spent_on"
    ).fetchall()
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["date", "category", "description", "amount"])
    for r in rows:
        writer.writerow([r["spent_on"], r["category"], r["description"], r["amount"]])
    return Response(
        out.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=expenses.csv"},
    )


init_db()

if __name__ == "__main__":
    app.run(debug=True)
