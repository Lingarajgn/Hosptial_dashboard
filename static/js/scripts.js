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

    window.addEventListener("click", () => {
        dropdownMenu.classList.remove("show");
    });

    // ===== Sidebar Tabs (Single Page Navigation) =====
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
