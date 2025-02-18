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

// Download by Name Form
document.getElementById("downloadNameForm").addEventListener("submit", async (e) => {
    e.preventDefault();
    const fileName = document.getElementById("fileName").value;
    const userId = document.getElementById("userIdName").value;

    if (!fileName || !userId) {
        alert("Please provide both the file name and your user ID.");
        return;
    }

    try {
        const response = await fetch("/download_by_name", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ file_name: fileName, user_id: userId }),
        });

        if (response.status === 200) {
            const contentDisposition = response.headers.get("Content-Disposition");

            if (contentDisposition && contentDisposition.includes("attachment")) {
                const blob = await response.blob();
                const url = window.URL.createObjectURL(blob);
                const a = document.createElement("a");
                a.href = url;
                a.download = fileName;
                document.body.appendChild(a);
                a.click();
                a.remove();
                window.URL.revokeObjectURL(url);
                alert("File downloaded successfully!");
            } else {
                const result = await response.json();
                document.getElementById("downloadNameResponse").textContent = JSON.stringify(result, null, 2);
            }
        } else {
            const result = await response.json();
            alert(result.error || "An error occurred while downloading the file.");
        }
    } catch (error) {
        console.error("Error:", error);
        alert("An error occurred while processing your request.");
    }
});

// Handle downloading from URL
document.getElementById("downloadUrlForm").addEventListener("submit", async (e) => {
    e.preventDefault();
    const fileUrl = document.getElementById("fileUrl").value;
    const userId = document.getElementById("userIdUrl").value;

    if (!fileUrl || !userId) {
        alert("Please provide both the file URL and your user ID.");
        return;
    }

    try {
        const response = await fetch("/download_from_url", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ file_url: fileUrl, user_id: userId }),
        });

        const result = await response.json();

        // Exclude the "users" field from the alert
        const { users, ...filteredResult } = result;

        // Display the filtered result (excluding 'users')
        document.getElementById("downloadUrlResponse").textContent = JSON.stringify(filteredResult, null, 2);
    } catch (error) {
        console.error("Error:", error);
        alert("An error occurred while processing your request.");
    }
});

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
