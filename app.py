from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from pymongo import MongoClient
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

    try:
        # Fetch incidents from MongoDB
        incidents = list(incidents_collection.find())
        for inc in incidents:
            inc["_id"] = str(inc["_id"])
            inc["lat"] = inc.get("lat", 14.4663)
            inc["lng"] = inc.get("lng", 75.9219)
            inc["user_email"] = inc.get("user_email", "Unknown")
            inc["speed"] = inc.get("speed", 0)
            inc["accel_mag"] = inc.get("accel_mag", 0)
            inc["created_at"] = inc.get("metadata", {}).get("created_at", "N/A")

        active_cases = len(incidents)   # Assuming all fetched = active
        resolved_cases = 0  # If you have a "status" field, you can count based on it

    except Exception as e:
        print("❌ Error fetching incidents:", e)
        incidents, active_cases, resolved_cases = [], 0, 0

    return render_template(
        "dashboard.html",
        active_cases=active_cases,
        resolved_cases=resolved_cases,
        incidents=incidents,
        hospital_name=session.get("hospital_name", "Unknown Hospital"),
        user=user
    )



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
