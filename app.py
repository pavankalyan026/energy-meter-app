import os
import sqlite3
from datetime import datetime
from flask import Flask, render_template, request, Response, send_from_directory

app = Flask(__name__)

# ---------- CONFIGURATION (RAILWAY SAFE) ----------
import os

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

# Detect Railway environment
IS_RAILWAY = os.environ.get("RAILWAY_ENVIRONMENT") is not None

if IS_RAILWAY:
    DB_PATH = "/tmp/energy.db"
    UPLOAD_FOLDER = "/tmp/uploads"
else:
    DB_PATH = os.path.join(BASE_DIR, "energy.db")
    UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")

os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# ---------- DATABASE ----------

def get_db():
    return sqlite3.connect(DB_PATH, check_same_thread=False)

def init_db():
    try:
        con = get_db()
        cur = con.cursor()

        cur.execute("""
            CREATE TABLE IF NOT EXISTS meters (
                meter_id TEXT PRIMARY KEY,
                location TEXT
            )
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS readings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                meter_id TEXT,
                opening REAL,
                closing REAL,
                consumption REAL,
                user TEXT,
                date TEXT,
                photo TEXT
            )
        """)

        con.commit()
        con.close()
        print("DB initialized")

    except Exception as e:
        print("DB INIT ERROR:", e)

# Initialize DB safely
init_db()

# ---------- HELPERS ----------

def get_opening_reading(meter_id):
    con = get_db()
    cur = con.cursor()
    cur.execute(
        "SELECT closing FROM readings WHERE meter_id=? ORDER BY id DESC LIMIT 1",
        (meter_id,)
    )
    row = cur.fetchone()
    con.close()
    return row[0] if row else 0.0

# ---------- ROUTES ----------

@app.route("/", methods=["GET", "POST"])
def meter_master():
    msg = ""

    if request.method == "POST":
        meter_id = request.form.get("meter_id")
        location = request.form.get("location")

        if meter_id and location:
            con = get_db()
            cur = con.cursor()
            cur.execute(
                "INSERT OR IGNORE INTO meters VALUES (?,?)",
                (meter_id, location)
            )
            con.commit()
            con.close()
            msg = "Meter added successfully"

    con = get_db()
    cur = con.cursor()
    cur.execute("SELECT * FROM meters")
    meters = cur.fetchall()
    con.close()

    return render_template("meters.html", meters=meters, msg=msg)

@app.route("/reading")
def reading():
    con = get_db()
    cur = con.cursor()
    cur.execute("SELECT meter_id FROM meters")
    meters = cur.fetchall()
    con.close()
    return render_template("reading.html", meters=meters)

@app.route("/save_reading", methods=["POST"])
def save_reading():
    meter_id = request.form.get("meter_id")
    user = request.form.get("user")
    closing = float(request.form.get("current"))
    photo = request.files.get("photo")

    if not photo or photo.filename == "":
        return "Error: Photo is mandatory"

    opening = get_opening_reading(meter_id)
    if closing < opening:
        return "Error: Closing reading cannot be less than opening"

    consumption = closing - opening

    filename = f"{meter_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
    photo_path = os.path.join(UPLOAD_FOLDER, filename)
    photo.save(photo_path)

    con = get_db()
    cur = con.cursor()
    cur.execute("""
        INSERT INTO readings
        (meter_id, opening, closing, consumption, user, date, photo)
        VALUES (?,?,?,?,?,?,?)
    """, (
        meter_id,
        opening,
        closing,
        consumption,
        user,
        datetime.now().strftime("%d-%m-%Y %H:%M"),
        filename
    ))
    con.commit()
    con.close()

    return """
        <h3>Reading Saved</h3>
        <a href="/reading">Back</a> | <a href="/view">View Records</a>
    """

@app.route("/view")
def view_readings():
    con = get_db()
    cur = con.cursor()
    cur.execute("""
        SELECT r.id, r.meter_id, m.location, r.opening, r.closing,
               r.consumption, r.user, r.date, r.photo
        FROM readings r
        JOIN meters m ON r.meter_id = m.meter_id
        ORDER BY r.id DESC
    """)
    rows = cur.fetchall()
    con.close()
    return render_template("view.html", rows=rows)

@app.route("/export")
def export():
    con = get_db()
    cur = con.cursor()
    cur.execute("""
        SELECT r.meter_id, m.location, r.opening, r.closing,
               r.consumption, r.user, r.date, r.photo
        FROM readings r
        JOIN meters m ON r.meter_id = m.meter_id
        ORDER BY r.id DESC
    """)
    rows = cur.fetchall()
    con.close()

    def generate():
        yield "Meter ID,Location,Opening,Closing,Consumption,User,Date,Photo\n"
        for r in rows:
            yield f"{r[0]},{r[1]},{r[2]},{r[3]},{r[4]},{r[5]},{r[6]},{r[7]}\n"

    return Response(
        generate(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=energy_readings.csv"}
    )

@app.route("/uploads/<path:filename>")
def uploaded_file(filename):
    return send_from_directory(UPLOAD_FOLDER, filename)

# ---------- START ----------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)