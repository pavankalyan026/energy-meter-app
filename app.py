import os
import re
import sqlite3
import csv
from datetime import datetime
from flask import Flask, render_template, request, Response, send_from_directory
from PIL import Image
import pytesseract
import os
import sqlite3

# Define absolute paths for Render
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DB_PATH = os.path.join(BASE_DIR, "energy.db")

def get_db():
    # check_same_thread=False is important for production web servers
    return sqlite3.connect(DB_PATH, check_same_thread=False)

# In your init_db function, ensure the 'readings' table is also created!
def init_db():
    con = get_db()
    cur = con.cursor()
    cur.execute("CREATE TABLE IF NOT EXISTS meters (meter_id TEXT PRIMARY KEY, location TEXT)")
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


app = Flask(__name__)

UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# ---------- DATABASE ----------

import sqlite3

DB_PATH = "energy.db"   # ✅ define database path

def get_db():
    return sqlite3.connect(DB_PATH)

def init_db():
    con = get_db()
    cur = con.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS meters (
            meter_id TEXT PRIMARY KEY,
            location TEXT
        )
    """)

    con.commit()   # ✅ save changes
    con.close()    # ✅ close connection
    print("DB initialized")
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

def read_meter_from_image(image_path):
    try:
        img = Image.open(image_path).convert("L")
        img = img.resize((800, 300))
        text = pytesseract.image_to_string(
            img,
            config="--psm 7 -c tessedit_char_whitelist=0123456789."
        )
        numbers = re.findall(r"\d+\.\d+|\d+", text)
        return float(numbers[0]) if numbers else None
    except:
        return None    

# ---------- ROUTES ----------

@app.route("/", methods=["GET", "POST"])
def meter_master():
    msg = ""

    try:
        if request.method == "POST":
            meter_id = request.form["meter_id"]
            location = request.form["location"]

            con = get_db()
            cur = con.cursor()
            cur.execute(
                "INSERT INTO meters (meter_id, location) VALUES (?,?)",
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

    except Exception as e:
        return f"<h3>Startup Error</h3><pre>{str(e)}</pre>"

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
    meter_id = request.form["meter_id"]
    user = request.form["user"]
    closing = float(request.form["current"])
    photo = request.files.get("photo")

    if photo is None or photo.filename == "":
        return "Photo is mandatory"

    opening = get_opening_reading(meter_id)
    if closing < opening:
        return "Closing reading cannot be less than opening reading"

    consumption = closing - opening
    filename = f"{meter_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
    photo_path = os.path.join(UPLOAD_FOLDER, filename)
    photo.save(photo_path)

    con = get_db()
    cur = con.cursor()
    cur.execute(
        """
        INSERT INTO readings
        (meter_id, opening, closing, consumption, user, date, photo)
        VALUES (?,?,?,?,?,?,?)
        """,
        (meter_id, opening, closing, consumption, user,
         datetime.now().strftime("%d-%m-%Y %H:%M"), photo_path)
    )
    con.commit()
    con.close()

    return f"""
    <h3>Daily Reading Saved</h3>"
    <p>Meter: {meter_id} | Consumption: {consumption}</p>
    <a href="/reading">Back to Entry</a> | <a href="/view">View Records</a>
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
    # Fixed query to match existing table columns
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
            photo_name = r[7].split("/")[-1] if r[7] else ""
            yield f"{r[0]},{r[1]},{r[2]},{r[3]},{r[4]},{r[5]},{r[6]},{photo_name}\n"

    return Response(
        generate(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=energy_readings.csv"}
    )

@app.route("/delete/<int:rid>")
def delete_reading(rid):
    admin_name = "Pavan" 
    con = get_db()
    cur = con.cursor()
    cur.execute("SELECT user FROM readings WHERE id=?", (rid,))
    row = cur.fetchone()

    if not row or row[0] != admin_name:
        return "Not authorized"

    cur.execute("DELETE FROM readings WHERE id=?", (rid,))
    con.commit()
    con.close()
    return " Deleted <br><a href='/view'>Back</a>"

@app.route("/uploads/<path:filename>")
def uploaded_file(filename):
    return send_from_directory(UPLOAD_FOLDER, filename)

if __name__ == "__main__":
   import os

port = int(os.environ.get("PORT", 5000))
app.run(host="0.0.0.0", port=port)

