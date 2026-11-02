// ==========================================================================
// ⚡ GridPulse Interactive GIS Map Engine (Leaflet.js)
// Dynamic Theme Layers, Substation Zones, Glowing Pins & Auto-Sync
// ==========================================================================

let outageMap = null;
let currentTileLayer = null;
let markersLayer = null;
let substationsLayer = null;
let allOutages = [];
let allLocalities = [];
let autoRefreshTimer = null;

const TILE_URLS = {
    light: "https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png",
    dark: "https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png",
    emergency: "https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png"
};

function getMapTileUrl(theme) {
    return TILE_URLS[theme] || TILE_URLS.light;
}

function initOutageMap() {
    const mapElement = document.getElementById("outageMap");
    if (!mapElement) return;

    // Default center: Metro locality cluster
    const defaultCenter = [12.9716, 77.6200];
    const defaultZoom = 12;

    outageMap = L.map("outageMap", {
        center: defaultCenter,
        zoom: defaultZoom,
        zoomControl: true,
        scrollWheelZoom: false
    });

    // Determine current theme
    const activeTheme = document.documentElement.getAttribute("data-theme") || "light";
    currentTileLayer = L.tileLayer(getMapTileUrl(activeTheme), {
        attribution: '&copy; <a href="https://carto.com/">CARTO</a> &copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
        maxZoom: 19
    }).addTo(outageMap);

    markersLayer = L.layerGroup().addTo(outageMap);
    substationsLayer = L.layerGroup().addTo(outageMap);

    // Initial load
    loadMapData("all");

    // Hook theme change handler
    window.onThemeChanged = function (newTheme) {
        if (outageMap && currentTileLayer) {
            outageMap.removeLayer(currentTileLayer);
            currentTileLayer = L.tileLayer(getMapTileUrl(newTheme), {
                attribution: '&copy; CARTO &copy; OpenStreetMap',
                maxZoom: 19
            }).addTo(outageMap);
        }
    };

    // Setup filter button listeners
    const filterButtons = document.querySelectorAll("[data-map-filter]");
    filterButtons.forEach((btn) => {
        btn.addEventListener("click", function () {
            filterButtons.forEach((b) => b.classList.remove("active", "btn-primary"));
            filterButtons.forEach((b) => b.classList.add("btn-outline-secondary"));

            this.classList.remove("btn-outline-secondary");
            this.classList.add("active", "btn-primary");

            const filterType = this.getAttribute("data-map-filter");
            filterMarkers(filterType);
        });
    });

    // Auto-refresh map data every 25 seconds
    autoRefreshTimer = setInterval(() => {
        const activeBtn = document.querySelector("[data-map-filter].active");
        const activeFilter = activeBtn ? activeBtn.getAttribute("data-map-filter") : "all";
        loadMapData(activeFilter, false); // silent background reload
    }, 25000);

    // Manual refresh button listener
    const refreshBtn = document.getElementById("btnRefreshMap");
    if (refreshBtn) {
        refreshBtn.addEventListener("click", () => {
            refreshBtn.classList.add("disabled");
            refreshBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-1"></span> Syncing...';
            const activeBtn = document.querySelector("[data-map-filter].active");
            const activeFilter = activeBtn ? activeBtn.getAttribute("data-map-filter") : "all";
            loadMapData(activeFilter, true).finally(() => {
                refreshBtn.classList.remove("disabled");
                refreshBtn.innerHTML = '<i class="bi bi-arrow-clockwise me-1"></i> Sync Live Data';
            });
        });
    }
}

function loadMapData(filter = "all", fitBounds = true) {
    const apiKey = window.GRIDPULSE_API_KEY || "gp_live_scada_demo_key_2026";
    const headers = { "X-API-Key": apiKey };

    return Promise.all([
        fetch("/api/outages", { headers }).then((res) => res.json()),
        fetch("/api/localities", { headers }).then((res) => res.json())
    ])
    .then(([outagesData, localitiesData]) => {
        if (outagesData.success) {
            allOutages = outagesData.data;
            renderMarkers(allOutages, filter, fitBounds);
        }
        if (localitiesData.success) {
            allLocalities = localitiesData.data;
            renderSubstations(allLocalities);
        }
    })
    .catch((err) => console.error("Error loading GIS map data:", err));
}

function getMarkerIcon(severity, status) {
    let pinClass = "pin-medium";
    let iconSymbol = "⚡";

    if (status === "RESOLVED") {
        pinClass = "pin-resolved";
        iconSymbol = "✓";
    } else if (severity === "CRITICAL") {
        pinClass = "pin-critical";
        iconSymbol = "⚠";
    } else if (severity === "HIGH") {
        pinClass = "pin-high";
        iconSymbol = "⚡";
    }

    return L.divIcon({
        className: "custom-marker-wrapper",
        html: `<div class="custom-pin ${pinClass}" style="width: 34px; height: 34px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 15px; box-shadow: 0 4px 12px rgba(0,0,0,0.35); color: #fff;">${iconSymbol}</div>`,
        iconSize: [34, 34],
        iconAnchor: [17, 17],
        popupAnchor: [0, -20]
    });
}

function renderSubstations(localities) {
    if (!substationsLayer) return;
    substationsLayer.clearLayers();

    localities.forEach(loc => {
        if (!loc.lat || !loc.lng) return;

        // Locality center circle marker
        const circle = L.circle([loc.lat, loc.lng], {
            color: loc.active_outages > 0 ? '#ef4444' : '#10b981',
            fillColor: loc.active_outages > 0 ? '#ef4444' : '#10b981',
            fillOpacity: 0.08,
            radius: 800,
            weight: 1.5,
            dashArray: '4, 4'
        });

        circle.bindTooltip(`<strong>${loc.name}</strong><br><small>${loc.substation_name}</small>`, {
            permanent: false,
            direction: "top"
        });

        substationsLayer.addLayer(circle);
    });
}

function renderMarkers(outages, filter, fitBounds = true) {
    if (!markersLayer) return;
    markersLayer.clearLayers();

    const filtered = outages.filter((item) => {
        if (filter === "all") return true;
        if (filter === "critical") return item.severity === "CRITICAL" && item.status !== "RESOLVED";
        if (filter === "active") return item.status !== "RESOLVED" && item.status !== "CLOSED";
        if (filter === "resolved") return item.status === "RESOLVED";
        return true;
    });

    const bounds = [];

    filtered.forEach((outage) => {
        if (!outage.lat || !outage.lng) return;

        const marker = L.marker([outage.lat, outage.lng], {
            icon: getMarkerIcon(outage.severity, outage.status)
        });

        // Popup HTML with real-time upvote ability
        const popupContent = `
            <div style="min-width: 240px; font-family: 'Plus Jakarta Sans', system-ui, sans-serif;">
                <div class="d-flex justify-content-between align-items-center mb-1.5">
                    <span class="badge bg-dark text-warning font-mono" style="font-size: 0.75rem;">${outage.ticket_no}</span>
                    <span class="badge ${outage.severity === 'CRITICAL' ? 'bg-danger' : outage.severity === 'HIGH' ? 'bg-warning text-dark' : 'bg-secondary'}" style="font-size: 0.7rem;">${outage.severity}</span>
                </div>
                <h6 class="fw-bold mb-1" style="font-size: 0.95rem; color: #0f172a;">${outage.outage_type}</h6>
                <div class="small text-muted mb-2"><i class="bi bi-geo-alt-fill text-danger me-1"></i>${outage.locality_name}</div>
                <p class="small text-secondary mb-2" style="font-size: 0.8rem; line-height: 1.35;">${outage.address}</p>
                
                <div class="p-2.5 rounded mb-2 border small" style="font-size: 0.78rem; background: rgba(0,0,0,0.03);">
                    <div><strong>Status:</strong> <span class="badge badge-status status-${outage.status}" style="font-size: 0.68rem;">${outage.status.replace(/_/g, ' ')}</span></div>
                    ${outage.estimated_restoration ? `<div class="mt-1"><strong>Target ETR:</strong> <span class="text-primary fw-bold">${outage.estimated_restoration}</span></div>` : ''}
                    <div class="mt-1"><strong>Impact:</strong> ~${outage.affected_households} households</div>
                    ${outage.crew_name ? `<div class="mt-1"><strong>Line Crew:</strong> ${outage.crew_name}</div>` : ''}
                </div>

                <div class="d-flex gap-1.5">
                    <a href="/track?ticket=${outage.ticket_no}" class="btn btn-sm btn-primary flex-grow-1 py-1" style="font-size: 0.8rem;">
                        <i class="bi bi-search me-1"></i> Track Ticket
                    </a>
                </div>
            </div>
        `;

        marker.bindPopup(popupContent);
        markersLayer.addLayer(marker);
        bounds.push([outage.lat, outage.lng]);
    });

    // Auto-fit if markers exist and requested
    if (fitBounds && bounds.length > 0 && outageMap) {
        outageMap.fitBounds(bounds, { padding: [50, 50], maxZoom: 14 });
    }
}

function filterMarkers(filterType) {
    renderMarkers(allOutages, filterType, false);
}

document.addEventListener("DOMContentLoaded", function () {
    initOutageMap();
});
