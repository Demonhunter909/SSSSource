import os
import sqlite3
import requests
from werkzeug.utils import secure_filename
from flask import Flask, flash, redirect, render_template, request, session, abort, url_for
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.security import check_password_hash, generate_password_hash
from functools import wraps

# Create Flask app and configure static files to be served from project root
app = Flask(__name__, static_folder='.', static_url_path='')

app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
app.secret_key = "your-secret-key-here"
Session(app)

# Initialize database
def init_db():
    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL
        )
    ''')
    conn.commit()
    # Ensure new columns for parent-child account model exist
    cursor.execute("PRAGMA table_info(users)")
    cols = [r[1] for r in cursor.fetchall()]
    if 'parent_id' not in cols:
        try:
            cursor.execute('ALTER TABLE users ADD COLUMN parent_id INTEGER')
        except Exception:
            pass
    if 'max_children' not in cols:
        try:
            cursor.execute('ALTER TABLE users ADD COLUMN max_children INTEGER DEFAULT 0')
        except Exception:
            pass
    # Create a simple site_settings table to store global limits
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS site_settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    ''')
    # Ensure a default max_users entry exists (0 = unlimited)
    cursor.execute("SELECT value FROM site_settings WHERE key = 'max_users'")
    if cursor.fetchone() is None:
        cursor.execute("INSERT INTO site_settings (key, value) VALUES ('max_users', '0')")
    conn.commit()
    conn.close()

init_db()

# Login required decorator
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get("user_id") is None:
            flash("You must be logged in", "error")
            return redirect("/login")
        return f(*args, **kwargs)
    return decorated_function

@app.after_request
def after_request(response):
    """Ensure responses aren't cached"""
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        
        # Validate inputs
        if not username or not password:
            flash("Username and password required", "error")
            return redirect("/login")
        
        # Query database
        conn = sqlite3.connect('users.db')
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE username = ?", (username,))
        user = cursor.fetchone()
        conn.close()
        
        # Check credentials
        if user is None or not check_password_hash(user["password"], password):
            flash("Invalid username or password", "error")
            return redirect("/login")
        
        # Store user in session
        session["user_id"] = user["id"]
        session["username"] = user["username"]
        flash(f"Welcome, {username}!", "success")
        return redirect("/")
    
    return render_template("login.html")

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        confirm_password = request.form.get("confirm_password")
        
        # Validate inputs
        if not username or not password or not confirm_password:
            flash("All fields required", "error")
            return redirect("/register")
        
        if password != confirm_password:
            flash("Passwords do not match", "error")
            return redirect("/register")
        
        # Hash password
        hashed_password = generate_password_hash(password)

        # Determine parent (if creator is logged in) and enforce max_children
        parent_id = None
        if session.get("user_id"):
            parent_id = session.get("user_id")

        conn = sqlite3.connect('users.db')
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # Check global site-wide max users
        cursor.execute("SELECT value FROM site_settings WHERE key = 'max_users'")
        row = cursor.fetchone()
        try:
            max_users = int(row[0]) if row and row[0] is not None else 0
        except Exception:
            max_users = 0
        if max_users > 0:
            cursor.execute("SELECT COUNT(*) FROM users")
            total = cursor.fetchone()[0]
            if total >= max_users:
                conn.close()
                flash("Site user limit reached", "error")
                return redirect("/register")

        # If creating under a parent, check parent's max_children (optional per-user limit)
        if parent_id is not None:
            cursor.execute("SELECT max_children FROM users WHERE id = ?", (parent_id,))
            row = cursor.fetchone()
            max_children = row["max_children"] if row and row["max_children"] is not None else 0
            cursor.execute("SELECT COUNT(*) as cnt FROM users WHERE parent_id = ?", (parent_id,))
            cnt = cursor.fetchone()[0]
            if cnt >= max_children:
                conn.close()
                flash("User creation limit reached for your account", "error")
                return redirect("/register")

        # Try to insert into database
        try:
            if parent_id is None:
                cursor.execute("INSERT INTO users (username, password) VALUES (?, ?)", (username, hashed_password))
            else:
                cursor.execute("INSERT INTO users (username, password, parent_id) VALUES (?, ?, ?)", (username, hashed_password, parent_id))
            conn.commit()
            flash("Account created! Please log in.", "success")
            return redirect("/login")
        except sqlite3.IntegrityError:
            flash("Username already exists", "error")
            return redirect("/register")
        finally:
            conn.close()
    
    return render_template("register.html")

@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out", "success")
    return redirect("/")


@app.route('/account/settings', methods=['GET', 'POST'])
def account_settings():
    # only for logged-in users
    if session.get('user_id') is None:
        flash('You must be logged in to access account settings', 'error')
        return redirect('/login')

    user_id = session.get('user_id')
    conn = sqlite3.connect('users.db')
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    if request.method == 'POST':
        # Update site-wide max users setting instead of per-user
        try:
            new_max = int(request.form.get('max_users', 0))
            if new_max < 0:
                raise ValueError
        except ValueError:
            flash('Invalid value for max users', 'error')
            conn.close()
            return redirect('/account/settings')

        cursor.execute("UPDATE site_settings SET value = ? WHERE key = 'max_users'", (str(new_max),))
        conn.commit()
        flash('Site user limit updated', 'success')

    cursor.execute('SELECT username FROM users WHERE id = ?', (user_id,))
    user = cursor.fetchone()
    # Read current site-wide max
    cursor.execute("SELECT value FROM site_settings WHERE key = 'max_users'")
    row = cursor.fetchone()
    conn.close()
    current_max = int(row[0]) if row and row[0] is not None else 0
    return render_template('account_settings.html', username=user['username'], max_users=current_max)

@app.route("/")
def index():
    if session.get("user_id"):
        return render_template("home.html", username=session.get("username"))
    return render_template("index.html")

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)