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
    conn = sqlite3.connect(DB_PATH, timeout=10, check_same_thread=False)  # 10 seconds timeout
    conn.row_factory = sqlite3.Row
    return conn



def init_db():
    """Initialize the SQLite database."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("PRAGMA journal_mode=WAL;")  # Enable WAL mode
    
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
    conn.close()  # Ensure the connection is closed


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

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM files WHERE file_name = ?", (file_name,))
    file_entry = cursor.fetchone()
    conn.close()

    if not file_entry:
        return jsonify({"error": "File not found"}), 404

    log_download(file_name, user_id)

    return send_from_directory(directory=os.path.dirname(file_entry["file_path"]), 
                               path=os.path.basename(file_entry["file_path"]), 
                               as_attachment=True)

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
