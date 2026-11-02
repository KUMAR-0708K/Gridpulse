import unittest
import os
import tempfile
import app
import database

class PowerOutageAppTestCase(unittest.TestCase):
    def setUp(self):
        app.app.config["TESTING"] = True
        app.app.config["WTF_CSRF_ENABLED"] = False
        self.client = app.app.test_client()
        # Initialize and seed database
        database.init_db()
        database.seed_db()

    def test_homepage_loads(self):
        """Test home page loads successfully with status code 200"""
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"GridPulse", response.data)
        self.assertIn(b"Live Outage Map", response.data)

    def test_report_page_get(self):
        """Test report outage page loads with form and localities"""
        response = self.client.get("/report")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Report a Power Outage", response.data)
        self.assertIn(b"Ward / Locality", response.data)

    def test_report_submission_and_tracking(self):
        """Test reporting an outage creates ticket and redirects to tracking"""
        post_data = {
            "locality_id": 1,
            "consumer_name": "Test Resident",
            "consumer_phone": "+91 99999 88888",
            "consumer_email": "test@locality.org",
            "account_or_meter_no": "MTR-112233",
            "address": "10th Cross, Test Ward",
            "landmark": "Near Community Hall",
            "outage_type": "Total Blackout",
            "severity": "CRITICAL",
            "description": "Entire street is dark and loud spark was heard from pole transformer.",
            "affected_households": 20,
            "lat": "12.9780",
            "lng": "77.6400"
        }
        response = self.client.post("/report", data=post_data, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"PWR-2026-", response.data)
        self.assertIn(b"Test Resident", response.data)

    def test_tracking_page_existing_ticket(self):
        """Test tracking existing seeded ticket PWR-2026-1001"""
        response = self.client.get("/track?ticket=PWR-2026-1001")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"PWR-2026-1001", response.data)
        self.assertIn(b"Rajesh Nair", response.data)
        self.assertIn(b"Restoration Lifecycle Progress", response.data)

    def test_api_outages_unauthorized(self):
        """Test GET /api/outages without API key returns 401 Unauthorized"""
        response = self.client.get("/api/outages")
        self.assertEqual(response.status_code, 401)
        json_data = response.get_json()
        self.assertFalse(json_data["success"])
        self.assertEqual(json_data["error"], "Unauthorized")

    def test_api_outages_authorized_header(self):
        """Test GET /api/outages with valid X-API-Key header returns 200 OK"""
        response = self.client.get("/api/outages", headers={"X-API-Key": "gp_live_scada_demo_key_2026"})
        self.assertEqual(response.status_code, 200)
        json_data = response.get_json()
        self.assertTrue(json_data["success"])
        self.assertGreater(json_data["count"], 0)

    def test_api_outages_authorized_query_param(self):
        """Test GET /api/outages with ?api_key= query parameter returns 200 OK"""
        response = self.client.get("/api/outages?api_key=gp_live_scada_demo_key_2026")
        self.assertEqual(response.status_code, 200)
        json_data = response.get_json()
        self.assertTrue(json_data["success"])

    def test_api_outages_authorized_bearer(self):
        """Test GET /api/outages with Bearer token authorization header returns 200 OK"""
        response = self.client.get("/api/outages", headers={"Authorization": "Bearer gp_live_scada_demo_key_2026"})
        self.assertEqual(response.status_code, 200)
        json_data = response.get_json()
        self.assertTrue(json_data["success"])

    def test_api_outages_invalid_key(self):
        """Test GET /api/outages with invalid API key returns 401 Unauthorized"""
        response = self.client.get("/api/outages", headers={"X-API-Key": "invalid_random_key_12345"})
        self.assertEqual(response.status_code, 401)
        json_data = response.get_json()
        self.assertFalse(json_data["success"])

    def test_api_auth_verify(self):
        """Test GET /api/auth/verify returns authentication metadata"""
        response = self.client.get("/api/auth/verify", headers={"X-API-Key": "gp_live_scada_demo_key_2026"})
        self.assertEqual(response.status_code, 200)
        json_data = response.get_json()
        self.assertTrue(json_data["success"])
        self.assertTrue(json_data["authenticated"])
        self.assertEqual(json_data["role"], "read_write")

    def test_api_create_outage_iot(self):
        """Test POST /api/outages creates new outage via SCADA/IoT API key"""
        payload = {
            "locality_id": 1,
            "consumer_name": "SCADA Feeder Telemetry",
            "outage_type": "Distribution Transformer Failure",
            "severity": "CRITICAL",
            "description": "Auto telemetry spike breaker trip.",
            "affected_households": 80
        }
        response = self.client.post(
            "/api/outages",
            headers={"X-API-Key": "gp_live_scada_demo_key_2026"},
            json=payload
        )
        self.assertEqual(response.status_code, 201)
        json_data = response.get_json()
        self.assertTrue(json_data["success"])
        self.assertTrue(json_data["ticket_no"].startswith("PWR-"))
        self.assertEqual(json_data["status"], "REPORTED")

    def test_api_create_outage_read_only_forbidden(self):
        """Test POST /api/outages with read_only API key returns 403 Forbidden"""
        payload = {
            "locality_id": 1,
            "outage_type": "Total Blackout"
        }
        response = self.client.post(
            "/api/outages",
            headers={"X-API-Key": "gp_live_public_read_key_2026"},
            json=payload
        )
        self.assertEqual(response.status_code, 403)
        json_data = response.get_json()
        self.assertFalse(json_data["success"])

    def test_api_track_single_ticket(self):
        """Test GET /api/outages/<ticket_no> returns ticket details and history"""
        response = self.client.get(
            "/api/outages/PWR-2026-1001",
            headers={"X-API-Key": "gp_live_scada_demo_key_2026"}
        )
        self.assertEqual(response.status_code, 200)
        json_data = response.get_json()
        self.assertTrue(json_data["success"])
        self.assertEqual(json_data["data"]["ticket_no"], "PWR-2026-1001")

    def test_api_upvote(self):
        """Test POST /api/upvote increments upvote count"""
        response = self.client.post("/api/upvote/PWR-2026-1001")
        self.assertEqual(response.status_code, 200)
        json_data = response.get_json()
        self.assertTrue(json_data["success"])
        self.assertGreaterEqual(json_data["upvotes"], 13)

    def test_localities_page(self):
        """Test localities page loads"""
        response = self.client.get("/localities")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Locality Grid Health", response.data)

    def test_safety_page(self):
        """Test safety page loads"""
        response = self.client.get("/safety")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Electrical Hazard Guidelines", response.data)
        self.assertIn(b"1912", response.data)

    def test_admin_auth_and_dashboard(self):
        """Test admin login and access to dashboard"""
        # Unauthorized access redirects to login
        res = self.client.get("/admin", follow_redirects=False)
        self.assertEqual(res.status_code, 302)

        # Login with valid credentials
        login_res = self.client.post("/admin/login", data={
            "username": "admin",
            "password": "gridadmin2026"
        }, follow_redirects=True)
        self.assertEqual(login_res.status_code, 200)
        self.assertIn(b"Grid Operations Command Center", login_res.data)

        # Access analytics
        analytics_res = self.client.get("/admin/analytics")
        self.assertEqual(analytics_res.status_code, 200)
        self.assertIn(b"Grid Analytics", analytics_res.data)

        # Access API Keys page
        api_keys_res = self.client.get("/admin/api-keys")
        self.assertEqual(api_keys_res.status_code, 200)
        self.assertIn(b"API Keys & Integrations", api_keys_res.data)

        # Generate new API key via admin
        gen_res = self.client.post("/admin/api-keys", data={
            "action": "generate",
            "key_name": "Test Integration Key",
            "role": "read_write"
        }, follow_redirects=True)
        self.assertEqual(gen_res.status_code, 200)
        self.assertIn(b"Test Integration Key", gen_res.data)

        # Test incident simulator
        sim_res = self.client.post("/admin/simulate-incident", follow_redirects=True)
        self.assertEqual(sim_res.status_code, 200)
        self.assertIn(b"Simulated Outage Incident Generated", sim_res.data)

if __name__ == "__main__":
    unittest.main()
