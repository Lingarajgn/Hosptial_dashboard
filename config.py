import os

# MongoDB connection string (direct variable)
MONGO_URI = os.getenv(
    "MONGO_URI",
    "mongodb+srv://bajarangiboys7:SwiftAid%402025@swiftaid.3cg4vht.mongodb.net/SwiftAid"
)

# Flask secret key
SECRET_KEY = os.getenv("SECRET_KEY", "supersecretkey")