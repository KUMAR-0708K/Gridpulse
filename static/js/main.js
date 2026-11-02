// ==========================================================================
// ⚡ GridPulse Main Client-Side JavaScript
// Theme Controller, Web Audio Feedback, Live ETR Countdown & Photo Preview
// ==========================================================================

// Global Theme Management
const ThemeManager = {
    currentTheme: "light",
    
    init() {
        const saved = localStorage.getItem("gridpulse_theme") || "light";
        this.setTheme(saved);
        
        // Setup listener for theme buttons
        const toggles = document.querySelectorAll("[data-theme-toggle]");
        toggles.forEach(btn => {
            btn.addEventListener("click", () => {
                const targetTheme = btn.getAttribute("data-theme-toggle");
                this.setTheme(targetTheme);
            });
        });

        // Speed-dial cycle button
        const cycleBtn = document.getElementById("btnThemeCycle");
        if (cycleBtn) {
            cycleBtn.addEventListener("click", () => {
                const themes = ["light", "dark", "emergency"];
                const nextIndex = (themes.indexOf(this.currentTheme) + 1) % themes.length;
                this.setTheme(themes[nextIndex]);
            });
        }
    },

    setTheme(themeName) {
        this.currentTheme = themeName;
        document.documentElement.setAttribute("data-theme", themeName);
        localStorage.setItem("gridpulse_theme", themeName);

        // Update active class on dropdown or buttons
        document.querySelectorAll("[data-theme-toggle]").forEach(btn => {
            if (btn.getAttribute("data-theme-toggle") === themeName) {
                btn.classList.add("active", "fw-bold");
            } else {
                btn.classList.remove("active", "fw-bold");
            }
        });

        // Notify map tile layer if Leaflet map exists
        if (window.onThemeChanged) {
            window.onThemeChanged(themeName);
        }
    }
};

// Web Audio API Synthesizer for tactile feedback
const SoundEffects = {
    ctx: null,
    muted: false,

    getAudioContext() {
        if (!this.ctx && (window.AudioContext || window.webkitAudioContext)) {
            const AudioCtx = window.AudioContext || window.webkitAudioContext;
            this.ctx = new AudioCtx();
        }
        return this.ctx;
    },

    playChime(type = "success") {
        if (this.muted) return;
        try {
            const ctx = this.getAudioContext();
            if (!ctx) return;
            if (ctx.state === "suspended") ctx.resume();

            const osc = ctx.createOscillator();
            const gain = ctx.createGain();
            osc.connect(gain);
            gain.connect(ctx.destination);

            const now = ctx.currentTime;

            if (type === "success") {
                // High dual pleasant chime
                osc.type = "sine";
                osc.frequency.setValueAtTime(587.33, now); // D5
                osc.frequency.exponentialRampToValueAtTime(880.00, now + 0.15); // A5
                gain.gain.setValueAtTime(0.12, now);
                gain.gain.exponentialRampToValueAtTime(0.001, now + 0.35);
                osc.start(now);
                osc.stop(now + 0.35);
            } else if (type === "alert") {
                // Warning notification tone
                osc.type = "triangle";
                osc.frequency.setValueAtTime(440, now);
                osc.frequency.setValueAtTime(330, now + 0.12);
                gain.gain.setValueAtTime(0.15, now);
                gain.gain.exponentialRampToValueAtTime(0.001, now + 0.3);
                osc.start(now);
                osc.stop(now + 0.3);
            }
        } catch (e) {
            // Audio context may be restricted before user gesture
        }
    }
};

// Live ETR (Estimated Time of Restoration) Countdown Clock
function initEtrCountdown() {
    const etrBox = document.querySelector(".etr-countdown-box");
    if (!etrBox) return;

    const rawTime = etrBox.getAttribute("data-etr-time");
    const digitsEl = etrBox.querySelector(".etr-digits");
    if (!digitsEl) return;

    // Parse or provide an active countdown
    // If format like "Today 16:30" or "In 2 hours", calculate a target epoch
    let targetEpoch = null;

    if (rawTime) {
        const timeMatch = rawTime.match(/(\d{1,2}):(\d{2})/);
        if (timeMatch) {
            const target = new Date();
            target.setHours(parseInt(timeMatch[1], 10));
            target.setMinutes(parseInt(timeMatch[2], 10));
            target.setSeconds(0);
            if (target < new Date()) {
                // If earlier today, add 2 hours for demonstration countdown
                target.setHours(target.getHours() + 2);
            }
            targetEpoch = target.getTime();
        }
    }

    if (!targetEpoch) {
        // Fallback: 1 hour 45 minutes from now
        targetEpoch = Date.now() + (105 * 60 * 1000);
    }

    function update() {
        const diff = targetEpoch - Date.now();
        if (diff <= 0) {
            digitsEl.innerHTML = `<span class="text-success"><i class="bi bi-check-circle me-1"></i> Crews Finalizing Restoration</span>`;
            return;
        }

        const hrs = Math.floor(diff / (1000 * 60 * 60));
        const mins = Math.floor((diff % (1000 * 60 * 60)) / (1000 * 60));
        const secs = Math.floor((diff % (1000 * 60)) / 1000);

        const pad = (n) => String(n).padStart(2, "0");
        digitsEl.textContent = `${pad(hrs)}h ${pad(mins)}m ${pad(secs)}s`;
    }

    update();
    setInterval(update, 1000);
}

// Client-side Photo Upload Preview
function initPhotoPreview() {
    const photoInput = document.getElementById("photo");
    const previewContainer = document.getElementById("uploadPreviewContainer");
    const previewImg = document.getElementById("uploadPreviewImg");
    const fileNameEl = document.getElementById("uploadFileName");
    const fileSizeEl = document.getElementById("uploadFileSize");
    const removeBtn = document.getElementById("uploadRemoveBtn");

    if (!photoInput || !previewContainer) return;

    photoInput.addEventListener("change", function () {
        const file = this.files[0];
        if (file) {
            const reader = new FileReader();
            reader.onload = function (e) {
                previewImg.src = e.target.result;
                fileNameEl.textContent = file.name;
                fileSizeEl.textContent = `(${(file.size / (1024 * 1024)).toFixed(2)} MB)`;
                previewContainer.style.display = "flex";
            };
            reader.readAsDataURL(file);
        }
    });

    if (removeBtn) {
        removeBtn.addEventListener("click", function () {
            photoInput.value = "";
            previewContainer.style.display = "none";
            previewImg.src = "";
        });
    }
}

// Interactive Severity Card Selector
function initSeverityCardSelector() {
    const radioCards = document.querySelectorAll(".severity-card-option");
    if (!radioCards.length) return;

    radioCards.forEach(card => {
        card.addEventListener("click", function () {
            const input = this.querySelector("input[type='radio']");
            if (input) {
                input.checked = true;
                radioCards.forEach(c => c.classList.remove("active"));
                this.classList.add("active");
                SoundEffects.playChime("alert");
            }
        });
    });
}

// Main Initialization
document.addEventListener("DOMContentLoaded", function () {
    // Initialize Theme
    ThemeManager.init();

    // Initialize Photo Preview
    initPhotoPreview();

    // Initialize ETR countdown
    initEtrCountdown();

    // Initialize Severity card selector
    initSeverityCardSelector();

    // Auto-dismiss alerts after 6 seconds
    const alerts = document.querySelectorAll(".alert-dismissible");
    alerts.forEach((alert) => {
        setTimeout(() => {
            const bsAlert = bootstrap.Alert.getOrCreateInstance(alert);
            if (bsAlert) bsAlert.close();
        }, 6000);
    });

    // Handle 'Also Affected' Upvote Button
    const upvoteButtons = document.querySelectorAll(".btn-upvote");
    upvoteButtons.forEach((btn) => {
        btn.addEventListener("click", function (e) {
            e.preventDefault();
            const ticketNo = this.getAttribute("data-ticket");
            if (!ticketNo || this.classList.contains("disabled")) return;

            const apiKey = window.GRIDPULSE_API_KEY || "gp_live_scada_demo_key_2026";
            fetch(`/api/upvote/${ticketNo}`, {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    "X-API-Key": apiKey
                }
            })
            .then((res) => res.json())
            .then((data) => {
                if (data.success) {
                    SoundEffects.playChime("success");
                    const countBadge = this.querySelector(".upvote-count");
                    if (countBadge) {
                        countBadge.textContent = data.upvotes;
                    }
                    this.classList.remove("btn-outline-secondary", "btn-outline-danger");
                    this.classList.add("btn-danger", "text-white", "disabled");
                    this.innerHTML = `<i class="bi bi-check-circle-fill me-1"></i> Reported (${data.upvotes})`;
                }
            })
            .catch((err) => console.error("Error upvoting ticket:", err));
        });
    });

    // Populate Status Update Modal in Admin Dashboard
    const statusModal = document.getElementById("updateStatusModal");
    if (statusModal) {
        statusModal.addEventListener("show.bs.modal", function (event) {
            const button = event.relatedTarget;
            const ticketId = button.getAttribute("data-ticket-id");
            const ticketNo = button.getAttribute("data-ticket-no");
            const currentStatus = button.getAttribute("data-status");
            const currentCrew = button.getAttribute("data-crew-id");
            const currentEtr = button.getAttribute("data-etr");

            const form = statusModal.querySelector("#updateTicketForm");
            form.action = `/admin/tickets/${ticketId}/update`;

            const ticketNoEl = statusModal.querySelector("#modalTicketNo");
            if (ticketNoEl) ticketNoEl.textContent = ticketNo;
            
            const statusSelect = statusModal.querySelector("#modalStatusSelect");
            if (statusSelect) statusSelect.value = currentStatus || "REPORTED";

            const crewSelect = statusModal.querySelector("#modalCrewSelect");
            if (crewSelect) crewSelect.value = currentCrew || "";

            const etrInput = statusModal.querySelector("#modalEtrInput");
            if (etrInput) etrInput.value = currentEtr || "";
        });
    }

    // Scroll to Top Speed-Dial
    const scrollTopBtn = document.getElementById("btnScrollTop");
    if (scrollTopBtn) {
        scrollTopBtn.addEventListener("click", () => {
            window.scrollTo({ top: 0, behavior: "smooth" });
        });
    }
});
