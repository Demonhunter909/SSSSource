import os
import psycopg2
from flask import Flask, flash, redirect, render_template, request, session
from flask_session import Session
from werkzeug.security import check_password_hash, generate_password_hash
from functools import wraps

app = Flask(__name__, static_folder='.', static_url_path='')
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
app.secret_key = "your-secret-key-here"
Session(app)

def get_db():
    return psycopg2.connect(
        host=os.getenv("DB_HOST"),
        port="5432",
        database="postgres",
        user="postgres",
        password=os.getenv("DB_PASSWORD")
    )

def init_db():
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            parent_id INTEGER,
            max_children INTEGER DEFAULT 0
        );
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS site_settings (
            key TEXT PRIMARY KEY,
            value TEXT
        );
    """)

    cursor.execute("SELECT value FROM site_settings WHERE key = 'max_users'")
    if cursor.fetchone() is None:
        cursor.execute("INSERT INTO site_settings (key, value) VALUES ('max_users', '0')")

    conn.commit()
    conn.close()

@app.route("/init")
def init_route():
    try:
        init_db()
        return "Database initialized successfully!"
    except Exception as e:
        return f"Error: {e}", 500


def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if session.get("user_id") is None:
            flash("You must be logged in", "error")
            return redirect("/login")
        return f(*args, **kwargs)
    return wrapper

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")

        if not username or not password:
            flash("Username and password required", "error")
            return redirect("/login")

        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT id, username, password FROM users WHERE username = %s", (username,))
        row = cursor.fetchone()
        conn.close()

        if row is None or not check_password_hash(row[2], password):
            flash("Invalid username or password", "error")
            return redirect("/login")

        session["user_id"] = row[0]
        session["username"] = row[1]
        flash(f"Welcome, {username}!", "success")
        return redirect("/")

    return render_template("login.html")

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        confirm = request.form.get("confirm_password")

        if not username or not password or not confirm:
            flash("All fields required", "error")
            return redirect("/register")

        if password != confirm:
            flash("Passwords do not match", "error")
            return redirect("/register")

        hashed = generate_password_hash(password)
        parent_id = session.get("user_id")

        conn = get_db()
        cursor = conn.cursor()

        # Check global max users
        cursor.execute("SELECT value FROM site_settings WHERE key = 'max_users'")
        max_users = int(cursor.fetchone()[0])

        if max_users > 0:
            cursor.execute("SELECT COUNT(*) FROM users")
            if cursor.fetchone()[0] >= max_users:
                conn.close()
                flash("Site user limit reached", "error")
                return redirect("/register")

        # Check parent max_children
        if parent_id:
            cursor.execute("SELECT max_children FROM users WHERE id = %s", (parent_id,))
            max_children = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM users WHERE parent_id = %s", (parent_id,))
            if cursor.fetchone()[0] >= max_children:
                conn.close()
                flash("User creation limit reached for your account", "error")
                return redirect("/register")

        try:
            cursor.execute("""
                INSERT INTO users (username, password, parent_id)
                VALUES (%s, %s, %s)
            """, (username, hashed, parent_id))
            conn.commit()
        except psycopg2.Error:
            flash("Username already exists", "error")
            conn.close()
            return redirect("/register")

        conn.close()
        flash("Account created! Please log in.", "success")
        return redirect("/login")

    return render_template("register.html")

@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out", "success")
    return redirect("/")

@app.route("/account/settings", methods=["GET", "POST"])
@login_required
def account_settings():
    user_id = session["user_id"]

    conn = get_db()
    cursor = conn.cursor()

    if request.method == "POST":
        try:
            new_max = int(request.form.get("max_users"))
            if new_max < 0:
                raise ValueError
        except ValueError:
            flash("Invalid value", "error")
            conn.close()
            return redirect("/account/settings")

        cursor.execute("UPDATE site_settings SET value = %s WHERE key = 'max_users'", (str(new_max),))
        conn.commit()
        flash("Site user limit updated", "success")

    cursor.execute("SELECT username FROM users WHERE id = %s", (user_id,))
    username = cursor.fetchone()[0]

    cursor.execute("SELECT value FROM site_settings WHERE key = 'max_users'")
    max_users = int(cursor.fetchone()[0])

    conn.close()

    return render_template("account_settings.html", username=username, max_users=max_users)

@app.route("/")
def index():
    if session.get("user_id"):
        return render_template("home.html", username=session["username"])
    return render_template("index.html")

@app.route("/articles")
def articles():
    return render_template("articles.html")

@app.route("/venom")
def venom():
    return render_template("venom.html")

@app.route("/talent")
def talent():
    return render_template("talent.html")

@app.route("/athletics")
def athletics():
    return render_template("athletics.html")

@app.route("/entertainment")
def entertainment():
    return render_template("entertainment.html")

@app.route("/news")
def news():
    return render_template("news.html")

@app.route("/features")
def features():
    return render_template("features.html")

if __name__ == "__main__":
    init_db()
    app.run(debug=True, host="0.0.0.0", port=5000)
