from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from pymongo import MongoClient
from bson.objectid import ObjectId
from werkzeug.security import generate_password_hash, check_password_hash
from config import MONGO_URI
from datetime import datetime
import re
from io import BytesIO
from flask import send_file
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

app = Flask(__name__)
app.secret_key = "supersecretkey"

# -----------------------------
# MONGO DB CONNECTION
# -----------------------------
try:
    client = MongoClient(MONGO_URI)
    db = client['SwiftAid']
    hospital_users = db['hospital_user']
    incidents_collection = db['incidents']
    case_status_collection = db['case_status']
    ambulances_collection = db['ambulances']
    resolved_cases_collection = db['resolved_cases']

    print("✅ Connected to MongoDB successfully")
except Exception as e:
    print("❌ MongoDB Connection Failed:", e)

# -----------------------------
# DASHBOARD
# -----------------------------
@app.route("/")
def dashboard():
    if "email" not in session:
        return redirect(url_for("login"))

    user = hospital_users.find_one({"email": session["email"]})
    if not user:
        return redirect(url_for("logout"))

    hospital_name = session.get("hospital_name")

    try:
        incidents = list(incidents_collection.find())
        all_statuses = list(case_status_collection.find())

        for inc in incidents:
            inc["_id"] = str(inc["_id"])
            inc["lat"] = inc.get("lat", 14.4663)
            inc["lng"] = inc.get("lng", 75.9219)
            inc["user_email"] = inc.get("user_email", "Unknown")
            inc["speed"] = inc.get("speed", 0)
            inc["accel_mag"] = inc.get("accel_mag", 0)
            inc["created_at"] = inc.get("metadata", {}).get("created_at", "N/A")

        for cs in all_statuses:
            cs["_id"] = str(cs["_id"])
            if "incident_id" in cs:
                cs["incident_id"] = str(cs["incident_id"])

        accepted_cases_global = {cs["incident_id"]: cs for cs in all_statuses if cs["status"] == "accepted"}
        rejected_cases_by_hospital = {
            cs["incident_id"]: cs for cs in all_statuses
            if cs["status"] == "rejected" and cs.get("hospital_name") == hospital_name
        }

        for inc in incidents:
            if inc["_id"] in accepted_cases_global:
                inc["status_info"] = accepted_cases_global[inc["_id"]]
            elif inc["_id"] in rejected_cases_by_hospital:
                inc["status_info"] = {"status": "rejected", "hospital_name": hospital_name}
            else:
                inc["status_info"] = None

        active_cases = len(incidents)
        accepted_cases = case_status_collection.count_documents({
            "status": "accepted",
            "hospital_name": hospital_name
        })

        available_ambulances = ambulances_collection.count_documents({
            "hospital_name": hospital_name,
            "status": "available"
        })

        resolved_cases = resolved_cases_collection.count_documents({
            "hospital_name": hospital_name
        })

    except Exception as e:
        print("❌ Error fetching incidents:", e)
        incidents, active_cases, accepted_cases = [], 0, 0

    return render_template(
        "dashboard.html",
        active_cases=active_cases,
        accepted_cases=accepted_cases,
        available_ambulances=available_ambulances,
        resolved_cases=resolved_cases,
        incidents=incidents,
        hospital_name=hospital_name,
        user=user
    )

# -----------------------------
# UPDATE CASE STATUS
# -----------------------------
@app.route("/update_case_status", methods=["POST"])
def update_case_status():
    """
    Update case status:
    ✅ Store only 'accepted' in DB
    ❌ If user rejects an already accepted case, delete it
    🚑 If any ambulance was linked, free it automatically
    """
    if "email" not in session:
        return jsonify({"success": False, "message": "Not logged in"}), 403

    data = request.get_json()
    incident_id = data.get("incident_id")
    status = data.get("status")

    if not incident_id or status not in ["accepted", "rejected"]:
        return jsonify({"success": False, "message": "Invalid input"}), 400

    user_email = session["email"]
    hospital = hospital_users.find_one({"email": user_email})
    hospital_name = hospital.get("hospital_name", "Unknown Hospital")

    try:
        if status == "accepted":
            # ✅ Add or update accepted case
            case_status_collection.update_one(
                {"incident_id": incident_id, "hospital_name": hospital_name},
                {
                    "$set": {
                        "incident_id": incident_id,
                        "hospital_name": hospital_name,
                        "accepted_by": user_email,
                        "status": "accepted",
                        "updated_at": datetime.utcnow()
                    }
                },
                upsert=True
            )
            return jsonify({"success": True, "message": "Case accepted successfully!"})

        elif status == "rejected":
            # 🧹 Delete case status (don’t store rejected)
            delete_result = case_status_collection.delete_one({
                "incident_id": incident_id,
                "hospital_name": hospital_name
            })

            # 🚑 If an ambulance was assigned, mark it as available
            linked_ambulance = ambulances_collection.find_one({"current_incident_id": incident_id})
            if linked_ambulance:
                ambulances_collection.update_one(
                    {"_id": linked_ambulance["_id"]},
                    {"$set": {"status": "available", "current_incident_id": None}}
                )

            if delete_result.deleted_count > 0:
                msg = "Case rejected and ambulance (if any) released."
            else:
                msg = "Case was not previously accepted."
            return jsonify({"success": True, "message": msg})

    except Exception as e:
        print("❌ update_case_status error:", e)
        return jsonify({"success": False, "message": "Server error"}), 500

# -----------------------------
# CASE DETAIL PAGE
# -----------------------------
@app.route("/case/<incident_id>")
def case_detail(incident_id):
    if "email" not in session:
        return redirect(url_for("login"))

    hospital_name = session.get("hospital_name")

    try:
        incident = incidents_collection.find_one({"_id": ObjectId(incident_id)})
        if not incident:
            return "Case not found", 404

        incident["_id"] = str(incident["_id"])
        incident["lat"] = incident.get("lat", 14.4663)
        incident["lng"] = incident.get("lng", 75.9219)
        incident["user_email"] = incident.get("user_email", "Unknown")
        incident["speed"] = incident.get("speed", 0)
        incident["accel_mag"] = incident.get("accel_mag", 0)
        incident["created_at"] = incident.get("metadata", {}).get("created_at", "N/A")

        status = case_status_collection.find_one({"incident_id": str(incident["_id"])})
        if status:
            incident["status"] = status["status"]
            incident["accepted_by"] = status.get("hospital_name")
        else:
            incident["status"] = "available"
            incident["accepted_by"] = None

    except Exception as e:
        print("❌ Error fetching case detail:", e)
        return "Error loading case details", 500

    return render_template(
        "case_detail.html",
        incident=incident,
        hospital_name=hospital_name
    )

# -----------------------------
# AMBULANCE ROUTES
# -----------------------------
@app.route("/ambulances", methods=["GET"])
def get_ambulances():
    """Fetch all ambulances belonging to the logged-in hospital and auto-sync their availability."""
    if "email" not in session:
        return jsonify({"success": False, "message": "Not logged in"}), 403

    hospital_name = session.get("hospital_name")
    ambs = list(ambulances_collection.find({"hospital_name": hospital_name}))

    for amb in ambs:
        amb_id = amb.get("_id")
        current_incident = amb.get("current_incident_id")

        # 🧠 Automatically sync status and mark assigned_case flag
        if not current_incident or current_incident in ("", None):
            # No case → mark available
            if amb.get("status") != "available":
                ambulances_collection.update_one(
                    {"_id": amb_id},
                    {"$set": {"status": "available", "current_incident_id": None}}
                )
            amb["status"] = "available"
            amb["assigned_case"] = False
        else:
            # Has assigned case → ensure on-duty and lock it
            if amb.get("status") != "on-duty":
                ambulances_collection.update_one(
                    {"_id": amb_id},
                    {"$set": {"status": "on-duty"}}
                )
            amb["status"] = "on-duty"
            amb["assigned_case"] = True

        amb["_id"] = str(amb["_id"])

    return jsonify({"success": True, "ambulances": ambs})

# -----------------------------
# GET RESOLVED CASES
# -----------------------------
@app.route("/resolved_cases", methods=["GET"])
def get_resolved_cases():
    if "email" not in session:
        return jsonify({"success": False, "message": "Not logged in"}), 403

    hospital_name = session.get("hospital_name")
    cases = list(resolved_cases_collection.find({"hospital_name": hospital_name}))
    for c in cases:
        c["_id"] = str(c["_id"])
    return jsonify({"success": True, "resolved_cases": cases})

# -----------------------------
# DELETE RESOLVED CASE
# -----------------------------
@app.route("/delete_resolved_case", methods=["POST"])
def delete_resolved_case():
    if "email" not in session:
        return jsonify({"success": False, "message": "Not logged in"}), 403

    data = request.get_json()
    case_id = data.get("case_id")

    if not case_id:
        return jsonify({"success": False, "message": "Missing case ID"}), 400

    try:
        result = resolved_cases_collection.delete_one({"_id": ObjectId(case_id)})
        if result.deleted_count == 0:
            return jsonify({"success": False, "message": "Case not found"}), 404
        return jsonify({"success": True, "message": "Resolved case deleted successfully!"})
    except Exception as e:
        print("❌ delete_resolved_case error:", e)
        return jsonify({"success": False, "message": "Error deleting resolved case"}), 500

# -----------------------------
# DOWNLOAD RESOLVED CASE AS PDF
# -----------------------------
@app.route("/download_resolved_case/<case_id>", methods=["GET"])
def download_resolved_case(case_id):
    """Generate a professional PDF report for resolved case."""
    if "email" not in session:
        return redirect(url_for("login"))

    case = resolved_cases_collection.find_one({"_id": ObjectId(case_id)})
    if not case:
        return "Case not found", 404

    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter

    # ===== Header Section =====
    pdf.setFont("Helvetica-Bold", 20)
    pdf.setFillColorRGB(0.2, 0.4, 0.6)
    pdf.drawString(180, 770, "🏥 SwiftAid Hospital Report")

    pdf.setFillColorRGB(0, 0, 0)
    pdf.setFont("Helvetica", 12)
    pdf.drawString(50, 745, f"Generated On: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC")
    pdf.line(50, 740, 550, 740)

    # ===== Case Information =====
    pdf.setFont("Helvetica-Bold", 14)
    pdf.drawString(50, 715, "🩺 Resolved Case Details:")
    pdf.setFont("Helvetica", 12)

    y = 690
    field_labels = {
        "incident_id": "Incident ID",
        "hospital_name": "Hospital Name",
        "user_email": "User Email",
        "driver_name": "Driver Name",
        "vehicle_number": "Vehicle Number",
        "resolved_at": "Resolved At"
    }

    for key, label in field_labels.items():
        value = case.get(key, "N/A")
        pdf.setFont("Helvetica-Bold", 12)
        pdf.drawString(60, y, f"{label}:")
        pdf.setFont("Helvetica", 12)
        pdf.drawString(200, y, str(value))
        y -= 25

    # ===== Footer =====
    pdf.setFont("Helvetica-Oblique", 11)
    pdf.setFillColorRGB(0.3, 0.3, 0.3)
    pdf.drawString(50, 60, "SwiftAid Emergency Response System — Confidential Report")
    pdf.drawString(50, 45, "For internal hospital use only. © 2025 SwiftAid")

    pdf.save()
    buffer.seek(0)

    return send_file(
        buffer,
        as_attachment=True,
        download_name=f"resolved_case_{case_id}.pdf",
        mimetype="application/pdf"
    )

# -----------------------------
# Add Ambulance
# -----------------------------
@app.route("/add_ambulance", methods=["POST"])
def add_ambulance():
    if "email" not in session:
        return jsonify({"success": False, "message": "Not logged in"}), 403

    data = request.get_json()
    vehicle_number = data.get("vehicle_number", "").strip()
    driver_name = data.get("driver_name", "").strip()
    phone = data.get("phone", "").strip()
    hospital_name = session.get("hospital_name")

    # ✅ Validation checks
    if not vehicle_number or not driver_name or not phone:
        return jsonify({"success": False, "message": "All fields are required"}), 400

    # Name should only contain letters and spaces
    if not re.match(r"^[A-Za-z ]+$", driver_name):
        return jsonify({"success": False, "message": "Invalid driver name. Only letters and spaces allowed."}), 400

    # Phone must be exactly 10 digits
    if not re.match(r"^[0-9]{10}$", phone):
        return jsonify({"success": False, "message": "Invalid phone number. Must be 10 digits."}), 400

    ambulances_collection.insert_one({
        "vehicle_number": vehicle_number,
        "driver_name": driver_name,
        "phone": phone,
        "status": "available",
        "hospital_name": hospital_name
    })
    return jsonify({"success": True, "message": "Ambulance added successfully"})

from bson import ObjectId

# -----------------------------
# UPDATE_AMBULANCE_STATUS ROUTES
# -----------------------------
@app.route("/update_ambulance_status", methods=["POST"])
def update_ambulance_status():
    """Toggle ambulance status (available ↔ on-duty), skip if assigned (locked)."""
    if "email" not in session:
        return jsonify({"success": False, "message": "Not logged in"}), 403

    data = request.get_json()
    amb_id = data.get("ambulance_id")
    new_status = data.get("status")

    if not amb_id or not new_status:
        return jsonify({"success": False, "message": "Invalid data"}), 400

    try:
        # ✅ Ensure correct type conversion for ObjectId
        try:
            amb_obj_id = ObjectId(amb_id)
        except Exception:
            return jsonify({"success": False, "message": "Invalid ambulance ID format"}), 400

        ambulance = ambulances_collection.find_one({"_id": amb_obj_id})
        if not ambulance:
            return jsonify({"success": False, "message": "Ambulance not found"}), 404

        # 🚫 If ambulance is assigned to a case → block manual status change
        if ambulance.get("current_incident_id"):
            return jsonify({
                "success": False,
                "message": "Ambulance is assigned to a case and cannot be manually updated."
            })

        # ✅ Toggle logic
        update_data = {"status": new_status}
        if new_status == "available":
            update_data["current_incident_id"] = None

        ambulances_collection.update_one(
            {"_id": amb_obj_id},
            {"$set": update_data}
        )

        print(f"✅ Ambulance {amb_id} updated to {new_status}")
        return jsonify({
            "success": True,
            "message": f"Ambulance marked as {new_status.capitalize()} successfully!"
        })

    except Exception as e:
        print("❌ update_ambulance_status error:", e)
        return jsonify({"success": False, "message": "Server error"}), 500

# -----------------------------
# ASSIGN AMBULANCE TO A CASE
# -----------------------------
@app.route("/assign_ambulance", methods=["POST"])
def assign_ambulance():
    if "email" not in session:
        return jsonify({"success": False, "message": "Not logged in"}), 403

    data = request.get_json()
    incident_id = data.get("incident_id")
    ambulance_id = data.get("ambulance_id")
    hospital_name = session.get("hospital_name")

    if not incident_id or not ambulance_id:
        return jsonify({"success": False, "message": "Missing incident_id or ambulance_id"}), 400

    try:
        # 1️⃣ Check if the incident is already accepted by another hospital
        existing_accept = case_status_collection.find_one({"incident_id": incident_id, "status": "accepted"})
        if existing_accept:
            return jsonify({"success": False, "message": "Case already accepted by another hospital"}), 409

        # 2️⃣ Mark case as accepted and link ambulance
        case_status_collection.update_one(
            {"incident_id": incident_id},
            {"$set": {
                "status": "accepted",
                "hospital_name": hospital_name,
                "ambulance_id": ambulance_id,
                "assigned_at": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
            }},
            upsert=True
        )

        # 3️⃣ Update ambulance record → mark as on-duty AND link to the incident
        ambulances_collection.update_one(
            {"_id": ObjectId(ambulance_id)},
            {"$set": {
                "status": "on-duty",
                "current_incident_id": incident_id  # ✅ store which incident it handles
            }}
        )

        return jsonify({"success": True, "message": "Ambulance assigned and incident linked successfully!"})

    except Exception as e:
        print("❌ assign_ambulance error:", e)
        return jsonify({"success": False, "message": "Server error while assigning ambulance"}), 500

# -----------------------------
# DELETE CASE STATUS (Revert Decision)
# -----------------------------
@app.route("/delete_case_status", methods=["POST"])
def delete_case_status():
    """Allow hospital to revert (delete) their case decision."""
    if "email" not in session:
        return jsonify({"success": False, "message": "Not logged in"}), 403

    data = request.get_json()
    incident_id = data.get("incident_id")
    hospital_name = session.get("hospital_name")

    if not incident_id:
        return jsonify({"success": False, "message": "Missing incident_id"}), 400

    try:
        # 🧹 Remove only this hospital's decision
        result = case_status_collection.delete_one({
            "incident_id": incident_id,
            "hospital_name": hospital_name
        })

        if result.deleted_count == 0:
            return jsonify({"success": False, "message": "No case decision found to delete"}), 404

        # 🩺 Also release any ambulance linked to this case
        linked_ambulance = ambulances_collection.find_one({"current_incident_id": incident_id})
        if linked_ambulance:
            ambulances_collection.update_one(
                {"_id": linked_ambulance["_id"]},
                {"$set": {"status": "available", "current_incident_id": None}}
            )

        return jsonify({"success": True, "message": "Case decision removed successfully"})


    except Exception as e:
        print("❌ delete_case_status error:", e)
        return jsonify({"success": False, "message": "Server error while deleting case status"}), 500


# -----------------------------
# DELETE INCIDENT (CLEAR CASE)
# -----------------------------
@app.route("/delete_incident", methods=["POST"])
def delete_incident():
    """Completely delete an incident and related data, and free any linked ambulance. Store it as resolved."""
    if "email" not in session:
        return jsonify({"success": False, "message": "Not logged in"}), 403

    data = request.get_json()
    incident_id = data.get("incident_id")
    hospital_name = session.get("hospital_name")

    if not incident_id:
        return jsonify({"success": False, "message": "Missing incident_id"}), 400

    try:
        # 🩺 1️⃣ Get the incident before deleting
        incident = incidents_collection.find_one({"_id": ObjectId(incident_id)})
        if not incident:
            return jsonify({"success": False, "message": "Incident not found"}), 404

        # 🚑 2️⃣ Get linked ambulance (if any)
        linked_ambulance = ambulances_collection.find_one({"current_incident_id": incident_id})
        ambulance_id = str(linked_ambulance["_id"]) if linked_ambulance else None
        driver_name = linked_ambulance.get("driver_name") if linked_ambulance else None
        vehicle_number = linked_ambulance.get("vehicle_number") if linked_ambulance else None

        # ✅ 3️⃣ Insert into resolved_cases collection
        resolved_cases_collection.insert_one({
            "incident_id": str(incident["_id"]),
            "user_email": incident.get("user_email", "Unknown"),
            "hospital_name": hospital_name,
            "ambulance_id": ambulance_id,
            "driver_name": driver_name,
            "vehicle_number": vehicle_number,
            "resolved_at": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        })

        # 🗑️ 4️⃣ Delete from incidents & case_status
        incidents_collection.delete_one({"_id": ObjectId(incident_id)})
        case_status_collection.delete_many({"incident_id": incident_id})

        # 🚐 5️⃣ Release ambulance if linked
        if linked_ambulance:
            ambulances_collection.update_one(
                {"_id": linked_ambulance["_id"]},
                {"$set": {"status": "available", "current_incident_id": None}}
            )

        print(f"✅ Case {incident_id} marked as resolved and removed.")
        return jsonify({"success": True, "message": "Case cleared and marked as resolved."})

    except Exception as e:
        print("❌ delete_incident error:", e)
        return jsonify({"success": False, "message": "Server error while deleting incident"}), 500


# -----------------------------
# LOGIN
# -----------------------------
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form["email"].strip().lower()
        password = request.form["password"]

        user = hospital_users.find_one({"email": email})
        if user and check_password_hash(user["password"], password):
            session["hospital_name"] = user["hospital_name"]
            session["email"] = user["email"]
            session["phone"] = user.get("phone", "")
            session["location"] = user.get("location", "")
            return redirect(url_for("dashboard"))
        else:
            return render_template("login.html", error="Invalid email or password")

    return render_template("login.html")


# -----------------------------
# REGISTER
# -----------------------------
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        hospital_name = request.form["hospital_name"].strip()
        email = request.form["email"].strip().lower()
        phone = request.form["phone"].strip()
        location = request.form["location"].strip()
        password = request.form["password"]
        confirm_password = request.form["confirm_password"]

        if not re.match(r"[^@]+@[^@]+\.[^@]+", email):
            return render_template("register.html", error="Invalid email format")
        if password != confirm_password:
            return render_template("register.html", error="Passwords do not match")
        if hospital_users.find_one({"email": email}):
            return render_template("register.html", error="Email already registered")

        hashed_pw = generate_password_hash(password)

        hospital_users.insert_one({
            "hospital_name": hospital_name,
            "email": email,
            "phone": phone,
            "location": location,
            "password": hashed_pw
        })

        return render_template("login.html", success="Registration successful! Please login.")

    return render_template("register.html")


# -----------------------------
# LOGOUT
# -----------------------------
@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# -----------------------------
# UPDATE PROFILE (AJAX)
# -----------------------------
@app.route("/update_profile", methods=["POST"])
def update_profile():
    if "email" not in session:
        return jsonify({"success": False, "message": "Not logged in"}), 403

    email = session["email"]
    updated_data = {
        "hospital_name": request.form.get("hospital_name"),
        "phone": request.form.get("phone"),
        "location": request.form.get("location"),
    }

    try:
        hospital_users.update_one({"email": email}, {"$set": updated_data})
        session["hospital_name"] = updated_data["hospital_name"]
        session["phone"] = updated_data["phone"]
        session["location"] = updated_data["location"]

        return jsonify({"success": True, "message": "Profile updated successfully!"})
    except Exception as e:
        print("❌ Profile update error:", e)
        return jsonify({"success": False, "message": "Error updating profile"}), 500


def get_karnataka_hospital_database():
    """Comprehensive Karnataka hospitals including Davanagere that OSM might miss"""
    return [
        # Critical hospitals that OSM often misses
        {"name": "Manipal Hospital", "location": "Bangalore, Karnataka", "city": "Bangalore", "state": "Karnataka",
         "type": "private"},
        {"name": "Apollo Hospitals", "location": "Bangalore, Karnataka", "city": "Bangalore", "state": "Karnataka",
         "type": "private"},
        {"name": "Fortis Hospital", "location": "Bangalore, Karnataka", "city": "Bangalore", "state": "Karnataka",
         "type": "private"},
        {"name": "Narayana Health", "location": "Bangalore, Karnataka", "city": "Bangalore", "state": "Karnataka",
         "type": "private"},
        {"name": "Columbia Asia Hospital", "location": "Bangalore, Karnataka", "city": "Bangalore",
         "state": "Karnataka", "type": "private"},

        # Government hospitals
        {"name": "Victoria Hospital", "location": "Bangalore, Karnataka", "city": "Bangalore", "state": "Karnataka",
         "type": "government"},
        {"name": "Bowring Hospital", "location": "Bangalore, Karnataka", "city": "Bangalore", "state": "Karnataka",
         "type": "government"},
        {"name": "Bangalore Medical College", "location": "Bangalore, Karnataka", "city": "Bangalore",
         "state": "Karnataka", "type": "government"},

        # Major cities across Karnataka
        {"name": "Apollo Hospital Mysore", "location": "Mysore, Karnataka", "city": "Mysore", "state": "Karnataka",
         "type": "private"},
        {"name": "JSS Hospital", "location": "Mysore, Karnataka", "city": "Mysore", "state": "Karnataka",
         "type": "private"},
        {"name": "KLE Hospital", "location": "Hubli, Karnataka", "city": "Hubli", "state": "Karnataka",
         "type": "private"},
        {"name": "KMC Hospital", "location": "Mangalore, Karnataka", "city": "Mangalore", "state": "Karnataka",
         "type": "private"},
        {"name": "AJ Hospital", "location": "Mangalore, Karnataka", "city": "Mangalore", "state": "Karnataka",
         "type": "private"},

        # DAVANAGERE HOSPITALS - Added as requested
        {"name": "JJM Medical College Hospital", "location": "Davanagere, Karnataka", "city": "Davanagere",
         "state": "Karnataka", "type": "private"},
        {"name": "Chigateri General Hospital", "location": "Davanagere, Karnataka", "city": "Davanagere",
         "state": "Karnataka", "type": "government"},
        {"name": "Bapuji Hospital", "location": "Davanagere, Karnataka", "city": "Davanagere", "state": "Karnataka",
         "type": "private"},
        {"name": "SS Institute of Medical Sciences", "location": "Davanagere, Karnataka", "city": "Davanagere",
         "state": "Karnataka", "type": "private"},
        {"name": "District Hospital Davanagere", "location": "Davanagere, Karnataka", "city": "Davanagere",
         "state": "Karnataka", "type": "government"},
        {"name": "Sri Siddhartha Medical College", "location": "Davanagere, Karnataka", "city": "Davanagere",
         "state": "Karnataka", "type": "private"},
        {"name": "Ashoka Hospital", "location": "Davanagere, Karnataka", "city": "Davanagere", "state": "Karnataka",
         "type": "private"},
        {"name": "Kiran Hospital", "location": "Davanagere, Karnataka", "city": "Davanagere", "state": "Karnataka",
         "type": "private"},
        {"name": "Sagar Hospitals", "location": "Davanagere, Karnataka", "city": "Davanagere", "state": "Karnataka",
         "type": "private"},
        {"name": "Manjunatha Hospital", "location": "Davanagere, Karnataka", "city": "Davanagere", "state": "Karnataka",
         "type": "private"},

        # Specialized institutes
        {"name": "NIMHANS", "location": "Bangalore, Karnataka", "city": "Bangalore", "state": "Karnataka",
         "type": "government"},
        {"name": "Kidwai Memorial Institute", "location": "Bangalore, Karnataka", "city": "Bangalore",
         "state": "Karnataka", "type": "government"},
        {"name": "Jayadeva Institute", "location": "Bangalore, Karnataka", "city": "Bangalore", "state": "Karnataka",
         "type": "government"},

        # Popular chains in Karnataka
        {"name": "Sakra World Hospital", "location": "Bangalore, Karnataka", "city": "Bangalore", "state": "Karnataka",
         "type": "private"},
        {"name": "BGS Global Hospital", "location": "Bangalore, Karnataka", "city": "Bangalore", "state": "Karnataka",
         "type": "private"},
        {"name": "MS Ramaiah Hospital", "location": "Bangalore, Karnataka", "city": "Bangalore", "state": "Karnataka",
         "type": "private"},

        # More Bangalore hospitals
        {"name": "St. John's Medical College Hospital", "location": "Bangalore, Karnataka", "city": "Bangalore",
         "state": "Karnataka", "type": "private"},
        {"name": "Vydehi Hospital", "location": "Whitefield, Bangalore", "city": "Bangalore", "state": "Karnataka",
         "type": "private"},
        {"name": "People Tree Hospitals", "location": "Bangalore, Karnataka", "city": "Bangalore", "state": "Karnataka",
         "type": "private"},

        # More major Karnataka cities
        {"name": "District Hospital", "location": "Shimoga, Karnataka", "city": "Shimoga", "state": "Karnataka",
         "type": "government"},
        {"name": "McGann Hospital", "location": "Shimoga, Karnataka", "city": "Shimoga", "state": "Karnataka",
         "type": "government"},
        {"name": "District Hospital", "location": "Bellary, Karnataka", "city": "Bellary", "state": "Karnataka",
         "type": "government"},
        {"name": "District Hospital", "location": "Belgaum, Karnataka", "city": "Belgaum", "state": "Karnataka",
         "type": "government"},
        {"name": "District Hospital", "location": "Gulbarga, Karnataka", "city": "Gulbarga", "state": "Karnataka",
         "type": "government"},
    ]


def search_hospitals_hybrid(query, limit=10):
    """
    Hybrid search: OpenStreetMap (primary) + Karnataka Local DB (fallback)
    Returns combined results with source information
    """
    all_hospitals = []

    try:
        # 1. First try OpenStreetMap API (real-time data)
        osm_hospitals = search_hospitals_nominatim(query, limit=limit)
        all_hospitals.extend(osm_hospitals)

        print(f"🔍 OSM found {len(osm_hospitals)} hospitals for query: '{query}'")

        # 2. If OSM returns few results, add local Karnataka hospitals
        if len(all_hospitals) < 5:
            local_hospitals = search_karnataka_hospitals_local(query, limit - len(all_hospitals))

            # Avoid duplicates
            existing_names = {h['name'].lower() for h in all_hospitals}
            for hospital in local_hospitals:
                if hospital['name'].lower() not in existing_names:
                    all_hospitals.append({
                        'name': hospital['name'],
                        'location': hospital['location'],
                        'type': 'karnataka'  # Mark as from local Karnataka DB
                    })
                    existing_names.add(hospital['name'].lower())

            print(f"🏥 Local DB added {len(local_hospitals)} Karnataka hospitals")

        # 3. Remove duplicates and limit results
        unique_hospitals = []
        seen_names = set()
        for hospital in all_hospitals:
            if hospital['name'] not in seen_names:
                unique_hospitals.append(hospital)
                seen_names.add(hospital['name'])

        return unique_hospitals[:limit]

    except Exception as e:
        print(f"❌ Hybrid search error: {e}")
        # Fallback to local only
        return search_karnataka_hospitals_local(query, limit)


def search_karnataka_hospitals_local(query, limit=8):
    """Fast local search in Karnataka hospitals database"""
    if not query or len(query) < 2:
        return []

    query = query.lower()
    hospitals = get_karnataka_hospital_database()

    # Smart matching - prioritize exact matches
    exact_matches = []
    partial_matches = []

    for hospital in hospitals:
        name_lower = hospital['name'].lower()
        location_lower = hospital['location'].lower()
        city_lower = hospital['city'].lower()

        # Exact name match (highest priority)
        if query in name_lower:
            if name_lower.startswith(query):
                exact_matches.insert(0, hospital)  # Beginning matches first
            else:
                exact_matches.append(hospital)
        # Location or city match
        elif query in location_lower or query in city_lower:
            partial_matches.append(hospital)

    return (exact_matches + partial_matches)[:limit]


def search_hospitals_nominatim(query, country="India", limit=8):
    """
    Improved OpenStreetMap search with better hospital detection for Karnataka
    """
    try:
        headers = {'User-Agent': USER_AGENT}

        # Smarter search query focused on Karnataka
        params = {
            'q': f'{query} hospital Karnataka',
            'format': 'json',
            'limit': limit,
            'addressdetails': 1,
            'countrycodes': 'in'
        }

        response = requests.get(NOMINATIM_API_URL, params=params, headers=headers, timeout=8)

        if response.status_code == 200:
            results = response.json()
            hospitals = []

            for result in results:
                hospital_name = extract_hospital_name_improved(result)
                if hospital_name:  # Only include if we found a proper hospital name
                    hospitals.append({
                        'name': hospital_name,
                        'location': extract_location(result),
                        'type': 'osm',
                        'lat': result.get('lat'),
                        'lon': result.get('lon')
                    })

            return hospitals
        return []

    except Exception as e:
        print(f"❌ OSM search error: {e}")
        return []


def extract_hospital_name_improved(result):
    """Better hospital name extraction from OSM"""
    address = result.get('address', {})
    display_name = result.get('display_name', '')

    # Priority order for hospital names
    if address.get('hospital'):
        return address['hospital']
    elif address.get('name'):
        name = address['name']
        # Check if it's actually a hospital
        hospital_keywords = ['hospital', 'medical', 'clinic', 'health', 'care', 'nursing']
        if any(keyword in name.lower() for keyword in hospital_keywords):
            return name
    elif 'hospital' in display_name.lower():
        # Extract hospital name from display name
        parts = display_name.split(',')
        for part in parts:
            part = part.strip()
            hospital_keywords = ['hospital', 'medical', 'clinic']
            if any(keyword in part.lower() for keyword in hospital_keywords):
                return part

    return None


def extract_location(result):
    """Extract location from Nominatim result"""
    address = result.get('address', {})
    location_parts = []

    # Build location string from address components
    if address.get('city'):
        location_parts.append(address['city'])
    elif address.get('town'):
        location_parts.append(address['town'])
    elif address.get('village'):
        location_parts.append(address['village'])

    if address.get('state'):
        location_parts.append(address['state'])

    if address.get('country'):
        location_parts.append(address['country'])

    return ', '.join(location_parts) if location_parts else result.get('display_name', '')


def init_karnataka_hospital_cache():
    """Initialize Karnataka hospital cache"""
    try:
        if hospitals_collection.count_documents({}) == 0:
            karnataka_hospitals = get_karnataka_hospital_database()
            hospitals_collection.insert_many(karnataka_hospitals)
            print("✅ Karnataka hospital cache initialized with 35+ hospitals including Davanagere")
        else:
            print("✅ Hospital cache already exists")
    except Exception as e:
        print(f"❌ Error initializing hospital cache: {e}")


# -----------------------------
# REAL-TIME HOSPITAL SEARCH API
# -----------------------------
@app.route("/api/hospitals/search", methods=["GET"])
def search_hospitals_api():
    """
    Hybrid hospital search: OSM + Karnataka Local DB
    """
    query = request.args.get('q', '').strip()
    limit = int(request.args.get('limit', 8))

    if not query or len(query) < 2:
        return jsonify({'hospitals': []})

    try:
        all_hospitals = []

        # 1. Search in already registered hospitals
        registered_hospitals = hospital_users.find({
            "$or": [
                {"hospital_name": {"$regex": query, "$options": "i"}},
                {"location": {"$regex": query, "$options": "i"}}
            ]
        }).limit(2)

        for hospital in registered_hospitals:
            all_hospitals.append({
                'name': hospital['hospital_name'],
                'location': hospital.get('location', ''),
                'type': 'registered'
            })

        # 2. Hybrid search (OSM + Local Karnataka)
        if len(all_hospitals) < limit:
            hybrid_results = search_hospitals_hybrid(query, limit - len(all_hospitals))

            # Avoid duplicates
            existing_names = {h['name'].lower() for h in all_hospitals}
            for hospital in hybrid_results:
                if hospital['name'].lower() not in existing_names:
                    all_hospitals.append(hospital)

        print(
            f"🎯 Total results: {len(all_hospitals)} (Registered: {len([h for h in all_hospitals if h.get('type') == 'registered'])}, OSM: {len([h for h in all_hospitals if h.get('type') == 'osm'])}, Karnataka: {len([h for h in all_hospitals if h.get('type') == 'karnataka'])})")

        return jsonify({'hospitals': all_hospitals[:limit]})

    except Exception as e:
        print(f"❌ Hospital search error: {e}")
        # Ultimate fallback - local Karnataka only
        local_results = search_karnataka_hospitals_local(query, limit)
        return jsonify({'hospitals': local_results})


if __name__ == "__main__":
    app.run(debug=True)