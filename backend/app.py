from flask import Flask, request, jsonify, send_from_directory
import os
import sqlite3
import hashlib
import urllib.request
import re

app = Flask(__name__, static_folder="../frontend", static_url_path="")
UPLOAD_FOLDER = "./static/uploads"
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
ALLOWED_EXTENSIONS = {'pdf', 'jpg', 'jpeg', 'png', 'mp3', 'xlsx', 'xls', 'txt'}

# Database initialization
DB_PATH = "files.db"

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Initialize the SQLite database."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS files (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        file_name TEXT UNIQUE,
        file_path TEXT,
        file_hash TEXT UNIQUE,
        uploaded_by TEXT,
        url TEXT
    )
    """)
    
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS downloads (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        file_name TEXT,
        user_id TEXT,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (file_name) REFERENCES files(file_name)
    )
    """)
    
    conn.commit()
    conn.close()

def calculate_file_hash(file_path):
    """Calculate SHA256 hash of the file."""
    hash_sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_sha256.update(chunk)
    return hash_sha256.hexdigest()

def check_duplicate(file_hash):
    """Check if a file with the same hash exists."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM files WHERE file_hash = ?", (file_hash,))
    duplicate = cursor.fetchone()
    conn.close()
    return duplicate

def add_file_to_db(file_name, file_path, file_hash, user_id, url=None):
    """Insert file metadata into the database."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO files (file_name, file_path, file_hash, uploaded_by, url) 
        VALUES (?, ?, ?, ?, ?)""",
        (file_name, file_path, file_hash, user_id, url)
    )
    conn.commit()
    conn.close()

def log_download(file_name, user_id):
    """Log user downloads."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO downloads (file_name, user_id) VALUES (?, ?)", (file_name, user_id))
    conn.commit()
    conn.close()

@app.route("/") 
def serve_frontend():
    return send_from_directory("../frontend", "index.html")

@app.route("/upload", methods=["POST"]) 
def upload_file():
    file = request.files.get("file")
    user_id = request.form.get("user_id")

    if not file or not user_id:
        return jsonify({"error": "File and user ID are required"}), 400

    file_path = os.path.join(UPLOAD_FOLDER, file.filename)
    file.save(file_path)

    file_hash = calculate_file_hash(file_path)

    # Check for duplicate
    duplicate = check_duplicate(file_hash)
    if duplicate:
        return jsonify({
            "message": "Duplicate file detected",
            "uploaded_by": duplicate["uploaded_by"]
        }), 409

    # Save file details to DB
    add_file_to_db(file.filename, file_path, file_hash, user_id)
    return jsonify({"message": "File uploaded successfully"})

@app.route("/download_by_name", methods=["POST"])
def download_by_name():
    file_name = request.json.get("file_name")
    user_id = request.json.get("user_id")

    if not file_name or not user_id:
        return jsonify({"error": "File name and user ID are required"}), 400

    # Retrieve file details from the database
    db = get_database()
    file_entry = db["files"].find_one({"file_name": file_name})

    if not file_entry:
        return jsonify({"error": "File not found"}), 404

    # Use file hash to detect if the user has already downloaded the file
    user_download_entry = db["downloads"].find_one({"file_name": file_name, "user_id": user_id})

    if user_download_entry:
        return jsonify({
            "message": "Duplicate file detected",
            "uploaded_by": file_entry.get("uploaded_by", "Unknown"),
            "users": list(db["downloads"].find({"file_name": file_name}, {"user_id": 1, "timestamp": 1, "_id": 0}))
        }), 200

    # Log the download for this user
    log_download(file_name, user_id)

    # Return the file as a downloadable response
    return send_from_directory(
        directory=os.path.dirname(file_entry["file_path"]),
        path=os.path.basename(file_entry["file_path"]),
        as_attachment=True
    )


@app.route("/download_from_url", methods=["POST"])
def download_from_url():
    data = request.json
    file_url = data.get("file_url")
    user_id = data.get("user_id")

    if not file_url or not user_id:
        return jsonify({"error": "Missing file URL or user ID"}), 400

    try:
        # Handle Google Drive links
        if "drive.google.com" in file_url:
            match = re.search(r"/file/d/([^/]+)/", file_url)
            if match:
                file_id = match.group(1)
                file_url = f"https://drive.google.com/uc?export=download&id={file_id}"

        # Fetch file with headers
        def fetch_file_with_headers(file_url):
            headers = {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
                )
            }
            request = urllib.request.Request(file_url, headers=headers)
            response = urllib.request.urlopen(request)
            return response

        temp_path = os.path.join(app.config["UPLOAD_FOLDER"], "temp_download")
        with fetch_file_with_headers(file_url) as response, open(temp_path, 'wb') as temp_file:
            temp_file.write(response.read())

        # Compute file hash
        file_hash = calculate_file_hash(temp_path)

        # Check for duplicates
        duplicate = check_duplicate(file_hash=file_hash, url=file_url)

        if duplicate:
            os.remove(temp_path)  # Clean up temporary file if duplicate detected
            return jsonify({
                "message": "Duplicate file detected",
                "existing_file": duplicate["file_name"],
                "location": duplicate["file_path"],
                "metadata": duplicate["metadata"],
                "users": duplicate["users"]  # Return user info
            }), 200

        # No duplicate: move the temp file to its final location
        unique_filename = generate_unique_filename(file_url, file_hash)
        file_path = os.path.join(app.config["UPLOAD_FOLDER"], unique_filename)
        os.rename(temp_path, file_path)

        # Add the file to the database
        add_file_to_db(
            unique_filename, file_path, file_hash,
            description=f"Downloaded from {file_url}", url=file_url, user_id=user_id
        )

        # Log the current user's download
        log_download(unique_filename, user_id)

        return jsonify({"message": "File downloaded and processed successfully"}), 200

    except urllib.error.HTTPError as e:
        return jsonify({"error": f"HTTP error occurred: {e.code} {e.reason}"}), e.code
    except urllib.error.URLError as e:
        return jsonify({"error": f"URL error occurred: {e.reason}"}), 400
    except Exception as e:
        return jsonify({"error": f"An unexpected error occurred: {str(e)}"}), 500

@app.route("/get_files", methods=["GET"])
def get_files():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT file_name, file_path, uploaded_by FROM files")
    files = cursor.fetchall()
    conn.close()

    files_list = [{"file_name": file["file_name"], "file_path": file["file_path"], "uploaded_by": file["uploaded_by"]} for file in files]
    return jsonify({"files": files_list})

if __name__ == "__main__":
    if not os.path.exists(UPLOAD_FOLDER):
        os.makedirs(UPLOAD_FOLDER)
    init_db()
    app.run(host="0.0.0.0", port=5000, debug=True)
