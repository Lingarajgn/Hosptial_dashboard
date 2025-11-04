// ==============================
// SwiftAid Dashboard Script (Full Fixed Version)
// ==============================
document.addEventListener("DOMContentLoaded", () => {
    // ===== Dropdown Toggle =====
    const dropBtn = document.querySelector(".dropbtn");
    const dropdownMenu = document.getElementById("dropdownMenu");

    if (dropBtn) {
        dropBtn.addEventListener("click", (e) => {
            e.stopPropagation();
            dropdownMenu.classList.toggle("show");
        });
    }
    window.addEventListener("click", () => dropdownMenu.classList.remove("show"));

    // ===== Sidebar Tabs =====
    const navLinks = document.querySelectorAll(".sidebar nav a");
    const sections = document.querySelectorAll(".tab-section");
    navLinks.forEach(link => {
        link.addEventListener("click", (e) => {
            e.preventDefault();
            const targetId = link.getAttribute("href").substring(1);
            navLinks.forEach(l => l.classList.remove("active"));
            link.classList.add("active");
            sections.forEach(section => {
                section.style.display = (section.id === targetId) ? "block" : "none";
            });
        });
    });

    // ===== Leaflet Map =====
    if (typeof incidentsData !== "undefined" && incidentsData.length > 0) {
        const map = L.map("map").setView([14.4663, 75.9219], 12);
        L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
            maxZoom: 19,
            attribution: "© OpenStreetMap contributors"
        }).addTo(map);

        incidentsData.forEach(incident => {
            if (incident.lat && incident.lng) {
                const marker = L.marker([incident.lat, incident.lng]).addTo(map);
                marker.bindPopup(`
                    <b>${incident.user_email}</b><br>
                    📍 Lat: ${incident.lat}, Lng: ${incident.lng}<br>
                    ⚡ Accel: ${incident.accel_mag.toFixed(2)}<br>
                    🚀 Speed: ${incident.speed}
                `);
            }
        });
    }

    // ===== Profile Editing =====
    const editBtn = document.getElementById("editProfileBtn");
    const cancelBtn = document.getElementById("cancelEditBtn");
    const profileView = document.getElementById("profileView");
    const editForm = document.getElementById("editProfileForm");
    const updateMessage = document.getElementById("updateMessage");

    if (editBtn && cancelBtn) {
        editBtn.addEventListener("click", () => {
            profileView.style.display = "none";
            editForm.style.display = "flex";
        });
        cancelBtn.addEventListener("click", () => {
            editForm.style.display = "none";
            profileView.style.display = "block";
        });
    }

    if (editForm) {
        editForm.addEventListener("submit", async (e) => {
            e.preventDefault();
            const formData = new FormData(editForm);

            try {
                const response = await fetch("/update_profile", {
                    method: "POST",
                    body: formData
                });
                const data = await response.json();
                updateMessage.style.display = "block";
                updateMessage.textContent = data.message;
                updateMessage.style.color = data.success ? "green" : "red";

                if (data.success) {
                    setTimeout(() => {
                        editForm.style.display = "none";
                        profileView.style.display = "block";
                        window.location.reload();
                    }, 1000);
                }
            } catch (error) {
                console.error("Update failed:", error);
                updateMessage.style.display = "block";
                updateMessage.style.color = "red";
                updateMessage.textContent = "Error saving profile.";
            }
        });
    }

    // ===== Ambulance Management =====
    const addAmbulanceBtn = document.getElementById("addAmbulanceBtn");
    const addAmbulanceForm = document.getElementById("addAmbulanceForm");
    const cancelAmbulanceBtn = document.getElementById("cancelAmbulanceBtn");
    const ambulanceList = document.getElementById("ambulanceList");

    if (addAmbulanceBtn) {
        addAmbulanceBtn.addEventListener("click", () => {
            addAmbulanceForm.style.display = "flex";
        });
    }

    if (cancelAmbulanceBtn) {
        cancelAmbulanceBtn.addEventListener("click", () => {
            addAmbulanceForm.style.display = "none";
        });
    }

    if (addAmbulanceForm) {
        addAmbulanceForm.addEventListener("submit", async (e) => {
            e.preventDefault();
            const vehicle_number = document.getElementById("vehicle_number").value.trim();
            const driver_name = document.getElementById("driver_name").value.trim();
            const phone = document.getElementById("phone").value.trim();

            const namePattern = /^[A-Za-z ]+$/;
            const phonePattern = /^[0-9]{10}$/;

            if (!vehicle_number || !driver_name || !phone) {
                alert("All fields are required.");
                return;
            }

            if (!namePattern.test(driver_name)) {
                alert("Invalid driver name. Only letters and spaces allowed.");
                return;
            }

            if (!phonePattern.test(phone)) {
                alert("Invalid phone number. Must be 10 digits.");
                return;
            }

            const response = await fetch("/add_ambulance", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ vehicle_number, driver_name, phone })
            });

            const data = await response.json();
            alert(data.message);
            if (data.success) {
                addAmbulanceForm.reset();
                addAmbulanceForm.style.display = "none";
                loadAmbulances();
            }
        });
    }

    async function loadAmbulances() {
        const res = await fetch("/ambulances");
        const data = await res.json();
        ambulanceList.innerHTML = "";

        if (data.success && data.ambulances.length > 0) {
            data.ambulances.forEach(amb => {
                let actionButton = "";

                if (amb.status === "available") {
                    actionButton = `
                        <button class="btn" 
                            style="background-color:#ffc107; color:white;"
                            onclick="toggleAmbulanceStatus('${amb._id}', '${amb.status}')">
                            Mark On-Duty
                        </button>`;
                } else if (amb.status === "on-duty" && !amb.assigned_case) {
                    actionButton = `
                        <button class="btn" 
                            style="background-color:#28a745; color:white;"
                            onclick="toggleAmbulanceStatus('${amb._id}', '${amb.status}')">
                            Mark Available
                        </button>`;
                } else if (amb.status === "on-duty" && amb.assigned_case) {
                    actionButton = `
                        <button class="btn" style="background-color:#6c757d; color:white; cursor:not-allowed;" disabled>
                            🔒 Assigned to Case
                        </button>`;
                }

                ambulanceList.innerHTML += `
                    <div class="card">
                        <h3>🚐 ${amb.vehicle_number}</h3>
                        <p><strong>Driver:</strong> ${amb.driver_name}</p>
                        <p><strong>Phone:</strong> ${amb.phone}</p>
                        <p><strong>Status:</strong> 
                            <span style="color:${amb.status === "available" ? "green" : "red"};">
                                ${amb.status}${amb.assigned_case ? " (Locked)" : ""}
                            </span>
                        </p>
                        ${actionButton}
                    </div>`;
            });
        } else {
            ambulanceList.innerHTML = "<p>No ambulances added yet.</p>";
        }
    }

    const ambulanceTab = document.querySelector('a[href="#ambulances"]');
    if (ambulanceTab) ambulanceTab.addEventListener("click", loadAmbulances);

    window.toggleAmbulanceStatus = async function (ambulanceId, currentStatus) {
        const newStatus = currentStatus === "available" ? "on-duty" : "available";
        if (!confirm(`Change status to '${newStatus}'?`)) return;

        try {
            const response = await fetch("/update_ambulance_status", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ ambulance_id: ambulanceId, status: newStatus })
            });

            const result = await response.json();

            if (!result.success) {
                alert(result.message);
                return;
            }

            alert(result.message);
            await loadAmbulances();
        } catch (err) {
            console.error("Error updating ambulance status:", err);
            alert("Failed to update status. Please try again.");
        }
    };

    // ==============================
    // 🩺 RESOLVED CASES MANAGEMENT
    // ==============================
    async function loadResolvedCases() {
        const res = await fetch("/resolved_cases");
        const data = await res.json();
        const resolvedList = document.getElementById("resolvedCasesList");

        resolvedList.innerHTML = "";

        if (data.success && data.resolved_cases.length > 0) {
            data.resolved_cases.forEach(caseItem => {
                resolvedList.innerHTML += `
                    <div class="card">
                        <h3>📋 Case ID: ${caseItem.incident_id}</h3>
                        <p><strong>Hospital:</strong> ${caseItem.hospital_name}</p>
                        <p><strong>User Email:</strong> ${caseItem.user_email}</p>
                        <p><strong>Driver:</strong> ${caseItem.driver_name || "N/A"}</p>
                        <p><strong>Vehicle:</strong> ${caseItem.vehicle_number || "N/A"}</p>
                        <p><strong>Resolved At:</strong> ${caseItem.resolved_at}</p>
                        <div class="case-actions">
                            <button class="btn" style="background-color:#dc3545;color:white;" onclick="deleteResolvedCase('${caseItem._id}')">🗑️ Delete</button>
                            <button class="btn" style="background-color:#17a2b8;color:white;" onclick="downloadResolvedPDF('${caseItem._id}')">📄 Download PDF</button>
                        </div>
                    </div>`;
            });
        } else {
            resolvedList.innerHTML = "<p>No resolved cases yet.</p>";
        }
    }
    window.loadResolvedCases = loadResolvedCases;

    window.deleteResolvedCase = async function (caseId) {
        if (!confirm("Are you sure you want to delete this resolved case?")) return;
        const res = await fetch("/delete_resolved_case", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ case_id: caseId })
        });
        const data = await res.json();
        alert(data.message);
        if (data.success) loadResolvedCases();
    };

    window.downloadResolvedPDF = function (caseId) {
        window.location.href = `/download_resolved_case/${caseId}`;
    };

    const resolvedTab = document.querySelector('a[href="#resolved-cases"]');
    if (resolvedTab) resolvedTab.addEventListener("click", loadResolvedCases);

    // ===== Profile Dropdown -> Settings =====
    const profileLink = document.getElementById("profileLink");
    if (profileLink) {
        profileLink.addEventListener("click", (e) => {
            e.preventDefault();
            document.querySelectorAll(".tab-section").forEach(sec => sec.style.display = "none");
            const settingsSection = document.getElementById("settings");
            if (settingsSection) settingsSection.style.display = "block";
            document.querySelectorAll(".sidebar nav a").forEach(l => l.classList.remove("active"));
            document.querySelector('.sidebar nav a[href="#settings"]').classList.add("active");
            dropdownMenu.classList.remove("show");
            window.scrollTo({ top: 0, behavior: "smooth" });
        });
    }
});

// ==============================
// Accept / Reject Case + Assign Ambulance + Delete Decision
// ==============================
let currentIncidentId = null;

async function updateCaseStatus(incidentId, status) {
    if (status === "accepted") {
        openAssignPopup(incidentId);
        return;
    }

    const response = await fetch("/update_case_status", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ incident_id: incidentId, status })
    });

    const data = await response.json();
    alert(data.message);
    if (data.success) location.reload();
}

// 🧹 CLEAR INCIDENT
async function clearIncident(incidentId) {
    if (!confirm("Are you sure you want to permanently delete this case?")) return;
    const res = await fetch("/delete_incident", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ incident_id: incidentId })
    });
    const data = await res.json();
    alert(data.message);
    if (data.success) location.reload();
}

// Popup for assigning ambulance
function openAssignPopup(incidentId) {
    currentIncidentId = incidentId;
    const popup = document.getElementById("assignAmbulancePopup");
    const listDiv = document.getElementById("ambulanceOptions");
    popup.style.display = "flex";

    fetch("/ambulances")
        .then(res => res.json())
        .then(data => {
            if (data.success && data.ambulances.length > 0) {
                listDiv.innerHTML = data.ambulances
                    .filter(a => a.status === "available")
                    .map(a => `
                        <div class="ambulance-option">
                            <p>🚐 <strong>${a.vehicle_number}</strong> — ${a.driver_name} (${a.phone})</p>
                            <button class="btn assign-btn" onclick="assignAmbulance('${a._id}', this)">Assign</button>
                        </div>
                    `).join("");
            } else {
                listDiv.innerHTML = "<p>No available ambulances right now.</p>";
            }
        });
}

function closeAssignPopup() {
    document.getElementById("assignAmbulancePopup").style.display = "none";
    currentIncidentId = null;
}

async function assignAmbulance(ambulanceId, btnElem) {
    if (!currentIncidentId) return alert("No case selected");
    if (btnElem) {
        btnElem.disabled = true;
        btnElem.textContent = "Assigning...";
    }
    const res = await fetch("/assign_ambulance", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ incident_id: currentIncidentId, ambulance_id: ambulanceId })
    });
    const data = await res.json();
    alert(data.message);
    if (data.success) {
        closeAssignPopup();
        location.reload();
    } else {
        if (btnElem) {
            btnElem.disabled = false;
            btnElem.textContent = "Assign";
        }
    }
}
