import hashlib
import os
from datetime import datetime
from database import get_database
import urllib.parse
import re


def calculate_file_hash(file_path):
    """Generate a unique hash (SHA-256) for a file."""
    sha256_hash = hashlib.sha256()
    with open(file_path, "rb") as f:
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()


def check_duplicate(file_hash=None, url=None):
    """
    Check for duplicates in the database using the file hash or URL.
    Args:
        file_hash (str): The hash of the file to check for duplicates (used in uploads and downloads by name).
        url (str): The URL of the file to check for duplicates (used in downloads from URL).
    Returns:
        dict: Details of the duplicate file or None if no duplicate is found.
    """
    db = get_database()
    collection = db["files"]

    # Check by file hash (used for uploads and downloads by name)
    if file_hash:
        duplicate_entry = collection.find_one({"file_hash": file_hash})
        if duplicate_entry:
            # Fetch all users who downloaded the file
            downloads = db["downloads"].find({"file_hash": file_hash})
            users = [
                {"user_id": log.get("user_id"), "timestamp": log.get("timestamp").isoformat()}
                for log in downloads
            ]
            return {
                "file_name": duplicate_entry["file_name"],
                "file_path": duplicate_entry["file_path"],
                "metadata": duplicate_entry.get("metadata"),
                "source_url": duplicate_entry.get("url"),
                "uploaded_by": duplicate_entry.get("uploaded_by", "Unknown"),
                "users": users  # Include users who downloaded the file
            }

    # Check by file URL (used for downloads from URL)
    if url:
        duplicate_entry = collection.find_one({"url": url})
        if duplicate_entry:
            # Fetch all users who downloaded the file
            downloads = db["downloads"].find({"file_name": duplicate_entry["file_name"]})
            users = [
                {"user_id": log.get("user_id"), "timestamp": log.get("timestamp").isoformat()}
                for log in downloads
            ]
            return {
                "file_name": duplicate_entry["file_name"],
                "file_path": duplicate_entry["file_path"],
                "metadata": duplicate_entry.get("metadata"),
                "source_url": duplicate_entry["url"],
                "uploaded_by": duplicate_entry.get("uploaded_by", "Unknown"),
                "users": users  # Add users who downloaded the file
            }
    return None



def add_file_to_db(file_name, file_path, file_hash, description=None, url=None, user_id=None):
    """
    Adds a file record to the database.
    Args:
        file_name (str): The name of the file.
        file_path (str): The path to the file.
        file_hash (str): The hash of the file.
        description (str): A description or additional metadata for the file.
        url (str): The source URL of the file (if applicable).
        user_id (str): The user ID of the uploader (if applicable).
    """
    db = get_database()
    file_record = {
        "file_name": file_name,
        "file_path": file_path,
        "file_hash": file_hash,
        "description": description,
        "url": url,
        "uploaded_by": user_id  # Add the uploader's user ID here
    }
    db["files"].insert_one(file_record)


def log_download(file_name, user_id):
    """
    Log the download request with user details.
    """
    db = get_database()
    db["downloads"].insert_one({
        "file_name": file_name,
        "user_id": user_id,
        "timestamp": datetime.utcnow(),
    })


def sanitize_filename(filename):
    """
    Replace any invalid characters in the filename with an underscore.
    """
    return re.sub(r'[<>:"/\\|?*]', '_', filename)


def generate_unique_filename(file_url, file_hash):
    """
    Generate a unique filename based on the file URL and hash.
    Args:
        file_url (str): The URL of the file being downloaded.
        file_hash (str): The hash of the file.
    Returns:
        str: A unique filename.
    """
    parsed_url = urllib.parse.urlparse(file_url)
    base_name = os.path.basename(parsed_url.path) or "downloaded_file"
    sanitized_name = sanitize_filename(base_name)
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    unique_name = f"{sanitized_name}_{file_hash[:8]}_{timestamp}"
    return unique_name
