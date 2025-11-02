// ==============================
// SwiftAid Dashboard Script
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
            const vehicle_number = document.getElementById("vehicle_number").value;
            const driver_name = document.getElementById("driver_name").value;
            const phone = document.getElementById("phone").value;

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

    // ===== Load Ambulances =====
    async function loadAmbulances() {
        const res = await fetch("/ambulances");
        const data = await res.json();
        ambulanceList.innerHTML = "";

        if (data.success && data.ambulances.length > 0) {
            data.ambulances.forEach(amb => {
                const toggleText = amb.status === "available" ? "Mark On-Duty" : "Mark Available";
                const toggleColor = amb.status === "available" ? "#ffc107" : "#28a745";

                ambulanceList.innerHTML += `
                    <div class="card">
                        <h3>🚐 ${amb.vehicle_number}</h3>
                        <p><strong>Driver:</strong> ${amb.driver_name}</p>
                        <p><strong>Phone:</strong> ${amb.phone}</p>
                        <p><strong>Status:</strong> 
                            <span style="color:${amb.status === "available" ? "green" : "red"};">
                                ${amb.status}
                            </span>
                        </p>
                        <button class="btn" 
                            style="background-color:${toggleColor}; color:white;"
                            onclick="toggleAmbulanceStatus('${amb._id}', '${amb.status}')">
                            ${toggleText}
                        </button>
                    </div>
                `;
            });
        } else {
            ambulanceList.innerHTML = "<p>No ambulances added yet.</p>";
        }
    }

    const ambulanceTab = document.querySelector('a[href="#ambulances"]');
    if (ambulanceTab) {
        ambulanceTab.addEventListener("click", loadAmbulances);
    }

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
            alert(result.message);
            if (result.success) loadAmbulances();
        } catch (err) {
            console.error("Error updating ambulance status:", err);
            alert("Failed to update status. Try again.");
        }
    };
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

// 🗑️ Delete Case Status (Revert Decision)
async function deleteCaseStatus(incidentId) {
    if (!confirm("Are you sure you want to delete this case decision?")) return;
    try {
        const response = await fetch("/delete_case_status", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ incident_id: incidentId })
        });
        const data = await response.json();
        alert(data.message);
        if (data.success) location.reload();
    } catch (err) {
        console.error("deleteCaseStatus error:", err);
        alert("Failed to delete case decision. Try again.");
    }
}

// ==============================
// 🧹 CLEAR INCIDENT (Delete Case)
// ==============================
async function clearIncident(incidentId) {
    if (!confirm("Are you sure you want to permanently delete this case?")) return;

    try {
        const res = await fetch("/delete_incident", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ incident_id: incidentId })
        });

        const data = await res.json();
        alert(data.message);

        if (data.success) {
            // Smoothly remove the case card
            const card = document.getElementById(`case-${incidentId}`);
            if (card) {
                card.style.transition = "opacity 0.4s ease";
                card.style.opacity = "0";
                setTimeout(() => card.remove(), 400);
            }

            // 🔄 Reload ambulance section silently
            if (typeof loadAmbulances === "function") {
                loadAmbulances();
            }
        }
    } catch (err) {
        console.error("clearIncident error:", err);
        alert("Failed to clear case. Please try again.");
    }
}



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

    try {
        const res = await fetch("/assign_ambulance", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                incident_id: currentIncidentId,
                ambulance_id: ambulanceId
            })
        });

        const data = await res.json();

        if (!res.ok) {
            alert(data.message || "Failed to assign ambulance");
            if (btnElem) {
                btnElem.disabled = false;
                btnElem.textContent = "Assign";
            }
            if (res.status === 409) location.reload();
            return;
        }

        alert(data.message || "Assigned!");
        closeAssignPopup();
        location.reload();
    } catch (err) {
        console.error("assignAmbulance error:", err);
        alert("Network or server error while assigning ambulance");
        if (btnElem) {
            btnElem.disabled = false;
            btnElem.textContent = "Assign";
        }
    }
}
