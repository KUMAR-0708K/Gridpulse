# ⚡ GridPulse - Locality Power Outage Reporting & Tracking Portal

An end-to-end municipal power outage reporting, live GIS tracking, and utility board dispatcher management platform designed for locality residents and local electricity boards.

---

## 🌟 Key Features

### 👤 1. Resident / Citizen Portal
- **Interactive Live Outage Map:**
  - Real-time GIS map using **Leaflet.js** with color-coded pins for incident severity (Critical, High, Medium, Restored).
  - Filter markers by status: *All Outages*, *Critical Hazards*, *Under Repair*, *Restored*.
  - Dynamic map tiles that adapt automatically to Light, Dark (OLED), or Emergency High-Contrast mode.
  - Click on any marker to inspect fault details, affected households count, assigned line crew, and estimated time of restoration (ETR).
- **Theme Modes (Light / Dark OLED / Emergency High-Contrast):**
  - Instant theme switcher in top navbar and floating quick dial.
  - High-contrast emergency theme designed specifically for blackouts and low-visibility conditions.
- **Outage Reporting with Pin Drop, Photo Preview & Severity Cards:**
  - Fast reporting with locality/ward auto-detection and feeder substation mapping.
  - Drop a pin directly on an interactive map or click *"Use My Current Location"* to capture exact GPS coordinates for linemen vans.
  - Client-side photo upload preview with file size verification and quick remove.
  - Interactive clickable severity hazard selector cards.
  - Generates instant unique ticket numbers (e.g. `PWR-2026-1001`).
- **Live Ticket Tracker with Real-Time ETR Countdown & 5-Stage Stepper:**
  - Search by Ticket Number or registered Mobile Phone Number.
  - Interactive visual progress tracker:
    1. **REPORTED** &rarr; 2. **INVESTIGATING** &rarr; 3. **CREW DISPATCHED** &rarr; 4. **RESTORATION IN PROGRESS** &rarr; 5. **POWER RESTORED**
  - Real-time live countdown timer widget ticking down seconds until target restoration time.
  - Web Audio API pleasant chime feedback on actions and updates.
  - *"Also Affected"* community upvote counter (+1) so neighbors can affirm outages and boost priority without duplicate tickets.
- **Locality Health & Maintenance Calendar:**
  - Grid status across all wards: *Normal*, *Degraded*, *Outage Active*, *Maintenance*.
  - View feeder substations and assistant engineer phone contacts.
  - Subscribe to instant SMS/Email notifications for your ward.
- **Electrical Safety & Floating Emergency Dial:**
  - 35-foot rule for downed wires, electrical fire protocols, generator backfeeding warnings, and surge protection.
  - Floating bottom-right speed-dial bar with one-touch dialing for 24x7 control room (`1912`), quick reporting, and theme toggling.

---

### 🏢 2. Utility Board & Dispatcher Command Center
- **Control Room Operations Dashboard:**
  - Real-time KPIs: Active Fault Tickets, Critical Hazards, Total Impacted Consumers, Restored Today.
  - One-Click Outage Simulator: Instantly trigger simulated SCADA telemetry grid faults in any ward for demonstration & stress testing.
  - Filterable incident desk: Filter by status, locality, severity, or search text.
  - Status management modal: Transition tickets through lifecycle, assign field crews, set ETR, and record lineman repair notes.
- **Lineman Fleet & Crew Dispatch:**
  - Track response units (*Available*, *Dispatched*, *On-Site*, *Off-Duty*).
  - Lead lineman details, phone numbers, vehicle registrations, and active ticket workloads.
  - Add and register new emergency squads.
- **Planned Maintenance & Shutdown Scheduler:**
  - Schedule preventative power cuts with start/end time windows, affected streets, and reasons.
  - Automatically flags locality status and alerts residents in advance.
- **Emergency Public Broadcasts:**
  - Broadcast urgent alerts (e.g., severe weather or tree trimming) that instantly display on the top ticker banner of every citizen page.
- **Grid Analytics & Reporting:**
  - Interactive **Chart.js** visualizations:
    - Outage incident frequency by locality.
    - Hazard severity distribution.
    - Failure root causes breakdown.
    - Ticket lifecycle resolution funnel.
  - One-click CSV export of all outage logs (`/admin/export/csv`).

---

## 🛠️ Technology Stack

| Layer | Technologies |
|---|---|
| **Backend** | Python 3, Flask, Werkzeug |
| **Database** | SQLite3 (Persistent with Foreign Keys & Cascading) |
| **Frontend** | HTML5, Bootstrap 5, Bootstrap Icons, Leaflet.js (GIS Mapping), Chart.js |
| **Data Formats**| RESTful JSON APIs, Geo-Coordinates, CSV Reports |

---

## 🚀 Quick Start Guide

### 1. Prerequisites
- Python 3.10+ installed.

### 2. Installation
Open PowerShell or Command Prompt in this project directory:
```bash
python -m pip install -r requirements.txt
```

### 3. Start Application
```bash
python app.py
```
*Or double click `run.bat` / run `.\run.ps1` on Windows.*

The web application will be live at:
- **Resident Portal:** [http://127.0.0.1:5000/](http://127.0.0.1:5000/)
- **Utility Board Dispatcher Desk:** [http://127.0.0.1:5000/admin/login](http://127.0.0.1:5000/admin/login)

---

## 🔑 Demo Staff Login Credentials

| Username | Password | Assigned Role |
|---|---|---|
| `admin` | `gridadmin2026` | Control Room Engineer |
| `dispatcher` | `gridadmin2026` | Senior Grid Dispatcher |

---

## 🧪 Testing

Run the automated test suite covering all routes, database operations, status updates, API key authentication, and REST APIs:
```bash
python test_app.py
```
All 17 unit & integration test cases will run and report execution status.

---

## 🔑 API Key Authentication & External Integrations

GridPulse REST APIs are protected by API key authentication to support secure telemetry ingestion from substation SCADA feeds, smart meter IoT gateways, linemen mobile apps, and municipal civic dashboards.

### Supported Authentication Methods

You can supply the API key using any of the following methods:

1. **HTTP Header (Recommended):**
   ```http
   X-API-Key: gp_live_scada_demo_key_2026
   ```
2. **Bearer Token:**
   ```http
   Authorization: Bearer gp_live_scada_demo_key_2026
   ```
3. **Query Parameter:**
   ```http
   GET /api/outages?api_key=gp_live_scada_demo_key_2026
   ```

### Pre-Seeded Evaluation API Keys

| Key Token | Role | Target System |
|---|---|---|
| `gp_live_scada_demo_key_2026` | `read_write` | Substation SCADA & Telemetry Ingestion (Master Key) |
| `gp_live_crew_mobile_key_2026` | `read_write` | Field Linemen Mobile Dispatch & Response App |
| `gp_live_public_read_key_2026` | `read_only` | Municipal Open Data & Civic Dashboards |

New API keys with custom roles (`read_only` or `read_write`) can be generated, revoked, and managed in the **Utility Command Center** under `/admin/api-keys`.

### Example cURL Commands

**Verify API Key Authentication:**
```bash
curl -X GET http://127.0.0.1:5000/api/auth/verify \
  -H "X-API-Key: gp_live_scada_demo_key_2026"
```

**Query Active Grid Outages:**
```bash
curl -X GET "http://127.0.0.1:5000/api/outages?status=active" \
  -H "X-API-Key: gp_live_scada_demo_key_2026"
```

**Ingest Real-Time SCADA Grid Fault Telemetry:**
```bash
curl -X POST http://127.0.0.1:5000/api/outages \
  -H "X-API-Key: gp_live_scada_demo_key_2026" \
  -H "Content-Type: application/json" \
  -d '{
    "locality_id": 1,
    "consumer_name": "SCADA Substation Feeder 4A",
    "consumer_phone": "+91 94481 00912",
    "address": "12th Cross, Sector 2",
    "landmark": "Near Substation Feeder Busbar",
    "outage_type": "Distribution Transformer Failure",
    "severity": "CRITICAL",
    "description": "Overcurrent breaker trip recorded by telemetry sensor.",
    "affected_households": 120
  }'
```

---

## 📡 REST API Reference

| Endpoint | Method | Required Role | Description |
|---|---|---|---|
| `/api/auth/verify` | `GET` | `read_only` | Validates API key and returns client identity and permissions. |
| `/api/outages` | `GET` | `read_only` | Returns JSON list of outages. Filter by `?status=active` and `?locality_id=X`. |
| `/api/outages` | `POST` | `read_write` | Ingests automated grid faults from SCADA or smart meters and generates ticket. |
| `/api/outages/<ticket_no>` | `GET` | `read_only` | Retrieves ticket lifecycle, assigned crew, and audit trail. |
| `/api/localities` | `GET` | `read_only` | Returns list of monitored wards, total connections, and active outage counts. |
| `/api/upvote/<ticket_no>` | `POST` | Public / Key | Increments the "Also Affected" community counter for an outage ticket. |
| `/admin/api-keys` | `GET/POST` | Staff Session | Admin console to generate, toggle, revoke, and delete API keys. |
| `/admin/export/csv` | `GET` | Staff Session | Exports complete historical outage reports in spreadsheet format. |

---

## 📂 Project Directory Structure

```
├── .env                        # Local environment configuration & master API key
├── .env.example                # Template environment settings
├── app.py                      # Core Flask application, auth decorator & routing
├── database.py                 # SQLite schema, migrations, API key helpers & seed data
├── test_app.py                 # Automated unit and integration test suite (17 tests)
├── requirements.txt            # Python dependencies
├── run.bat                     # Windows batch launcher
├── run.ps1                     # PowerShell launcher
├── README.md                   # System documentation
├── static/
│   ├── css/
│   │   └── style.css           # Styling, status badges & responsive layout
│   ├── js/
│   │   ├── main.js             # Alert auto-dismiss, Web Audio & API upvote
│   │   └── map.js              # Leaflet GIS interactive map logic with API key
│   └── uploads/                # Uploaded fault evidence photos
└── templates/
    ├── base.html               # Master layout with navbar, API key meta & alert ticker
    ├── index.html              # Resident homepage & live GIS map
    ├── report.html             # Outage report form with pin-drop map & photo upload
    ├── track.html              # Ticket tracker with 5-stage progress bar
    ├── localities.html         # Locality health board & SMS alerts subscription
    ├── safety.html             # Electrical safety guide & emergency helplines
    ├── admin_login.html        # Utility board authentication page
    ├── admin_dashboard.html    # Command center dispatch desk & ticket manager
    ├── admin_api_keys.html     # API keys & external integrations management
    ├── admin_crews.html        # Line crew & response fleet manager
    ├── admin_maintenance.html  # Planned outage scheduler
    ├── admin_announcements.html# Emergency public broadcasts manager
    └── admin_analytics.html    # Chart.js grid reliability telemetry
```
