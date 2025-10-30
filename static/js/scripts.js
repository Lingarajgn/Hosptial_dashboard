document.addEventListener("DOMContentLoaded", () => {
    // Sidebar navigation
    const navLinks = document.querySelectorAll(".sidebar nav a");
    const sections = {
        dashboard: [document.getElementById("stats"), document.querySelector(".map-container")],
        cases: [document.getElementById("cases")],
        settings: [document.getElementById("settings")]
    };

    navLinks.forEach(link => {
        link.addEventListener("click", e => {
            e.preventDefault();
            navLinks.forEach(n => n.classList.remove("active"));
            link.classList.add("active");

            Object.values(sections).flat().forEach(sec => sec && (sec.style.display = "none"));
            const target = link.getAttribute("href").replace("#", "");
            (sections[target] || []).forEach(sec => sec && (sec.style.display = "block"));
        });
    });

    // Leaflet Map
    if (typeof incidentsData !== "undefined" && incidentsData.length > 0) {
        const map = L.map("map").setView([14.4663, 75.9219], 12);
        L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
            maxZoom: 19,
            attribution: "© OpenStreetMap contributors"
        }).addTo(map);

        incidentsData.forEach(incident => {
            if (incident.latitude && incident.longitude) {
                const marker = L.marker([incident.latitude, incident.longitude]).addTo(map);
                marker.bindPopup(`<b>${incident.title}</b><br>${incident.location}`);
            }
        });
    }

    // Settings - Toggle Edit Mode
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

    // AJAX Profile Save
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
                        window.location.reload(); // Refresh data
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
});
