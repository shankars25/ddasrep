from pymongo import MongoClient
import os

MONGO_URI = os.getenv("MONGO_URI", "mongodb+srv://sutarshankar420:Admin@clusterddas.2r0vh.mongodb.net/")

client = MongoClient(MONGO_URI)
db = client["yourdb"]
collection = db["your_collection"]

def get_database():
    # Replace with your MongoDB connection URI
    client = MongoClient("mongodb://localhost:27017")
    db = client["ddas1"]
    return db




