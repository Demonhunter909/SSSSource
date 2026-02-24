import os
import psycopg2
import datetime
from flask import Flask, flash, redirect, render_template, request, session
from flask_session import Session
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import check_password_hash, generate_password_hash
from functools import wraps
from datetime import timedelta

app = Flask(__name__, static_folder='.', static_url_path='')

# Database URI for sessions
db_uri = f"postgresql://{os.getenv('DB_USER')}:{os.getenv('DB_PASSWORD')}@{os.getenv('DB_HOST')}:{os.getenv('DB_PORT', '5432')}/{os.getenv('DB_NAME')}"

# SQLAlchemy config
app.config["SQLALCHEMY_DATABASE_URI"] = db_uri
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db = SQLAlchemy(app)

# Session configuration
app.config["SESSION_TYPE"] = "sqlalchemy"
app.config["SESSION_SQLALCHEMY"] = db
app.config["SESSION_SQLALCHEMY_TABLE"] = "sessions"
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(days=7)
app.config["SESSION_PERMANENT"] = True
app.secret_key = "your-secret-key-here"

Session(app)

if app.debug:
    app.config["SESSION_COOKIE_SECURE"] = False
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
else:
    app.config["SESSION_COOKIE_SECURE"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "None"

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

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS uploads (
        id SERIAL PRIMARY KEY,
        url TEXT NOT NULL,
        category TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        user_id INTEGER REFERENCES users(id),
        title TEXT,
        description TEXT
    );
""")

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            id SERIAL PRIMARY KEY,
            session_id VARCHAR(255) UNIQUE NOT NULL,
            data BYTEA NOT NULL,
            expiry TIMESTAMP NOT NULL
        );
    """)

    cursor.execute("SELECT value FROM site_settings WHERE key = 'max_users'")
    if cursor.fetchone() is None:
        cursor.execute("INSERT INTO site_settings (key, value) VALUES ('max_users', '0')")

    conn.commit()
    conn.close()

# Create sessions table on startup
def create_sessions_table():
    try:
        with app.app_context():
            conn = get_db()
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS sessions (
                    id SERIAL PRIMARY KEY,
                    session_id VARCHAR(255) UNIQUE NOT NULL,
                    data BYTEA NOT NULL,
                    expiry TIMESTAMP NOT NULL
                );
            """)
            conn.commit()
            conn.close()
    except Exception as e:
        print(f"Error creating sessions table: {e}")

@app.route("/init")
def init_route():
    try:
        init_db()
        create_sessions_table()
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
        session.permanent = True
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

        flash("Account created! Check your email to verify. Please check your spam folder if you don't see the email.", "success")
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
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, url, title, description, category
            FROM uploads
            ORDER BY created_at DESC
        """)
        uploads = cursor.fetchall()
        conn.close()

        return render_template("home.html", username=session["username"], uploads=uploads)

    return render_template("index.html")


@app.route("/articles")
def articles():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, url, title, description
        FROM uploads 
        WHERE category = 'articles' 
        ORDER BY created_at DESC
        """)    
    urls = cursor.fetchall()
    conn.close()

    return render_template("articles.html", urls=urls)


@app.route("/venom")
def venom():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, url, title, description
        FROM uploads 
        WHERE category = 'venom' 
        ORDER BY created_at DESC
        """)    
    urls = cursor.fetchall()
    conn.close()

    return render_template("venom.html", urls=urls)


@app.route("/talent")
def talent():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, url, title, description
        FROM uploads 
        WHERE category = 'talent' 
        ORDER BY created_at DESC
        """)    
    urls = cursor.fetchall()
    conn.close()

    return render_template("talent.html", urls=urls)

@app.route("/athletics")
def athletics():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, url, title, description
        FROM uploads 
        WHERE category = 'athletics' 
        ORDER BY created_at DESC
        """)    
    urls = cursor.fetchall()
    conn.close()

    return render_template("athletics.html", urls=urls)

@app.route("/entertainment")
def entertainment():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, url, title, description
        FROM uploads 
        WHERE category = 'entertainment' 
        ORDER BY created_at DESC
        """)    
    urls = cursor.fetchall()
    conn.close()

    return render_template("entertainment.html", urls=urls)


@app.route("/news")
def news():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, url, title, description
        FROM uploads 
        WHERE category = 'news' 
        ORDER BY created_at DESC
        """)    
    urls = cursor.fetchall()
    conn.close()

    return render_template("news.html", urls=urls)


@app.route("/features")
def features():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, url, title, description
        FROM uploads 
        WHERE category = 'features' 
        ORDER BY created_at DESC
        """)
    urls = cursor.fetchall()
    conn.close()

    return render_template("features.html", urls=urls)


@app.route("/upload", methods=["GET", "POST"])
@login_required
def upload():
    if request.method == "POST":
        title = request.form.get("title")
        description = request.form.get("description")
        url = request.form.get("url")
        category = request.form.get("category")

        if not url or not category or not title:
            flash("Title, URL and category required", "error")
            return redirect("/upload")

        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO uploads (url, category, user_id, title, description)
            VALUES (%s, %s, %s, %s, %s)
        """, (url, category, session["user_id"], title, description))
        conn.commit()
        conn.close()

        flash("URL uploaded successfully!", "success")
        return redirect(f"/{category}")

    return render_template("home.html")
    
@app.route("/delete-url/<int:url_id>")
@login_required
def delete_url(url_id):
    conn = get_db()
    cursor = conn.cursor()

    # Get category so we can redirect back to the correct page
    cursor.execute("SELECT category FROM uploads WHERE id = %s", (url_id,))
    row = cursor.fetchone()

    if not row:
        flash("URL not found", "error")
        return redirect("/")

    category = row[0]

    cursor.execute("DELETE FROM uploads WHERE id = %s", (url_id,))
    conn.commit()
    conn.close()

    flash("URL deleted", "success")
    return redirect(f"/{category}")

@app.route("/edit-url/<int:url_id>", methods=["GET", "POST"])
@login_required
def edit_url(url_id):
    conn = get_db()
    cursor = conn.cursor()

    if request.method == "POST":
        title = request.form.get("title")
        description = request.form.get("description")
        url = request.form.get("url")

        # Get category BEFORE updating
        cursor.execute("SELECT category FROM uploads WHERE id = %s", (url_id,))
        row = cursor.fetchone()
        category = row[0]

        # Update the record
        cursor.execute("""
            UPDATE uploads
            SET title = %s, description = %s, url = %s
            WHERE id = %s
        """, (title, description, url, url_id))

        conn.commit()
        conn.close()

        flash("URL updated!", "success")
        return redirect(f"/{category}")

    cursor.execute("SELECT title, description, url FROM uploads WHERE id = %s", (url_id,))
    item = cursor.fetchone()
    conn.close()

    return render_template("edit_url.html", item=item, url_id=url_id)



if __name__ == "__main__":
    init_db()
    create_sessions_table()
    app.run(debug=False, host="0.0.0.0", port=5000)
