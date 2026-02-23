import os
import psycopg2
import datetime
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
        port=os.getenv("DB_PORT", "5432"),
        database=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD")
    )

def init_db():
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            username TEXT UNIQUE NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            parent_id INTEGER,
            max_children INTEGER DEFAULT 0,
            email_verified BOOLEAN DEFAULT FALSE,
            admin_approved BOOLEAN DEFAULT FALSE
        );
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS verification_tokens (
            id SERIAL PRIMARY KEY,
            user_id INTEGER REFERENCES users(id),
            token TEXT UNIQUE NOT NULL,
            expires_at TIMESTAMP NOT NULL,
            type TEXT NOT NULL
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
        cursor.execute("SELECT id, username, password, email_verified, admin_approved FROM users WHERE username = %s", (username,))
        row = cursor.fetchone()
        conn.close()

        if row is None or not check_password_hash(row[2], password):
            flash("Invalid username or password", "error")
            return redirect("/login")

        if not row[3]:
            flash("Please verify your email first", "error")
            return redirect("/login")

        if not row[4]:
            flash("Your account is awaiting admin approval", "error")
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
        email = request.form.get("email")
        password = request.form.get("password")
        confirm = request.form.get("confirm_password")

        if not username or not email or not password or not confirm:
            flash("All fields required", "error")
            return redirect("/register")

        if password != confirm:
            flash("Passwords do not match", "error")
            return redirect("/register")

        hashed = generate_password_hash(password)
        parent_id = session.get("user_id")

        conn = get_db()
        cursor = conn.cursor()

        try:
            cursor.execute("""
                INSERT INTO users (username, email, password, parent_id)
                VALUES (%s, %s, %s, %s)
                RETURNING id
            """, (username, email, hashed, parent_id))
            user_id = cursor.fetchone()[0]
        except psycopg2.Error:
            flash("Username or email already exists", "error")
            conn.close()
            return redirect("/register")

        # Create verification token
        from utils import generate_token, token_expiration
        token = generate_token()

        cursor.execute("""
            INSERT INTO verification_tokens (user_id, token, expires_at, type)
            VALUES (%s, %s, %s, 'email_verify')
        """, (user_id, token, token_expiration()))

        conn.commit()
        conn.close()

        # Send verification email
        from email_service import send_email
        send_email(
            email,
            "Verify Your Email",
            f"""
            <p>Click below to verify your email:</p>
            <a href="https://thessssource.onrender.com/verify-email/{token}">
                Verify Email
            </a>
            """
        )

        flash("Account created! Check your email to verify.", "success")
        return redirect("/login")

    return render_template("register.html")

@app.route("/verify-email/<token>")
def verify_email(token):
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT user_id, expires_at FROM verification_tokens
        WHERE token = %s AND type = 'email_verify'
    """, (token,))
    row = cursor.fetchone()

    if not row:
        conn.close()
        flash("Invalid or expired token", "error")
        return redirect("/register")

    user_id, expires_at = row

    if expires_at < datetime.datetime.utcnow():
        conn.close()
        flash("Token expired", "error")
        return redirect("/register")

    cursor.execute("UPDATE users SET email_verified = TRUE WHERE id = %s", (user_id,))

    # Create admin approval token
    from utils import generate_token, token_expiration
    admin_token = generate_token()

    cursor.execute("""
        INSERT INTO verification_tokens (user_id, token, expires_at, type)
        VALUES (%s, %s, %s, 'admin_approval')
    """, (user_id, admin_token, token_expiration()))

    conn.commit()
    conn.close()

    # Send admin approval email
    from email_service import send_email
    send_email(
        "brandonbarbee512@gmail.com",
        "New User Requires Approval",
        f"""
        <p>A user has verified their email and now requires your approval.</p>
        <a href="https://thessssource.onrender.com/admin/approve/{admin_token}">Approve</a><br>
        <a href="https://thessssource.onrender.com/admin/deny/{admin_token}">Deny and Remove</a>
        """
    )

    flash("Email verified! Waiting for admin approval.", "success")
    return redirect("/register")

@app.route("/admin/approve/<token>")
def admin_approve(token):
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT user_id FROM verification_tokens
        WHERE token = %s AND type = 'admin_approval'
    """, (token,))
    row = cursor.fetchone()

    if not row:
        conn.close()
        flash("Invalid token", "error")
        return redirect("/register")

    user_id = row[0]

    cursor.execute("UPDATE users SET admin_approved = TRUE WHERE id = %s", (user_id,))
    conn.commit()
    conn.close()

    flash("User approved! They can now log in.", "success")
    return redirect("/login")

@app.route("/admin/deny/<token>")
def admin_deny(token):
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT user_id FROM verification_tokens
        WHERE token = %s AND type = 'admin_approval'
    """, (token,))
    row = cursor.fetchone()

    if not row:
        conn.close()
        flash("Invalid token", "error")
        return redirect("/register")

    user_id = row[0]

    # Delete tokens first
    cursor.execute("DELETE FROM verification_tokens WHERE user_id = %s", (user_id,))

    # Now delete the user
    cursor.execute("DELETE FROM users WHERE id = %s", (user_id,))

    conn.commit()
    conn.close()

    flash("User denied and removed.", "error")
    return redirect("/register")

@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out", "success")
    return redirect("/")

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
