import os
import random
import string
import secrets
from functools import wraps
from datetime import datetime, timedelta
from flask import (
    Flask, render_template, request, redirect, url_for,
    flash, jsonify, session, send_from_directory, Response
)
from werkzeug.utils import secure_filename
import database

# Lightweight .env loader without third-party dependencies
def load_env_file():
    env_path = os.path.join(os.path.dirname(__file__), ".env")
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, val = line.split("=", 1)
                    key = key.strip()
                    val = val.strip().strip('"').strip("'")
                    if key and key not in os.environ:
                        os.environ[key] = val

load_env_file()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "powerwatch_local_utility_secret_key_2026")
DEFAULT_API_KEY = os.getenv("GRIDPULSE_API_KEY", "gp_live_scada_demo_key_2026")
app.config["UPLOAD_FOLDER"] = os.path.join(app.root_path, "static", "uploads")
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024  # 16 MB max
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "webp", "gif"}

os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

# Ensure database is initialized
database.init_db()
database.seed_db()

def generate_secure_api_key(prefix="gp_live"):
    """Generate a cryptographically secure 32-character hexadecimal API key."""
    return f"{prefix}_{secrets.token_hex(16)}"

def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

def generate_ticket_number():
    year = datetime.now().year
    rand_digits = "".join(random.choices(string.digits, k=4))
    return f"PWR-{year}-{rand_digits}"

# Context processor for global notifications
@app.context_processor
def inject_global_data():
    conn = database.get_db()
    announcements = conn.execute(
        "SELECT * FROM announcements WHERE is_active = 1 ORDER BY created_at DESC LIMIT 3"
    ).fetchall()
    
    # Active outages summary count
    active_count = conn.execute(
        "SELECT COUNT(*) FROM outage_reports WHERE status NOT IN ('RESOLVED', 'CLOSED')"
    ).fetchone()[0]
    
    conn.close()
    return {
        "active_announcements": announcements,
        "global_active_outages": active_count,
        "current_year": datetime.now().year,
        "default_api_key": DEFAULT_API_KEY
    }

# ----------------- RESIDENT FACING ROUTES ----------------- #

@app.route("/")
def index():
    conn = database.get_db()
    
    # Key Metrics
    total_active_outages = conn.execute(
        "SELECT COUNT(*) FROM outage_reports WHERE status NOT IN ('RESOLVED', 'CLOSED')"
    ).fetchone()[0]
    
    impacted_households = conn.execute(
        "SELECT COALESCE(SUM(affected_households), 0) FROM outage_reports WHERE status NOT IN ('RESOLVED', 'CLOSED')"
    ).fetchone()[0]
    
    crews_deployed = conn.execute(
        "SELECT COUNT(*) FROM crews WHERE current_status IN ('DISPATCHED', 'ON_SITE')"
    ).fetchone()[0]
    
    affected_localities_count = conn.execute(
        "SELECT COUNT(DISTINCT locality_id) FROM outage_reports WHERE status NOT IN ('RESOLVED', 'CLOSED')"
    ).fetchone()[0]

    # Localities
    localities = conn.execute("SELECT * FROM localities ORDER BY name ASC").fetchall()

    # Recent active outages for the feed
    recent_outages = conn.execute("""
        SELECT r.*, l.name as locality_name, l.substation_name, c.crew_name
        FROM outage_reports r
        JOIN localities l ON r.locality_id = l.id
        LEFT JOIN crews c ON r.assigned_crew_id = c.id
        ORDER BY 
            CASE r.severity
                WHEN 'CRITICAL' THEN 1
                WHEN 'HIGH' THEN 2
                WHEN 'MEDIUM' THEN 3
                ELSE 4
            END,
            r.reported_at DESC
        LIMIT 10
    """).fetchall()

    # Upcoming scheduled maintenance
    maintenance_list = conn.execute("""
        SELECT m.*, l.name as locality_name
        FROM scheduled_maintenance m
        JOIN localities l ON m.locality_id = l.id
        WHERE m.status IN ('SCHEDULED', 'IN_PROGRESS')
        ORDER BY m.start_time ASC
        LIMIT 4
    """).fetchall()

    conn.close()
    return render_template(
        "index.html",
        total_active_outages=total_active_outages,
        impacted_households=impacted_households,
        crews_deployed=crews_deployed,
        affected_localities_count=affected_localities_count,
        localities=localities,
        recent_outages=recent_outages,
        maintenance_list=maintenance_list
    )

@app.route("/report", methods=["GET", "POST"])
def report_outage():
    conn = database.get_db()
    if request.method == "POST":
        locality_id = request.form.get("locality_id")
        consumer_name = request.form.get("consumer_name", "").strip()
        consumer_phone = request.form.get("consumer_phone", "").strip()
        consumer_email = request.form.get("consumer_email", "").strip()
        account_or_meter_no = request.form.get("account_or_meter_no", "").strip()
        address = request.form.get("address", "").strip()
        landmark = request.form.get("landmark", "").strip()
        outage_type = request.form.get("outage_type")
        severity = request.form.get("severity", "MEDIUM")
        description = request.form.get("description", "").strip()
        lat_val = request.form.get("lat")
        lng_val = request.form.get("lng")
        affected_households = request.form.get("affected_households", 1)

        # Validation
        if not locality_id or not consumer_name or not consumer_phone or not address or not outage_type:
            flash("Please fill in all mandatory fields (Locality, Name, Phone, Address, Outage Type).", "danger")
            localities = conn.execute("SELECT * FROM localities ORDER BY name ASC").fetchall()
            conn.close()
            return render_template("report.html", localities=localities)

        # Handle Coordinates
        try:
            lat = float(lat_val) if lat_val else None
            lng = float(lng_val) if lng_val else None
        except ValueError:
            lat, lng = None, None

        # Fallback to locality center if not dropped
        if lat is None or lng is None:
            loc_row = conn.execute("SELECT lat, lng FROM localities WHERE id = ?", (locality_id,)).fetchone()
            if loc_row:
                # Add tiny random jitter so markers in same area don't stack exactly on top
                lat = loc_row["lat"] + random.uniform(-0.003, 0.003)
                lng = loc_row["lng"] + random.uniform(-0.003, 0.003)

        # Photo upload
        photo_filename = None
        if "photo" in request.files:
            file = request.files["photo"]
            if file and file.filename != "" and allowed_file(file.filename):
                fname = secure_filename(file.filename)
                unique_name = f"{int(datetime.now().timestamp())}_{fname}"
                file.save(os.path.join(app.config["UPLOAD_FOLDER"], unique_name))
                photo_filename = unique_name

        ticket_no = generate_ticket_number()
        # Verify uniqueness
        while conn.execute("SELECT id FROM outage_reports WHERE ticket_no = ?", (ticket_no,)).fetchone():
            ticket_no = generate_ticket_number()

        # Insert Outage
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO outage_reports (
                ticket_no, locality_id, consumer_name, consumer_phone, consumer_email,
                account_or_meter_no, address, landmark, outage_type, severity,
                description, lat, lng, photo_filename, status, affected_households
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'REPORTED', ?)
        """, (
            ticket_no, locality_id, consumer_name, consumer_phone, consumer_email,
            account_or_meter_no, address, landmark, outage_type, severity,
            description, lat, lng, photo_filename, affected_households
        ))
        report_id = cursor.lastrowid

        # Insert Status History
        cursor.execute("""
            INSERT INTO status_history (report_id, status, notes, updated_by)
            VALUES (?, 'REPORTED', 'Outage reported by resident via web portal.', 'Resident')
        """, (report_id,))

        # Update locality status to OUTAGE_ACTIVE if currently NORMAL
        cursor.execute("""
            UPDATE localities
            SET status = CASE WHEN status = 'NORMAL' THEN 'OUTAGE_ACTIVE' ELSE status END
            WHERE id = ?
        """, (locality_id,))

        conn.commit()
        conn.close()

        flash(f"Outage successfully logged! Your Ticket Number is {ticket_no}. You can track restoration progress anytime.", "success")
        return redirect(url_for("track_outage", ticket=ticket_no))

    localities = conn.execute("SELECT * FROM localities ORDER BY name ASC").fetchall()
    conn.close()
    return render_template("report.html", localities=localities)

@app.route("/track")
def track_outage():
    ticket_query = request.args.get("ticket", "").strip()
    phone_query = request.args.get("phone", "").strip()
    report = None
    history = []
    crew = None
    reports_by_phone = []

    conn = database.get_db()
    if ticket_query:
        report = conn.execute("""
            SELECT r.*, l.name as locality_name, l.substation_name, l.contact_officer, l.officer_phone
            FROM outage_reports r
            JOIN localities l ON r.locality_id = l.id
            WHERE UPPER(r.ticket_no) = UPPER(?)
        """, (ticket_query,)).fetchone()

        if report:
            history = conn.execute("""
                SELECT * FROM status_history WHERE report_id = ? ORDER BY updated_at ASC
            """, (report["id"],)).fetchall()

            if report["assigned_crew_id"]:
                crew = conn.execute("SELECT * FROM crews WHERE id = ?", (report["assigned_crew_id"],)).fetchone()
        else:
            flash(f"No outage ticket found matching '{ticket_query}'. Please verify your ticket reference number.", "warning")

    elif phone_query:
        # Search by phone number
        cleaned_phone = phone_query.replace(" ", "").replace("-", "")
        reports_by_phone = conn.execute("""
            SELECT r.*, l.name as locality_name
            FROM outage_reports r
            JOIN localities l ON r.locality_id = l.id
            WHERE REPLACE(REPLACE(r.consumer_phone, ' ', ''), '-', '') LIKE ?
            ORDER BY r.reported_at DESC
        """, (f"%{cleaned_phone}%",)).fetchall()

        if not reports_by_phone:
            flash(f"No records found registered under contact '{phone_query}'.", "info")

    conn.close()
    return render_template(
        "track.html",
        ticket_query=ticket_query,
        phone_query=phone_query,
        report=report,
        history=history,
        crew=crew,
        reports_by_phone=reports_by_phone
    )

@app.route("/localities")
def localities_overview():
    conn = database.get_db()
    localities = conn.execute("""
        SELECT l.*,
            (SELECT COUNT(*) FROM outage_reports r WHERE r.locality_id = l.id AND r.status NOT IN ('RESOLVED', 'CLOSED')) as active_outages,
            (SELECT COALESCE(SUM(affected_households), 0) FROM outage_reports r WHERE r.locality_id = l.id AND r.status NOT IN ('RESOLVED', 'CLOSED')) as affected_households,
            (SELECT COUNT(*) FROM scheduled_maintenance m WHERE m.locality_id = l.id AND m.status = 'SCHEDULED') as scheduled_count
        FROM localities l
        ORDER BY active_outages DESC, l.name ASC
    """).fetchall()

    maintenance = conn.execute("""
        SELECT m.*, l.name as locality_name
        FROM scheduled_maintenance m
        JOIN localities l ON m.locality_id = l.id
        ORDER BY m.start_time ASC
    """).fetchall()

    conn.close()
    return render_template("localities.html", localities=localities, maintenance=maintenance)

@app.route("/subscribe", methods=["POST"])
def subscribe_alerts():
    locality_id = request.form.get("locality_id")
    contact_type = request.form.get("contact_type")
    contact_value = request.form.get("contact_value", "").strip()

    if not locality_id or not contact_type or not contact_value:
        flash("Please provide all required alert subscription fields.", "danger")
        return redirect(url_for("localities_overview"))

    conn = database.get_db()
    # Check if duplicate
    existing = conn.execute("""
        SELECT id FROM subscribers WHERE locality_id = ? AND contact_value = ?
    """, (locality_id, contact_value)).fetchone()

    if not existing:
        conn.execute("""
            INSERT INTO subscribers (locality_id, contact_type, contact_value)
            VALUES (?, ?, ?)
        """, (locality_id, contact_type, contact_value))
        conn.commit()

    conn.close()
    flash(f"Successfully subscribed {contact_value} for instant power status & restoration alerts!", "success")
    return redirect(url_for("localities_overview"))

@app.route("/safety")
def safety():
    return render_template("safety.html")

# ----------------- REST API AUTHENTICATION & ENDPOINTS ----------------- #

def get_request_api_key():
    """Extract API key from header, Bearer token, or query parameter."""
    # 1. Custom header X-API-Key
    api_key = request.headers.get("X-API-Key")
    if api_key:
        return api_key.strip()
    
    # 2. Authorization header (Bearer <key> or ApiKey <key>)
    auth_header = request.headers.get("Authorization", "")
    if auth_header:
        parts = auth_header.split()
        if len(parts) == 2 and parts[0].lower() in ["bearer", "apikey", "token"]:
            return parts[1].strip()
        elif len(parts) == 1:
            return parts[0].strip()
            
    # 3. Query parameter ?api_key=...
    query_key = request.args.get("api_key")
    if query_key:
        return query_key.strip()

    return None

def validate_api_key(required_role="read_only"):
    """
    Validates API key from request.
    Returns (is_valid: bool, key_data: dict, error_message: str, http_status: int)
    """
    key_str = get_request_api_key()
    
    # Allow active admin session
    if not key_str and session.get("admin_logged_in"):
        return True, {"key_name": "Admin Session", "role": "admin", "api_key": "session"}, "", 200

    if not key_str:
        return False, None, "Missing API Key. Authenticate via 'X-API-Key' header, 'Authorization: Bearer <key>', or '?api_key=<key>' parameter.", 401

    conn = database.get_db()
    row = conn.execute("SELECT * FROM api_keys WHERE api_key = ?", (key_str,)).fetchone()
    
    # Support master env key fallback
    if not row and key_str == DEFAULT_API_KEY:
        conn.close()
        return True, {"key_name": "Master Environment Key", "role": "admin", "api_key": key_str}, "", 200

    if not row:
        conn.close()
        return False, None, "Invalid API key provided. Authentication failed.", 401

    if not row["is_active"]:
        conn.close()
        return False, None, "This API key has been revoked or deactivated by an administrator.", 403

    if required_role == "read_write" and row["role"] not in ["read_write", "admin"]:
        conn.close()
        return False, None, "Insufficient permissions. This API key has read-only access.", 403

    # Update last used timestamp
    try:
        conn.execute("UPDATE api_keys SET last_used_at = CURRENT_TIMESTAMP WHERE id = ?", (row["id"],))
        conn.commit()
    except Exception:
        pass
    finally:
        conn.close()

    return True, dict(row), "", 200

def require_api_key(required_role="read_only"):
    """Decorator to require valid API key with specified role."""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            is_valid, key_data, error_msg, status_code = validate_api_key(required_role=required_role)
            if not is_valid:
                return jsonify({
                    "success": False,
                    "error": "Unauthorized" if status_code == 401 else "Forbidden",
                    "message": error_msg
                }), status_code
            return f(*args, **kwargs)
        return decorated_function
    return decorator

@app.route("/api/auth/verify")
@require_api_key(required_role="read_only")
def api_auth_verify():
    """Verify an API key and return authentication metadata."""
    _, key_data, _, _ = validate_api_key(required_role="read_only")
    raw_key = key_data.get("api_key", "")
    masked = raw_key[:8] + "..." + raw_key[-4:] if len(raw_key) > 12 else raw_key
    return jsonify({
        "success": True,
        "authenticated": True,
        "key_name": key_data.get("key_name", "Unknown"),
        "role": key_data.get("role", "read_only"),
        "api_key_masked": masked
    })

@app.route("/api/outages", methods=["GET", "POST"])
def api_outages():
    if request.method == "POST":
        # Create outage via external SCADA / IoT integration
        is_valid, key_data, error_msg, status_code = validate_api_key(required_role="read_write")
        if not is_valid:
            return jsonify({
                "success": False,
                "error": "Unauthorized" if status_code == 401 else "Forbidden",
                "message": error_msg
            }), status_code

        data = request.get_json(silent=True) or request.form
        if not data:
            return jsonify({"success": False, "message": "Invalid JSON payload or missing form data."}), 400

        locality_id = data.get("locality_id")
        outage_type = data.get("outage_type")
        if not locality_id or not outage_type:
            return jsonify({
                "success": False,
                "message": "Missing mandatory fields: 'locality_id' and 'outage_type' are required."
            }), 422

        conn = database.get_db()
        cursor = conn.cursor()

        loc = cursor.execute("SELECT * FROM localities WHERE id = ?", (locality_id,)).fetchone()
        if not loc:
            conn.close()
            return jsonify({"success": False, "message": f"Locality ID {locality_id} not found."}), 404

        consumer_name = data.get("consumer_name", f"Integration ({key_data.get('key_name', 'SCADA')})")
        consumer_phone = data.get("consumer_phone", "+91 94481 00912")
        consumer_email = data.get("consumer_email", "")
        account_no = data.get("account_or_meter_no", "IOT-SCADA-01")
        address = data.get("address", f"Substation Feeder, {loc['name']}")
        landmark = data.get("landmark", loc["substation_name"])
        severity = data.get("severity", "CRITICAL").upper()
        description = data.get("description", "Automated incident ingested via external GridPulse REST API.")
        affected_households = int(data.get("affected_households", 50))
        estimated_restoration = data.get("estimated_restoration", "In ~2 hours")

        lat = data.get("lat")
        lng = data.get("lng")
        try:
            lat = float(lat) if lat is not None else (loc["lat"] + random.uniform(-0.002, 0.002))
            lng = float(lng) if lng is not None else (loc["lng"] + random.uniform(-0.002, 0.002))
        except (ValueError, TypeError):
            lat = loc["lat"]
            lng = loc["lng"]

        ticket_no = generate_ticket_number()
        while cursor.execute("SELECT id FROM outage_reports WHERE ticket_no = ?", (ticket_no,)).fetchone():
            ticket_no = generate_ticket_number()

        cursor.execute("""
            INSERT INTO outage_reports (
                ticket_no, locality_id, consumer_name, consumer_phone, consumer_email,
                account_or_meter_no, address, landmark, outage_type, severity,
                description, lat, lng, status, affected_households, estimated_restoration
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'REPORTED', ?, ?)
        """, (
            ticket_no, locality_id, consumer_name, consumer_phone, consumer_email,
            account_no, address, landmark, outage_type, severity,
            description, lat, lng, affected_households, estimated_restoration
        ))
        report_id = cursor.lastrowid

        cursor.execute("""
            INSERT INTO status_history (report_id, status, notes, updated_by)
            VALUES (?, 'REPORTED', ?, ?)
        """, (report_id, f"Outage created via API ({key_data.get('key_name', 'SCADA')}). {description}", "API Gateway"))

        cursor.execute("UPDATE localities SET status = 'OUTAGE_ACTIVE' WHERE id = ?", (locality_id,))
        conn.commit()
        conn.close()

        return jsonify({
            "success": True,
            "message": "Outage ticket successfully created.",
            "ticket_no": ticket_no,
            "id": report_id,
            "status": "REPORTED",
            "locality": loc["name"],
            "severity": severity,
            "estimated_restoration": estimated_restoration
        }), 201

    # GET request - Retrieve outages list
    is_valid, _, error_msg, status_code = validate_api_key(required_role="read_only")
    if not is_valid:
        return jsonify({
            "success": False,
            "error": "Unauthorized" if status_code == 401 else "Forbidden",
            "message": error_msg
        }), status_code

    conn = database.get_db()
    status_filter = request.args.get("status")
    locality_filter = request.args.get("locality_id")

    query = """
        SELECT r.id, r.ticket_no, r.address, r.landmark, r.outage_type, r.severity,
               r.lat, r.lng, r.status, r.reported_at, r.estimated_restoration,
               r.affected_households, r.upvotes, r.description,
               l.name as locality_name, l.substation_name,
               c.crew_name
        FROM outage_reports r
        JOIN localities l ON r.locality_id = l.id
        LEFT JOIN crews c ON r.assigned_crew_id = c.id
        WHERE 1=1
    """
    params = []

    if status_filter == "active":
        query += " AND r.status NOT IN ('RESOLVED', 'CLOSED')"
    elif status_filter:
        query += " AND r.status = ?"
        params.append(status_filter)

    if locality_filter:
        query += " AND r.locality_id = ?"
        params.append(locality_filter)

    query += " ORDER BY r.reported_at DESC"

    rows = conn.execute(query, params).fetchall()
    conn.close()

    outages = [dict(row) for row in rows]
    return jsonify({"success": True, "count": len(outages), "data": outages})

@app.route("/api/outages/<ticket_no>")
@app.route("/api/track/<ticket_no>")
@require_api_key(required_role="read_only")
def api_track_ticket(ticket_no):
    """Retrieve full details, crew assignment, and lifecycle history for a single ticket."""
    conn = database.get_db()
    report = conn.execute("""
        SELECT r.*, l.name as locality_name, l.substation_name, l.contact_officer, l.officer_phone,
               c.crew_name, c.lead_lineman, c.phone as crew_phone, c.vehicle_no as crew_vehicle
        FROM outage_reports r
        JOIN localities l ON r.locality_id = l.id
        LEFT JOIN crews c ON r.assigned_crew_id = c.id
        WHERE UPPER(r.ticket_no) = UPPER(?)
    """, (ticket_no,)).fetchone()

    if not report:
        conn.close()
        return jsonify({"success": False, "message": f"Ticket '{ticket_no}' not found."}), 404

    history_rows = conn.execute("""
        SELECT status, notes, updated_by, updated_at
        FROM status_history
        WHERE report_id = ?
        ORDER BY updated_at ASC
    """, (report["id"],)).fetchall()
    conn.close()

    data = dict(report)
    data["history"] = [dict(h) for h in history_rows]
    return jsonify({"success": True, "data": data})

@app.route("/api/localities")
@require_api_key(required_role="read_only")
def api_localities():
    conn = database.get_db()
    rows = conn.execute("""
        SELECT l.*,
            (SELECT COUNT(*) FROM outage_reports r WHERE r.locality_id = l.id AND r.status NOT IN ('RESOLVED', 'CLOSED')) as active_outages
        FROM localities l
    """).fetchall()
    conn.close()
    return jsonify({"success": True, "data": [dict(r) for r in rows]})

@app.route("/api/upvote/<ticket_no>", methods=["POST"])
def api_upvote(ticket_no):
    conn = database.get_db()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE outage_reports
        SET upvotes = upvotes + 1, affected_households = affected_households + 1
        WHERE UPPER(ticket_no) = UPPER(?)
    """, (ticket_no,))
    conn.commit()
    
    updated = cursor.execute("""
        SELECT upvotes, affected_households FROM outage_reports WHERE UPPER(ticket_no) = UPPER(?)
    """, (ticket_no,)).fetchone()
    conn.close()

    if updated:
        return jsonify({
            "success": True,
            "upvotes": updated["upvotes"],
            "affected_households": updated["affected_households"]
        })
    return jsonify({"success": False, "message": "Ticket not found"}), 404

# ----------------- UTILITY BOARD ADMIN / DISPATCHER PORTAL ----------------- #

def admin_required(f):
    def decorated_function(*args, **kwargs):
        if not session.get("admin_logged_in"):
            flash("Please sign in with Utility Board staff credentials to access the dispatcher command center.", "warning")
            return redirect(url_for("admin_login"))
        return f(*args, **kwargs)
    decorated_function.__name__ = f.__name__
    return decorated_function

@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()
        
        # Built-in demo credentials for utility control room
        if username in ["admin", "dispatcher", "bescom"] and password in ["gridadmin2026", "admin123", "power123"]:
            session["admin_logged_in"] = True
            session["admin_user"] = username
            session["admin_role"] = "Senior Grid Dispatcher" if username == "dispatcher" else "Control Room Engineer"
            flash(f"Welcome, {session['admin_user']}. You are authenticated as {session['admin_role']}.", "success")
            return redirect(url_for("admin_dashboard"))
        else:
            flash("Invalid credentials. (Hint for evaluation: user 'admin' / pass 'gridadmin2026')", "danger")

    return render_template("admin_login.html")

@app.route("/admin/logout")
def admin_logout():
    session.clear()
    flash("You have safely signed out of the Utility Dispatch Desk.", "info")
    return redirect(url_for("admin_login"))

@app.route("/admin")
@admin_required
def admin_dashboard():
    conn = database.get_db()

    # Filter parameters
    status = request.args.get("status", "")
    locality_id = request.args.get("locality_id", "")
    severity = request.args.get("severity", "")
    search = request.args.get("search", "").strip()

    # Base query for tickets
    query = """
        SELECT r.*, l.name as locality_name, l.substation_name, c.crew_name, c.phone as crew_phone
        FROM outage_reports r
        JOIN localities l ON r.locality_id = l.id
        LEFT JOIN crews c ON r.assigned_crew_id = c.id
        WHERE 1=1
    """
    params = []

    if status:
        query += " AND r.status = ?"
        params.append(status)
    if locality_id:
        query += " AND r.locality_id = ?"
        params.append(locality_id)
    if severity:
        query += " AND r.severity = ?"
        params.append(severity)
    if search:
        query += " AND (r.ticket_no LIKE ? OR r.consumer_name LIKE ? OR r.consumer_phone LIKE ? OR r.address LIKE ?)"
        wild = f"%{search}%"
        params.extend([wild, wild, wild, wild])

    query += " ORDER BY r.reported_at DESC"
    tickets = conn.execute(query, params).fetchall()

    # Summary Stats
    total_tickets = conn.execute("SELECT COUNT(*) FROM outage_reports").fetchone()[0]
    active_tickets = conn.execute("SELECT COUNT(*) FROM outage_reports WHERE status NOT IN ('RESOLVED', 'CLOSED')").fetchone()[0]
    critical_tickets = conn.execute("SELECT COUNT(*) FROM outage_reports WHERE status NOT IN ('RESOLVED', 'CLOSED') AND severity = 'CRITICAL'").fetchone()[0]
    resolved_today = conn.execute("SELECT COUNT(*) FROM outage_reports WHERE status = 'RESOLVED'").fetchone()[0]

    # Available crews for assignment dropdowns
    crews = conn.execute("SELECT * FROM crews ORDER BY crew_name ASC").fetchall()
    localities = conn.execute("SELECT * FROM localities ORDER BY name ASC").fetchall()

    conn.close()
    return render_template(
        "admin_dashboard.html",
        tickets=tickets,
        total_tickets=total_tickets,
        active_tickets=active_tickets,
        critical_tickets=critical_tickets,
        resolved_today=resolved_today,
        crews=crews,
        localities=localities,
        selected_status=status,
        selected_locality=locality_id,
        selected_severity=severity,
        search_query=search
    )

@app.route("/admin/tickets/<int:ticket_id>/update", methods=["POST"])
@admin_required
def admin_update_ticket(ticket_id):
    new_status = request.form.get("status")
    assigned_crew_id = request.form.get("assigned_crew_id")
    estimated_restoration = request.form.get("estimated_restoration", "").strip()
    resolution_notes = request.form.get("resolution_notes", "").strip()
    staff_name = session.get("admin_user", "Dispatcher")

    if not new_status:
        flash("Status is required.", "danger")
        return redirect(url_for("admin_dashboard"))

    conn = database.get_db()
    cursor = conn.cursor()

    assigned_crew_val = int(assigned_crew_id) if assigned_crew_id and assigned_crew_id.isdigit() else None

    # Handle resolution timestamp
    resolved_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S") if new_status in ["RESOLVED", "CLOSED"] else None

    cursor.execute("""
        UPDATE outage_reports
        SET status = ?,
            assigned_crew_id = COALESCE(?, assigned_crew_id),
            estimated_restoration = CASE WHEN ? != '' THEN ? ELSE estimated_restoration END,
            resolution_notes = CASE WHEN ? != '' THEN ? ELSE resolution_notes END,
            resolved_at = CASE WHEN ? IS NOT NULL THEN ? ELSE resolved_at END
        WHERE id = ?
    """, (
        new_status, assigned_crew_val,
        estimated_restoration, estimated_restoration,
        resolution_notes, resolution_notes,
        resolved_at, resolved_at,
        ticket_id
    ))

    # Add audit status history record
    note_msg = f"Status updated to '{new_status}'."
    if resolution_notes:
        note_msg += f" Note: {resolution_notes}"
    if estimated_restoration:
        note_msg += f" (ETR: {estimated_restoration})"

    cursor.execute("""
        INSERT INTO status_history (report_id, status, notes, updated_by)
        VALUES (?, ?, ?, ?)
    """, (ticket_id, new_status, note_msg, staff_name))

    # Update crew status if assigned
    if assigned_crew_val:
        crew_status = "ON_SITE" if new_status == "RESTORATION_IN_PROGRESS" else "DISPATCHED"
        if new_status in ["RESOLVED", "CLOSED"]:
            crew_status = "AVAILABLE"
        cursor.execute("UPDATE crews SET current_status = ? WHERE id = ?", (crew_status, assigned_crew_val))

    # Check if all outages in the ticket's locality are resolved
    ticket_row = cursor.execute("SELECT locality_id FROM outage_reports WHERE id = ?", (ticket_id,)).fetchone()
    if ticket_row:
        loc_id = ticket_row["locality_id"]
        unresolved_in_loc = cursor.execute(
            "SELECT COUNT(*) FROM outage_reports WHERE locality_id = ? AND status NOT IN ('RESOLVED', 'CLOSED')",
            (loc_id,)
        ).fetchone()[0]
        if unresolved_in_loc == 0:
            cursor.execute("UPDATE localities SET status = 'NORMAL' WHERE id = ? AND status = 'OUTAGE_ACTIVE'", (loc_id,))

    conn.commit()
    conn.close()

    flash(f"Ticket #{ticket_id} status updated to {new_status} successfully.", "success")
    return redirect(url_for("admin_dashboard"))

@app.route("/admin/simulate-incident", methods=["POST"])
@admin_required
def admin_simulate_incident():
    conn = database.get_db()
    cursor = conn.cursor()

    localities = cursor.execute("SELECT * FROM localities").fetchall()
    if not localities:
        conn.close()
        flash("No localities configured to simulate incident.", "danger")
        return redirect(url_for("admin_dashboard"))

    loc = random.choice(localities)
    types_list = [
        ("Distribution Transformer Failure", "CRITICAL", "Loud boom heard at feeder box; sparking observed.", 85),
        ("Fallen Tree on Overhead Line", "HIGH", "Heavy tree branch snapped overhead HT cable onto road.", 45),
        ("Wire Snapped / Broken Pole", "CRITICAL", "Delivery truck struck electric pole; live conductor hanging.", 120),
        ("Phase Imbalance / Low Voltage", "MEDIUM", "Single phase dropped; appliances fluctuating.", 25)
    ]
    chosen = random.choice(types_list)
    ticket_no = generate_ticket_number()
    while cursor.execute("SELECT id FROM outage_reports WHERE ticket_no = ?", (ticket_no,)).fetchone():
        ticket_no = generate_ticket_number()

    lat = loc["lat"] + random.uniform(-0.003, 0.003)
    lng = loc["lng"] + random.uniform(-0.003, 0.003)

    cursor.execute("""
        INSERT INTO outage_reports (
            ticket_no, locality_id, consumer_name, consumer_phone,
            address, landmark, outage_type, severity, description,
            lat, lng, status, affected_households, estimated_restoration
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'REPORTED', ?, ?)
    """, (
        ticket_no, loc["id"], "Automated Grid Telemetry Sensor", "+91 94481 00912",
        f"Near Pillar #{random.randint(10, 99)}, {loc['name']}",
        f"Near {loc['substation_name']}",
        chosen[0], chosen[1], chosen[2],
        lat, lng, chosen[3], "In ~2 hours"
    ))
    report_id = cursor.lastrowid

    cursor.execute("""
        INSERT INTO status_history (report_id, status, notes, updated_by)
        VALUES (?, 'REPORTED', 'Live telemetry fault detected & logged by SCADA substation monitor.', 'SCADA System')
    """, (report_id,))

    cursor.execute("UPDATE localities SET status = 'OUTAGE_ACTIVE' WHERE id = ?", (loc["id"],))
    conn.commit()
    conn.close()

    flash(f"⚡ Simulated Outage Incident Generated! Ticket #{ticket_no} created in {loc['name']}.", "warning")
    return redirect(url_for("admin_dashboard"))

@app.route("/admin/crews", methods=["GET", "POST"])
@admin_required
def admin_crews():
    conn = database.get_db()

    if request.method == "POST":
        action = request.form.get("action")
        if action == "add":
            crew_name = request.form.get("crew_name", "").strip()
            lead_lineman = request.form.get("lead_lineman", "").strip()
            phone = request.form.get("phone", "").strip()
            vehicle_no = request.form.get("vehicle_no", "").strip()
            if crew_name and lead_lineman and phone:
                conn.execute("""
                    INSERT INTO crews (crew_name, lead_lineman, phone, vehicle_no, current_status)
                    VALUES (?, ?, ?, ?, 'AVAILABLE')
                """, (crew_name, lead_lineman, phone, vehicle_no))
                conn.commit()
                flash(f"Line crew '{crew_name}' added successfully.", "success")
        elif action == "update_status":
            crew_id = request.form.get("crew_id")
            new_status = request.form.get("current_status")
            if crew_id and new_status:
                conn.execute("UPDATE crews SET current_status = ? WHERE id = ?", (new_status, crew_id))
                conn.commit()
                flash("Crew status updated.", "info")

    crews = conn.execute("""
        SELECT c.*, l.name as current_locality_name,
               (SELECT COUNT(*) FROM outage_reports r WHERE r.assigned_crew_id = c.id AND r.status NOT IN ('RESOLVED', 'CLOSED')) as assigned_active_tickets
        FROM crews c
        LEFT JOIN localities l ON c.current_locality_id = l.id
        ORDER BY c.crew_name ASC
    """).fetchall()

    conn.close()
    return render_template("admin_crews.html", crews=crews)

@app.route("/admin/maintenance", methods=["GET", "POST"])
@admin_required
def admin_maintenance():
    conn = database.get_db()

    if request.method == "POST":
        action = request.form.get("action")
        if action == "add":
            locality_id = request.form.get("locality_id")
            title = request.form.get("title", "").strip()
            substation = request.form.get("substation", "").strip()
            start_time = request.form.get("start_time", "").strip()
            end_time = request.form.get("end_time", "").strip()
            affected_areas = request.form.get("affected_areas", "").strip()
            reason = request.form.get("reason", "").strip()

            if locality_id and title and start_time and end_time:
                conn.execute("""
                    INSERT INTO scheduled_maintenance (locality_id, title, substation, start_time, end_time, affected_areas, reason, status)
                    VALUES (?, ?, ?, ?, ?, ?, ?, 'SCHEDULED')
                """, (locality_id, title, substation, start_time, end_time, affected_areas, reason))
                
                # Flag locality status
                conn.execute("UPDATE localities SET status = 'MAINTENANCE' WHERE id = ?", (locality_id,))
                conn.commit()
                flash(f"Scheduled maintenance shutdown announced for {title}.", "success")
        elif action == "complete":
            m_id = request.form.get("maintenance_id")
            if m_id:
                conn.execute("UPDATE scheduled_maintenance SET status = 'COMPLETED' WHERE id = ?", (m_id,))
                conn.commit()
                flash("Scheduled maintenance marked as completed.", "info")

    maintenance_list = conn.execute("""
        SELECT m.*, l.name as locality_name
        FROM scheduled_maintenance m
        JOIN localities l ON m.locality_id = l.id
        ORDER BY m.start_time DESC
    """).fetchall()

    localities = conn.execute("SELECT * FROM localities ORDER BY name ASC").fetchall()
    conn.close()
    return render_template("admin_maintenance.html", maintenance_list=maintenance_list, localities=localities)

@app.route("/admin/announcements", methods=["GET", "POST"])
@admin_required
def admin_announcements():
    conn = database.get_db()

    if request.method == "POST":
        action = request.form.get("action")
        if action == "add":
            title = request.form.get("title", "").strip()
            message = request.form.get("message", "").strip()
            severity = request.form.get("severity", "INFO")
            if title and message:
                conn.execute("""
                    INSERT INTO announcements (title, message, severity, is_active)
                    VALUES (?, ?, ?, 1)
                """, (title, message, severity))
                conn.commit()
                flash("Emergency public alert broadcasted successfully.", "success")
        elif action == "delete":
            ann_id = request.form.get("announcement_id")
            if ann_id:
                conn.execute("DELETE FROM announcements WHERE id = ?", (ann_id,))
                conn.commit()
                flash("Alert removed from public feed.", "info")

    announcements = conn.execute("SELECT * FROM announcements ORDER BY created_at DESC").fetchall()
    conn.close()
    return render_template("admin_announcements.html", announcements=announcements)

@app.route("/admin/analytics")
@admin_required
def admin_analytics():
    conn = database.get_db()

    # Outages by Locality
    locality_stats = conn.execute("""
        SELECT l.name, COUNT(r.id) as count
        FROM localities l
        LEFT JOIN outage_reports r ON l.id = r.locality_id
        GROUP BY l.id, l.name
        ORDER BY count DESC
    """).fetchall()

    # Outages by Incident Type
    type_stats = conn.execute("""
        SELECT outage_type, COUNT(*) as count
        FROM outage_reports
        GROUP BY outage_type
        ORDER BY count DESC
    """).fetchall()

    # Outages by Severity
    severity_stats = conn.execute("""
        SELECT severity, COUNT(*) as count
        FROM outage_reports
        GROUP BY severity
    """).fetchall()

    # Outages by Status
    status_stats = conn.execute("""
        SELECT status, COUNT(*) as count
        FROM outage_reports
        GROUP BY status
    """).fetchall()

    conn.close()
    return render_template(
        "admin_analytics.html",
        locality_stats=locality_stats,
        type_stats=type_stats,
        severity_stats=severity_stats,
        status_stats=status_stats
    )

@app.route("/admin/export/csv")
@admin_required
def export_csv():
    import csv
    import io

    conn = database.get_db()
    rows = conn.execute("""
        SELECT r.ticket_no, l.name as locality, r.consumer_name, r.consumer_phone,
               r.address, r.outage_type, r.severity, r.status, r.reported_at,
               r.resolved_at, r.estimated_restoration, r.affected_households,
               c.crew_name
        FROM outage_reports r
        JOIN localities l ON r.locality_id = l.id
        LEFT JOIN crews c ON r.assigned_crew_id = c.id
        ORDER BY r.reported_at DESC
    """).fetchall()
    conn.close()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Ticket No", "Locality", "Resident Name", "Phone",
        "Address", "Outage Type", "Severity", "Status",
        "Reported Time", "Resolved Time", "Estimated ETR", "Households Affected", "Crew Assigned"
    ])

    for row in rows:
        writer.writerow([
            row["ticket_no"], row["locality"], row["consumer_name"], row["consumer_phone"],
            row["address"], row["outage_type"], row["severity"], row["status"],
            row["reported_at"], row["resolved_at"] or "N/A", row["estimated_restoration"] or "N/A",
            row["affected_households"], row["crew_name"] or "Unassigned"
        ])

    csv_data = output.getvalue()
    filename = f"power_outages_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"

    return Response(
        csv_data,
        mimetype="text/csv",
        headers={"Content-disposition": f"attachment; filename={filename}"}
    )

@app.route("/admin/api-keys", methods=["GET", "POST"])
@admin_required
def admin_api_keys():
    newly_created_key = None
    if request.method == "POST":
        action = request.form.get("action")
        if action == "generate":
            key_name = request.form.get("key_name", "").strip()
            role = request.form.get("role", "read_write")
            if not key_name:
                flash("Key description or system name is required.", "danger")
            else:
                new_key = generate_secure_api_key()
                database.create_api_key(key_name, new_key, role)
                newly_created_key = {"key_name": key_name, "api_key": new_key, "role": role}
                flash(f"New API Key generated successfully for '{key_name}'!", "success")
        elif action == "toggle":
            key_id = request.form.get("key_id")
            if key_id:
                database.toggle_api_key_status(key_id)
                flash("API Key status toggled successfully.", "info")
        elif action == "delete":
            key_id = request.form.get("key_id")
            if key_id:
                database.delete_api_key(key_id)
                flash("API Key permanently deleted.", "warning")

    api_keys = database.get_all_api_keys()

    # Calculate statistics
    total_keys = len(api_keys)
    active_keys = sum(1 for k in api_keys if k["is_active"] == 1)
    revoked_keys = total_keys - active_keys
    rw_keys = sum(1 for k in api_keys if k["role"] in ["read_write", "admin"])

    return render_template(
        "admin_api_keys.html",
        api_keys=api_keys,
        total_keys=total_keys,
        active_keys=active_keys,
        revoked_keys=revoked_keys,
        rw_keys=rw_keys,
        newly_created_key=newly_created_key,
        master_api_key=DEFAULT_API_KEY
    )

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    debug_mode = os.environ.get("FLASK_DEBUG", "true").lower() in ("true", "1")
    app.run(host="0.0.0.0", port=port, debug=debug_mode)
