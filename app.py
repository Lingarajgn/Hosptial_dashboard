from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from pymongo import MongoClient
from bson import ObjectId
from werkzeug.security import generate_password_hash, check_password_hash
from config import MONGO_URI
from datetime import datetime
import re

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
        # 🟢 1️⃣ Fetch data from MongoDB
        incidents = list(incidents_collection.find())
        all_statuses = list(case_status_collection.find())

        # 🟢 2️⃣ Convert ObjectIds to strings (ADD THIS PART HERE)
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

        # 🟢 3️⃣ Continue with the rest of your logic
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

    except Exception as e:
        print("❌ Error fetching incidents:", e)
        incidents, active_cases, accepted_cases = [], 0, 0

    return render_template(
        "dashboard.html",
        active_cases=active_cases,
        accepted_cases=accepted_cases,
        incidents=incidents,
        hospital_name=hospital_name,
        user=user
    )



# -----------------------------
# UPDATE CASE STATUS
# -----------------------------
@app.route("/update_case_status", methods=["POST"])
def update_case_status():
    if "email" not in session:
        return jsonify({"success": False, "message": "Not logged in"}), 403

    data = request.get_json()
    incident_id = data.get("incident_id")
    status = data.get("status")
    hospital_name = session.get("hospital_name")

    if not incident_id or not status:
        return jsonify({"success": False, "message": "Invalid data"}), 400

    # ✅ CASE ALREADY ACCEPTED BY ANY HOSPITAL
    existing_accept = case_status_collection.find_one({"incident_id": incident_id, "status": "accepted"})
    if existing_accept and status == "accepted":
        return jsonify({"success": False, "message": "Case already accepted by another hospital"}), 409

    if status == "accepted":
        # ✅ Only one hospital can accept
        case_status_collection.update_one(
            {"incident_id": incident_id},
            {"$set": {"status": "accepted", "hospital_name": hospital_name}},
            upsert=True
        )

    elif status == "rejected":
        # ✅ Each hospital can reject independently
        case_status_collection.update_one(
            {"incident_id": incident_id, "hospital_name": hospital_name},
            {"$set": {"status": "rejected"}},
            upsert=True
        )

    return jsonify({"success": True, "message": f"Case {status} successfully"})

# -----------------------------
# /case/<incident_id>
# -----------------------------
from bson import ObjectId

@app.route("/case/<incident_id>")
def case_detail(incident_id):
    if "email" not in session:
        return redirect(url_for("login"))

    hospital_name = session.get("hospital_name")

    try:
        # Find the incident by its ObjectId
        incident = incidents_collection.find_one({"_id": ObjectId(incident_id)})
        if not incident:
            return "Case not found", 404

        # Convert ObjectId to string
        incident["_id"] = str(incident["_id"])
        incident["lat"] = incident.get("lat", 14.4663)
        incident["lng"] = incident.get("lng", 75.9219)
        incident["user_email"] = incident.get("user_email", "Unknown")
        incident["speed"] = incident.get("speed", 0)
        incident["accel_mag"] = incident.get("accel_mag", 0)
        incident["created_at"] = incident.get("metadata", {}).get("created_at", "N/A")

        # Find case status (accepted/rejected)
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
# 🚑 AMBULANCE MANAGEMENT
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

        # 🧠 Automatically sync status
        if not current_incident or current_incident in ("", None):
            # No case → mark available
            if amb.get("status") != "available":
                ambulances_collection.update_one(
                    {"_id": amb_id},
                    {"$set": {"status": "available", "current_incident_id": None}}
                )
            amb["status"] = "available"
            amb["current_incident_id"] = None
        else:
            # Has assigned case → ensure on-duty
            if amb.get("status") != "on-duty":
                ambulances_collection.update_one(
                    {"_id": amb_id},
                    {"$set": {"status": "on-duty"}}
                )
            amb["status"] = "on-duty"

        amb["_id"] = str(amb["_id"])

    return jsonify({"success": True, "ambulances": ambs})




# -----------------------------
# ADD AMBULANCE
# -----------------------------

@app.route("/add_ambulance", methods=["POST"])
def add_ambulance():
    """Add a new ambulance record."""
    if "email" not in session:
        return jsonify({"success": False, "message": "Not logged in"}), 403

    data = request.get_json()
    vehicle_number = data.get("vehicle_number")
    driver_name = data.get("driver_name")
    phone = data.get("phone")
    hospital_name = session.get("hospital_name")

    if not vehicle_number or not driver_name:
        return jsonify({"success": False, "message": "Missing required fields"}), 400

    ambulances_collection.insert_one({
        "vehicle_number": vehicle_number,
        "driver_name": driver_name,
        "phone": phone,
        "status": "available",
        "hospital_name": hospital_name
    })
    return jsonify({"success": True, "message": "Ambulance added successfully"})


# -----------------------------
# UPDATE AMBULANCE STATUS
# -----------------------------

@app.route("/update_ambulance_status", methods=["POST"])
def update_ambulance_status():
    """Manually toggle ambulance status between available / on-duty and clear incident link if available."""
    if "email" not in session:
        return jsonify({"success": False, "message": "Not logged in"}), 403

    data = request.get_json()
    amb_id = data.get("ambulance_id")
    new_status = data.get("status")

    if not amb_id or not new_status:
        return jsonify({"success": False, "message": "Invalid data"}), 400

    try:
        update_data = {"status": new_status}

        # 🧹 If ambulance is now available, remove the linked incident
        if new_status == "available":
            update_data["current_incident_id"] = None

        ambulances_collection.update_one(
            {"_id": ObjectId(amb_id)},
            {"$set": update_data}
        )

        return jsonify({"success": True, "message": f"Ambulance marked as {new_status}"})

    except Exception as e:
        print("❌ Ambulance status update error:", e)
        return jsonify({"success": False, "message": "Error updating status"}), 500


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
    """Completely delete an incident and related data, and free any linked ambulance."""
    if "email" not in session:
        return jsonify({"success": False, "message": "Not logged in"}), 403

    data = request.get_json()
    incident_id = data.get("incident_id")

    if not incident_id:
        return jsonify({"success": False, "message": "Missing incident_id"}), 400

    try:
        # 🗑️ 1️⃣ Delete the incident itself
        result = incidents_collection.delete_one({"_id": ObjectId(incident_id)})

        # 🧹 2️⃣ Delete any related case status
        case_status_collection.delete_many({"incident_id": incident_id})

        # 🚑 3️⃣ Find and free any ambulances linked to this case
        linked_ambulances = list(ambulances_collection.find({"current_incident_id": incident_id}))
        if linked_ambulances:
            for amb in linked_ambulances:
                ambulances_collection.update_one(
                    {"_id": amb["_id"]},
                    {"$set": {"status": "available", "current_incident_id": None}}
                )
                print(f"🚐 Freed ambulance: {amb.get('vehicle_number', 'N/A')}")

        # ✅ 4️⃣ Handle case where incident wasn't found
        if result.deleted_count == 0:
            return jsonify({"success": False, "message": "Incident not found"}), 404

        print(f"✅ Incident {incident_id} and linked data removed successfully.")
        return jsonify({
            "success": True,
            "message": "Incident cleared successfully! Linked ambulance(s) released."
        })

    except Exception as e:
        print(f"❌ delete_incident error: {e}")
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


if __name__ == "__main__":
    app.run(debug=True)