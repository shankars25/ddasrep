from pymongo import MongoClient

def get_database():
    # Replace with your MongoDB connection URI
    client = MongoClient("mongodb://localhost:27017")
    db = client["ddas1"]
    return db
