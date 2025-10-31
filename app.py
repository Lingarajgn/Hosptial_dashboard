from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from pymongo import MongoClient
from bson import ObjectId
from werkzeug.security import generate_password_hash, check_password_hash
from config import MONGO_URI
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