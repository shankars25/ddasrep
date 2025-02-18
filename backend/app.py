from flask import Flask, request, jsonify, send_from_directory
from duplicate_check import calculate_file_hash, check_duplicate, add_file_to_db, log_download, sanitize_filename, generate_unique_filename
import os
import urllib.parse
from datetime import datetime
from urllib.request import urlopen
import re
from database import get_database
app = Flask(__name__, static_folder="../frontend", static_url_path="")
UPLOAD_FOLDER = "./static/uploads"
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
ALLOWED_EXTENSIONS = {'pdf', 'jpg', 'jpeg', 'png', 'mp3', 'xlsx', 'xls', 'txt'}


def allowed_file(filename):
    """Check if the uploaded file has an allowed extension."""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


@app.route("/") #for homepage
def serve_frontend():
    return send_from_directory("../frontend", "index.html")


@app.route("/<path:path>")#serving static files
def serve_static_files(path):
    return send_from_directory("../frontend", path)

@app.route("/upload", methods=["POST"])
def upload_file():
    file = request.files.get("file")
    user_id = request.form.get("user_id")  # Retrieve the user ID

    if not file or not user_id:
        return jsonify({"error": "File and user ID are required"}), 400

    file_path = os.path.join(UPLOAD_FOLDER, file.filename)
    file.save(file_path)

    # Calculate the file hash
    file_hash = calculate_file_hash(file_path)

    # Check for duplicates using file hash
    duplicate = check_duplicate(file_hash=file_hash)
    if duplicate:
        return jsonify({
            "message": "Duplicate file detected",
            "uploaded_by": duplicate.get("uploaded_by", "Unknown")  # Return uploader's user ID
        }), 409

    # Save file details to the database
    # Change `metadata` to `description` here
    add_file_to_db(file.filename, file_path, file_hash, description="File metadata", url=None, user_id=user_id)
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
    try:
        db = get_database()
        files = db["files"].find()  # Fetch all files from the 'files' collection

        # Convert MongoDB cursor to a list of files
        files_list = [{"file_name": file["file_name"], "file_path": file["file_path"], "uploaded_by": file.get("uploaded_by", "Unknown")} for file in files]

        return jsonify({"files": files_list})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    if not os.path.exists(UPLOAD_FOLDER):
        os.makedirs(UPLOAD_FOLDER)
    app.run(host="0.0.0.0", port=5000, debug=True)
