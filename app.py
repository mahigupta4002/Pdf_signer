import os
import fitz
import sqlite3
from flask import Flask, request, render_template, redirect, url_for, send_file, session, flash, g

app = Flask(__name__)
app.secret_key = "secret123"

UPLOAD_FOLDER = "uploads"
SIGNED_FOLDER = "signed"
DB_FILE = "requests.db"
SIGNATURE_FILE = os.path.join("static", "signature.png")

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(SIGNED_FOLDER, exist_ok=True)

# ---------------- DB helpers ----------------
from flask import redirect, url_for

@app.route("/")
def index():
    # redirect anyone hitting the root URL to the login page
    return redirect(url_for('login'))   # <- 'login' must match the name of your login view function

def get_db():
    # returns a sqlite3.Connection with row_factory=sqlite3.Row
    db = getattr(g, "_database", None)
    if db is None:
        db = sqlite3.connect(DB_FILE)
        db.row_factory = sqlite3.Row
        g._database = db
    return db

@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, "_database", None)
    if db is not None:
        db.close()

def init_db():
    conn = sqlite3.connect(DB_FILE)
    try:
        conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE,
            password TEXT,
            role TEXT
        )
        """)
        conn.execute("""
        CREATE TABLE IF NOT EXISTS requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pdf_path TEXT,
            signed_path TEXT,
            status TEXT,
            user_id INTEGER,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
        """)
        # Create default admin if missing
        cur = conn.execute("SELECT * FROM users WHERE role='admin'")
        if cur.fetchone() is None:
            conn.execute("INSERT INTO users (username, password, role) VALUES (?, ?, ?)",
                         ("admin", "admin123", "admin"))
        conn.commit()
    finally:
        conn.close()

init_db()

# ---------------- PDF stamping ----------------
# Safe, robust stamp_pdf: always places signature bottom-right and prevents type errors
def stamp_pdf(input_pdf, output_pdf, size=(120, 60), margin=20, signature_path=SIGNATURE_FILE):
    """
    Always place the admin signature at the bottom-right corner of each page.
    - size: (width, height) in points. If values are strings they will be coerced.
    - margin: distance from page edges in points. coerced to float/int.
    - signature_path: path to signature image file.
    """
    # Coerce size and margin to numbers (float)
    try:
        w_req = float(size[0])
        h_req = float(size[1])
    except Exception:
        # fallback to defaults if coercion fails
        print("Warning: invalid size provided, falling back to (120,60). Received:", size)
        w_req, h_req = 120.0, 60.0

    try:
        margin = float(margin)
    except Exception:
        print("Warning: invalid margin provided, falling back to 20. Received:", margin)
        margin = 20.0

    # Ensure the signature file exists
    if not os.path.isfile(signature_path):
        raise FileNotFoundError(f"Signature file not found: {signature_path}")

    doc = fitz.open(input_pdf)

    for page_index, page in enumerate(doc, start=1):
        pw = float(page.rect.width)
        ph = float(page.rect.height)

        # Compute usable space (at least 10 pts)
        usable_w = max(10.0, pw - 2.0 * margin)
        usable_h = max(10.0, ph - 2.0 * margin)

        # Clamp requested size to usable area
        rect_w = min(w_req, usable_w)
        rect_h = min(h_req, usable_h)

        # If rect_w or rect_h somehow <= 0, force safe defaults
        if rect_w <= 0 or rect_h <= 0:
            rect_w = min(120.0, usable_w)
            rect_h = min(60.0, usable_h)

        # Bottom-right coordinates (keep margin from edges)
        x0 = pw - margin - rect_w
        y0 = ph - margin - rect_h
        x1 = pw - margin
        y1 = ph - margin

        # Safety: clamp coordinates inside page
        x0 = max(0.0, x0)
        y0 = max(0.0, y0)
        x1 = min(pw, x1)
        y1 = min(ph, y1)

        rect = fitz.Rect(x0, y0, x1, y1)

        # Insert signature image into the rectangle (keep_proportion ensures aspect ratio)
        try:
            page.insert_image(rect, filename=signature_path, keep_proportion=True)
        except Exception as e:
            # Helpful debug info — include page index
            print(f"Failed inserting image on page {page_index}: {e}")
            raise

    doc.save(output_pdf)


# ---------------- Auth ----------------
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form["username"].strip()
        password = request.form["password"].strip()
        if not username or not password:
            flash("Username and password required")
            return render_template("register.html", title="Register")
        db = get_db()
        try:
            db.execute("INSERT INTO users (username, password, role) VALUES (?, ?, ?)",
                       (username, password, "user"))
            db.commit()
            flash("Registration successful. Please login.")
            return redirect(url_for("login"))
        except sqlite3.IntegrityError:
            flash("Username already exists")
    return render_template("register.html", title="Register")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"].strip()
        password = request.form["password"].strip()
        db = get_db()
        row = db.execute("SELECT * FROM users WHERE username=? AND password=?", (username, password)).fetchone()
        if row:
            session["user_id"] = row["id"]
            session["username"] = row["username"]
            session["role"] = row["role"]
            return redirect(url_for("admin_panel" if row["role"] == "admin" else "user_dashboard"))
        flash("Invalid credentials")
    return render_template("login.html", title="Login")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

# ---------------- User ----------------
@app.route("/upload", methods=["GET", "POST"])
def upload():
    if "user_id" not in session or session.get("role") != "user":
        return redirect(url_for("login"))
    if request.method == "POST":
        pdf_file = request.files.get("pdf")
        if not pdf_file or not pdf_file.filename.lower().endswith(".pdf"):
            flash("Please upload a PDF file")
            return render_template("upload.html", title="Upload")
        pdf_path = os.path.join(UPLOAD_FOLDER, pdf_file.filename)
        pdf_file.save(pdf_path)
        db = get_db()
        db.execute("INSERT INTO requests (pdf_path, signed_path, status, user_id) VALUES (?, ?, ?, ?)",
                   (pdf_path, "", "pending", session["user_id"]))
        db.commit()
        flash("Uploaded and pending admin approval")
        return redirect(url_for("user_dashboard"))
    return render_template("upload.html", title="Upload")

@app.route("/dashboard")
def user_dashboard():
    if "user_id" not in session:
        return redirect(url_for("login"))
    db = get_db()
    rows = db.execute("SELECT * FROM requests WHERE user_id=? ORDER BY id DESC", (session["user_id"],)).fetchall()
    return render_template("dashboard.html", requests=rows, username=session.get("username"), title="Dashboard")

@app.route("/download/<int:req_id>")
def download_file(req_id):
    if "user_id" not in session:
        return redirect(url_for("login"))
    db = get_db()
    req = db.execute("SELECT * FROM requests WHERE id=?", (req_id,)).fetchone()
    if not req:
        return "Request not found", 404
    # req["status"], req["signed_path"], req["user_id"]
    if req["status"] == "approved" and req["user_id"] == session["user_id"] and req["signed_path"]:
        return send_file(req["signed_path"], as_attachment=True)
    return "File not available yet."

# ---------------- Admin ----------------
@app.route("/admin/panel")
def admin_panel():
    if session.get("role") != "admin":
        return redirect(url_for("login"))
    db = get_db()
    # join to get username; alias columns so template keys are clear
    rows = db.execute("""
        SELECT r.id as id, u.username as username, r.pdf_path as pdf_path,
               r.status as status, r.signed_path as signed_path
        FROM requests r
        JOIN users u ON r.user_id = u.id
        ORDER BY r.id DESC
    """).fetchall()
    return render_template("admin.html", requests=rows, title="Admin Panel")

@app.route("/admin/approve/<int:req_id>")
def approve(req_id):
    if session.get("role") != "admin":
        return redirect(url_for("login"))
    db = get_db()
    req = db.execute("SELECT * FROM requests WHERE id=?", (req_id,)).fetchone()
    if not req:
        flash("Request not found")
        return redirect(url_for("admin_panel"))
    # produce signed path
    signed_path = os.path.join(SIGNED_FOLDER, f"signed_{os.path.basename(req['pdf_path'])}")
    # stamp using signature file
    stamp_pdf(req["pdf_path"], signed_path, SIGNATURE_FILE)
    db.execute("UPDATE requests SET signed_path=?, status=? WHERE id=?", (signed_path, "approved", req_id))
    db.commit()
    flash("Approved and signed")
    return redirect(url_for("admin_panel"))

@app.route("/admin/reject/<int:req_id>")
def reject(req_id):
    if session.get("role") != "admin":
        return redirect(url_for("login"))
    db = get_db()
    db.execute("UPDATE requests SET status=? WHERE id=?", ("rejected", req_id))
    db.commit()
    flash("Request rejected")
    return redirect(url_for("admin_panel"))

@app.route("/admin/settings", methods=["GET", "POST"])
def admin_settings():
    if session.get("role") != "admin":
        return redirect(url_for("login"))
    if request.method == "POST":
        sig = request.files.get("signature")
        if sig:
            sig.save(SIGNATURE_FILE)
            flash("Signature updated")
        newpass = request.form.get("password")
        if newpass:
            db = get_db()
            db.execute("UPDATE users SET password=? WHERE username='admin'", (newpass,))
            db.commit()
            flash("Password updated")
    return render_template("settings.html", title="Settings")


# ---------------- Admin: view uploaded PDF in browser ----------------
@app.route("/admin/view/<int:req_id>")
def admin_view_pdf(req_id):
    if session.get("role") != "admin":
        return redirect(url_for("login"))

    db = get_db()
    req = db.execute("SELECT * FROM requests WHERE id=?", (req_id,)).fetchone()
    if not req:
        flash("Request not found")
        return redirect(url_for("admin_panel"))

    pdf_path = req["pdf_path"]
    if not pdf_path or not os.path.isfile(pdf_path):
        flash("PDF file not available on server")
        return redirect(url_for("admin_panel"))

    # Browser will try to open the PDF inline
    return send_file(pdf_path, as_attachment=False)


# ---------------- Admin: upload a PDF (admin uploads for signing) ----------------
@app.route("/admin/upload", methods=["GET", "POST"])
def admin_upload_pdf():
    if session.get("role") != "admin":
        return redirect(url_for("login"))

    if request.method == "POST":
        pdf_file = request.files.get("pdf")
        if not pdf_file or not pdf_file.filename.lower().endswith(".pdf"):
            flash("Please choose a PDF file")
            return render_template("admin_upload.html", title="Admin Upload")

        # Save uploaded file
        safe_name = pdf_file.filename
        pdf_path = os.path.join(UPLOAD_FOLDER, safe_name)
        pdf_file.save(pdf_path)

        # Create signed output and stamp immediately using SIGNATURE_FILE
        signed_name = f"signed_admin_{os.path.basename(safe_name)}"
        signed_path = os.path.join(SIGNED_FOLDER, signed_name)

        try:
            stamp_pdf(pdf_path, signed_path, SIGNATURE_FILE)
        except Exception as e:
            flash(f"Failed to stamp PDF: {e}")
            return render_template("admin_upload.html", title="Admin Upload")

        # Insert into requests table as 'approved' and user_id = admin's id
        db = get_db()
        db.execute(
            "INSERT INTO requests (pdf_path, signed_path, status, user_id) VALUES (?, ?, ?, ?)",
            (pdf_path, signed_path, "approved", session["user_id"])
        )
        db.commit()
        flash("PDF uploaded and signed successfully")
        return redirect(url_for("admin_panel"))

    return render_template("admin_upload.html", title="Admin Upload")

# if __name__ == "__main__":
#     app.run(debug=True)

if __name__ == "__main__":
    init_db()
    app.run(debug=True)


