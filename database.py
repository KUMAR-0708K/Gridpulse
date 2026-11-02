import sqlite3
import os
import random
from datetime import datetime, timedelta

DB_FILE = os.path.join(os.path.dirname(__file__), "power_outage.db")

def get_db():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn

def init_db():
    conn = get_db()
    cursor = conn.cursor()

    cursor.executescript("""
    CREATE TABLE IF NOT EXISTS localities (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE,
        code TEXT NOT NULL UNIQUE,
        substation_name TEXT NOT NULL,
        total_connections INTEGER DEFAULT 1200,
        status TEXT DEFAULT 'NORMAL', -- NORMAL, DEGRADED, OUTAGE_ACTIVE, MAINTENANCE
        lat REAL NOT NULL,
        lng REAL NOT NULL,
        contact_officer TEXT,
        officer_phone TEXT
    );

    CREATE TABLE IF NOT EXISTS crews (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        crew_name TEXT NOT NULL,
        lead_lineman TEXT NOT NULL,
        phone TEXT NOT NULL,
        vehicle_no TEXT,
        current_status TEXT DEFAULT 'AVAILABLE', -- AVAILABLE, DISPATCHED, ON_SITE, OFF_DUTY
        current_locality_id INTEGER,
        FOREIGN KEY(current_locality_id) REFERENCES localities(id) ON DELETE SET NULL
    );

    CREATE TABLE IF NOT EXISTS outage_reports (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ticket_no TEXT UNIQUE NOT NULL,
        locality_id INTEGER NOT NULL,
        consumer_name TEXT NOT NULL,
        consumer_phone TEXT NOT NULL,
        consumer_email TEXT,
        account_or_meter_no TEXT,
        address TEXT NOT NULL,
        landmark TEXT,
        outage_type TEXT NOT NULL,
        severity TEXT DEFAULT 'MEDIUM', -- CRITICAL, HIGH, MEDIUM, LOW
        description TEXT,
        lat REAL,
        lng REAL,
        photo_filename TEXT,
        status TEXT DEFAULT 'REPORTED', -- REPORTED, INVESTIGATING, CREW_DISPATCHED, RESTORATION_IN_PROGRESS, RESOLVED, CLOSED
        reported_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        assigned_crew_id INTEGER,
        estimated_restoration TEXT,
        resolved_at TIMESTAMP,
        resolution_notes TEXT,
        affected_households INTEGER DEFAULT 1,
        upvotes INTEGER DEFAULT 1,
        FOREIGN KEY(locality_id) REFERENCES localities(id) ON DELETE CASCADE,
        FOREIGN KEY(assigned_crew_id) REFERENCES crews(id) ON DELETE SET NULL
    );

    CREATE TABLE IF NOT EXISTS status_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        report_id INTEGER NOT NULL,
        status TEXT NOT NULL,
        notes TEXT,
        updated_by TEXT DEFAULT 'System',
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(report_id) REFERENCES outage_reports(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS scheduled_maintenance (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        locality_id INTEGER NOT NULL,
        title TEXT NOT NULL,
        substation TEXT,
        start_time TEXT NOT NULL,
        end_time TEXT NOT NULL,
        affected_areas TEXT NOT NULL,
        reason TEXT NOT NULL,
        status TEXT DEFAULT 'SCHEDULED', -- SCHEDULED, IN_PROGRESS, COMPLETED, CANCELLED
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(locality_id) REFERENCES localities(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS announcements (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        message TEXT NOT NULL,
        severity TEXT DEFAULT 'INFO', -- INFO, WARNING, URGENT
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        is_active INTEGER DEFAULT 1
    );

    CREATE TABLE IF NOT EXISTS subscribers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        locality_id INTEGER NOT NULL,
        contact_type TEXT NOT NULL, -- SMS, EMAIL
        contact_value TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(locality_id) REFERENCES localities(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS api_keys (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        key_name TEXT NOT NULL,
        api_key TEXT UNIQUE NOT NULL,
        role TEXT DEFAULT 'read_write', -- 'read_only', 'read_write', 'admin'
        is_active INTEGER DEFAULT 1,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        last_used_at TIMESTAMP
    );
    """)

    conn.commit()
    conn.close()

    # Ensure default API keys exist
    seed_api_keys()

def seed_db():
    conn = get_db()
    cursor = conn.cursor()

    # Check if localities already populated
    cursor.execute("SELECT COUNT(*) FROM localities")
    if cursor.fetchone()[0] > 0:
        conn.close()
        return

    # Base coordinates: Centered around a lively municipality locality grid
    # E.g., Lat 12.9716, Lng 77.5946 (Metro hub style)
    localities_data = [
        ("Indira Nagar Sector 1-4", "IN-SEC", "Indira Nagar 66kV Substation", 3400, "OUTAGE_ACTIVE", 12.9784, 77.6408, "R. K. Sharma (AE)", "+91 98450 11201"),
        ("Koramangala 4th & 5th Block", "KOR-BLK", "Koramangala Main Substation", 4200, "DEGRADED", 12.9352, 77.6245, "Anita V. Rao (AEE)", "+91 98450 11202"),
        ("Whitefield Tech Corridor", "WTF-COR", "ITPL 220kV Receiving Station", 6500, "NORMAL", 12.9698, 77.7499, "Suresh Hegde (EE)", "+91 98450 11203"),
        ("Jayanagar 3rd & 4th East", "JYN-EST", "South Circle Substation", 2800, "NORMAL", 12.9308, 77.5838, "Pradeep Kumar (AE)", "+91 98450 11204"),
        ("Malleshwaram Central", "MLS-CTR", "North Hub 110kV Substation", 3100, "MAINTENANCE", 13.0031, 77.5643, "Manjunath Swamy (AEE)", "+91 98450 11205"),
        ("HSR Layout Sector 2 & 3", "HSR-SEC", "Agara Lake Feeder", 3900, "OUTAGE_ACTIVE", 12.9121, 77.6446, "Deepa Narayanan (AE)", "+91 98450 11206"),
        ("Hebbal Lakeview Ward", "HBL-W4", "Hebbal Outer Substation", 2500, "NORMAL", 13.0358, 77.5970, "Gopal Reddy (AE)", "+91 98450 11207"),
        ("Rajajinagar Industrial Area", "RJJ-IND", "Peenya Grid Interlink", 4800, "DEGRADED", 12.9982, 77.5530, "K. Narayanaswamy (EE)", "+91 98450 11208")
    ]

    cursor.executemany("""
    INSERT INTO localities (name, code, substation_name, total_connections, status, lat, lng, contact_officer, officer_phone)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, localities_data)

    # Insert Crews
    crews_data = [
        ("Rapid Response Alpha", "Sunil Gowda (Senior Lineman)", "+91 94481 22001", "KA-01-EA-4412", "DISPATCHED", 1),
        ("Emergency Delta Line Crew", "Mohammed Farooq (Supervisor)", "+91 94481 22002", "KA-01-EA-9981", "ON_SITE", 6),
        ("Transformer Maintenance Unit 3", "Venkatesh Babu (Technician)", "+91 94481 22003", "KA-04-TR-1209", "ON_SITE", 5),
        ("Feeder Patrol Crew Bravo", "Kishore Kumar (Lineman)", "+91 94481 22004", "KA-05-EA-3341", "AVAILABLE", None),
        ("Night Vigil Squad 1", "Arun Prakash (Assistant Lineman)", "+91 94481 22005", "KA-01-NV-7744", "AVAILABLE", None)
    ]

    cursor.executemany("""
    INSERT INTO crews (crew_name, lead_lineman, phone, vehicle_no, current_status, current_locality_id)
    VALUES (?, ?, ?, ?, ?, ?)
    """, crews_data)

    # Sample Outages
    now = datetime.now()
    t_1h_ago = (now - timedelta(hours=1, minutes=20)).strftime("%Y-%m-%d %H:%M:%S")
    t_2h_ago = (now - timedelta(hours=2, minutes=45)).strftime("%Y-%m-%d %H:%M:%S")
    t_30m_ago = (now - timedelta(minutes=35)).strftime("%Y-%m-%d %H:%M:%S")
    t_4h_ago = (now - timedelta(hours=4, minutes=10)).strftime("%Y-%m-%d %H:%M:%S")
    t_yesterday = (now - timedelta(days=1, hours=2)).strftime("%Y-%m-%d %H:%M:%S")

    reports_data = [
        (
            "PWR-2026-1001", 1, "Rajesh Nair", "+91 98451 12345", "rajesh.nair@example.com", "MTR-884129",
            "12th Main Road, 100 Feet Cross, Indira Nagar", "Near Metro Pillar 142",
            "Fallen Tree on Overhead Line", "CRITICAL",
            "A large banyan tree branch snapped due to sudden wind and snapped 11kV distribution line. Sparks were seen.",
            12.9790, 77.6415, None, "CREW_DISPATCHED", t_2h_ago, 1,
            (now + timedelta(minutes=45)).strftime("%I:%M %p"), None, None, 140, 12
        ),
        (
            "PWR-2026-1002", 6, "Pooja Hegde", "+91 98452 67890", "pooja.h@example.com", "MTR-339211",
            "27th Main, Sector 2, HSR Layout", "Behind NIFT Campus",
            "Distribution Transformer Failure", "HIGH",
            "Sudden loud noise from neighborhood pole transformer followed by complete darkness across 3 streets.",
            12.9135, 77.6455, None, "RESTORATION_IN_PROGRESS", t_1h_ago, 2,
            (now + timedelta(hours=1, minutes=15)).strftime("%I:%M %p"), None, None, 85, 18
        ),
        (
            "PWR-2026-1003", 2, "Kavita Sundaram", "+91 98453 99887", "kavita.s@example.com", "MTR-554102",
            "80 Feet Road, 4th Block, Koramangala", "Opposite Sony World Junction",
            "Phase Imbalance / Low Voltage", "MEDIUM",
            "Single phase power cut. Tube lights flickering dimly, refrigerator and AC not powering on.",
            12.9360, 77.6252, None, "INVESTIGATING", t_30m_ago, None,
            (now + timedelta(hours=2)).strftime("%I:%M %p"), None, None, 25, 6
        ),
        (
            "PWR-2026-1004", 8, "Vikas Jain", "+91 98454 22334", "vikas.jain@example.com", "MTR-998811",
            "Industrial Estate Phase 1, Rajajinagar", "Near Substation Gate 2",
            "Substation Feeder Tripping", "HIGH",
            "Industrial line tripped during heavy load switch. Industrial units on Standby DG generators.",
            12.9995, 77.5520, None, "INVESTIGATING", t_4h_ago, None,
            (now + timedelta(hours=1, minutes=30)).strftime("%I:%M %p"), None, None, 40, 9
        ),
        (
            "PWR-2026-0995", 4, "Chandrashekar B.", "+91 98455 44556", "chandra.b@example.com", "MTR-120034",
            "9th Cross, Jayanagar 3rd East", "Near Shalini Grounds",
            "Underground Cable Fault", "HIGH",
            "Underground cable puncture repaired after excavator damage. Power successfully restored.",
            12.9312, 77.5845, None, "RESOLVED", t_yesterday, 4,
            None, (now - timedelta(hours=18)).strftime("%Y-%m-%d %H:%M:%S"),
            "Cable jointing sleeve installed and tested with megger insulation test. Supply normalized.", 60, 8
        )
    ]

    for r in reports_data:
        cursor.execute("""
        INSERT INTO outage_reports (
            ticket_no, locality_id, consumer_name, consumer_phone, consumer_email, account_or_meter_no,
            address, landmark, outage_type, severity, description, lat, lng, photo_filename,
            status, reported_at, assigned_crew_id, estimated_restoration, resolved_at, resolution_notes,
            affected_households, upvotes
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, r)
        rep_id = cursor.lastrowid

        # Insert historical audit trails
        ticket_no = r[0]
        status = r[14]
        reported_at = r[15]

        cursor.execute("""
        INSERT INTO status_history (report_id, status, notes, updated_by, updated_at)
        VALUES (?, 'REPORTED', 'Outage reported by resident via web portal.', 'Resident', ?)
        """, (rep_id, reported_at))

        if status in ['INVESTIGATING', 'CREW_DISPATCHED', 'RESTORATION_IN_PROGRESS', 'RESOLVED']:
            cursor.execute("""
            INSERT INTO status_history (report_id, status, notes, updated_by, updated_at)
            VALUES (?, 'INVESTIGATING', 'Assigned to control room dispatcher. Feeder data verified.', 'Control Room Operator', ?)
            """, (rep_id, (datetime.strptime(reported_at, "%Y-%m-%d %H:%M:%S") + timedelta(minutes=15)).strftime("%Y-%m-%d %H:%M:%S")))

        if status in ['CREW_DISPATCHED', 'RESTORATION_IN_PROGRESS', 'RESOLVED']:
            cursor.execute("""
            INSERT INTO status_history (report_id, status, notes, updated_by, updated_at)
            VALUES (?, 'CREW_DISPATCHED', 'Lineman team dispatched to site with hydraulic ladder truck.', 'Dispatch Desk', ?)
            """, (rep_id, (datetime.strptime(reported_at, "%Y-%m-%d %H:%M:%S") + timedelta(minutes=30)).strftime("%Y-%m-%d %H:%M:%S")))

        if status in ['RESTORATION_IN_PROGRESS', 'RESOLVED']:
            cursor.execute("""
            INSERT INTO status_history (report_id, status, notes, updated_by, updated_at)
            VALUES (?, 'RESTORATION_IN_PROGRESS', 'Crew on site. Isolation tag placed, line replacement under way.', 'Lead Lineman', ?)
            """, (rep_id, (datetime.strptime(reported_at, "%Y-%m-%d %H:%M:%S") + timedelta(minutes=45)).strftime("%Y-%m-%d %H:%M:%S")))

        if status == 'RESOLVED':
            cursor.execute("""
            INSERT INTO status_history (report_id, status, notes, updated_by, updated_at)
            VALUES (?, 'RESOLVED', 'Field repair completed, line charged and voltage balanced across all 3 phases.', 'Assistant Executive Engineer', ?)
            """, (rep_id, r[19]))

    # Scheduled Maintenance
    maint_start = (now + timedelta(days=1, hours=4)).strftime("%Y-%m-%d 10:00 AM")
    maint_end = (now + timedelta(days=1, hours=8)).strftime("%Y-%m-%d 02:00 PM")
    cursor.execute("""
    INSERT INTO scheduled_maintenance (locality_id, title, substation, start_time, end_time, affected_areas, reason, status)
    VALUES (5, 'Annual Substation Overhaul & Tree Trimming', 'Malleshwaram 110kV Substation', ?, ?, '15th Cross to Margosa Road', 'Routine busbar cleaning and preventive vegetation pruning near HT lines', 'SCHEDULED')
    """, (maint_start, maint_end))

    # Announcements
    cursor.execute("""
    INSERT INTO announcements (title, message, severity, is_active)
    VALUES 
    ('Pre-Monsoon Line Clearing Drive Active', 'Utility maintenance crews are conducting tree trimming near HT conductors across Indira Nagar and Koramangala. Brief intermittent outages may occur.', 'INFO', 1),
    ('Emergency Severe Weather Advisory', 'Thunderstorm alert issued for eastern localities. Please stay at least 35 feet away from snapped or sagging overhead power lines. Report immediate hazards.', 'WARNING', 1)
    """)

    # Subscriptions mock
    cursor.execute("""
    INSERT INTO subscribers (locality_id, contact_type, contact_value)
    VALUES (1, 'SMS', '+91 98451 12345'), (6, 'EMAIL', 'pooja.h@example.com')
    """)

    conn.commit()
    conn.close()

def seed_api_keys():
    """Seed initial demo API keys if none exist."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM api_keys")
    if cursor.fetchone()[0] == 0:
        default_keys = [
            ("SCADA Feeder Telemetry System", "gp_live_scada_demo_key_2026", "read_write"),
            ("Rapid Response Lineman Mobile App", "gp_live_crew_mobile_key_2026", "read_write"),
            ("Municipal Public Dashboard & Civic Data", "gp_live_public_read_key_2026", "read_only"),
        ]
        cursor.executemany("""
            INSERT INTO api_keys (key_name, api_key, role, is_active)
            VALUES (?, ?, ?, 1)
        """, default_keys)
        conn.commit()
    conn.close()

def get_api_key(key_str):
    """Retrieve an API key record by key string."""
    conn = get_db()
    row = conn.execute("SELECT * FROM api_keys WHERE api_key = ?", (key_str,)).fetchone()
    conn.close()
    return row

def get_all_api_keys():
    """Retrieve all API keys ordered by creation date."""
    conn = get_db()
    rows = conn.execute("SELECT * FROM api_keys ORDER BY created_at DESC").fetchall()
    conn.close()
    return rows

def create_api_key(key_name, api_key, role="read_write"):
    """Create a new API key record."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO api_keys (key_name, api_key, role, is_active)
        VALUES (?, ?, ?, 1)
    """, (key_name, api_key, role))
    conn.commit()
    new_id = cursor.lastrowid
    conn.close()
    return new_id

def toggle_api_key_status(key_id):
    """Toggle between active and revoked status."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE api_keys
        SET is_active = CASE WHEN is_active = 1 THEN 0 ELSE 1 END
        WHERE id = ?
    """, (key_id,))
    conn.commit()
    conn.close()

def delete_api_key(key_id):
    """Permanently delete an API key."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM api_keys WHERE id = ?", (key_id,))
    conn.commit()
    conn.close()

def update_api_key_usage(api_key):
    """Update last used timestamp for an API key."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("UPDATE api_keys SET last_used_at = CURRENT_TIMESTAMP WHERE api_key = ?", (api_key,))
    conn.commit()
    conn.close()

if __name__ == "__main__":
    init_db()
    seed_db()
    print("Database initialized and seeded successfully.")
