// Handling tab switching
const tabLinks = document.querySelectorAll(".tab-link");
const tabPanes = document.querySelectorAll(".tab-pane");

tabLinks.forEach(link => {
    link.addEventListener("click", (e) => {
        e.preventDefault();
        const targetTab = e.target.getAttribute("data-tab");

        // Remove active class from all tabs
        tabLinks.forEach(link => link.classList.remove("active"));
        tabPanes.forEach(pane => pane.classList.remove("active"));

        // Add active class to clicked tab and corresponding tab pane
        e.target.classList.add("active");
        document.getElementById(targetTab).classList.add("active");
    });
});

// Default to the first tab being active
document.querySelector(".tab-link").classList.add("active");
document.querySelector(".tab-pane").classList.add("active");

// Upload Form Event Listener
document.getElementById("uploadForm").addEventListener("submit", async (e) => {
    e.preventDefault();
    const formData = new FormData(e.target);

    const response = await fetch("/upload", { 
        method: "POST", 
        body: formData 
    });

    const result = await response.json();
    document.getElementById("uploadResponse").textContent = JSON.stringify(result, null, 2);

    if (result.message === "Duplicate file detected") {
        alert(`Duplicate detected. Uploaded by user ID: ${result.uploaded_by}`);
    } else {
        alert(result.message || "File uploaded successfully!");
    }
});

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


// Get files from the server
document.getElementById("getFilesButton").addEventListener("click", async () => {
    try {
        const response = await fetch("/get_files", { method: "GET" });

        const result = await response.json();
        
        const filesListDiv = document.getElementById("filesList");
        filesListDiv.innerHTML = '';

        if (result.files && result.files.length > 0) {
            const fileListHtml = result.files.map(file => 
                `<div>
                    <strong>${file.file_name}</strong><br>
                    Path: ${file.file_path}<br>
                    Uploaded by: ${file.uploaded_by}<br>
                    <hr>
                </div>`).join('');
            filesListDiv.innerHTML = fileListHtml;
        } else {
            filesListDiv.innerHTML = '<p>No files found in the database.</p>';
        }
    } catch (error) {
        console.error("Error fetching files:", error);
        alert("An error occurred while fetching the files.");
    }
});
