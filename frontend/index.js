// ----------------------------
// State Management
// ----------------------------
let currentTab = "home";

const files = {
    image: null,
    video: null,
    audio: null
};

// ----------------------------
// Tab Switching
// ----------------------------
function switchTab(tabName) {
    document.querySelectorAll(".nav-links a").forEach(link => {
        link.classList.remove("active");
        if (link.getAttribute("onclick")?.includes(tabName)) {
            link.classList.add("active");
        }
    });

    document.querySelectorAll(".tab-content").forEach(tab => {
        tab.classList.add("hidden");
        tab.classList.remove("show");
    });

    const selected = document.getElementById(`${tabName}-tab`);
    if (selected) {
        selected.classList.remove("hidden");
        selected.classList.add("show");
    }

    currentTab = tabName;
}

// ----------------------------
// File Handling
// ----------------------------
function setupFileHandler(type) {
    const dropZone = document.getElementById(`${type}-drop-zone`);
    const input = document.getElementById(`${type}-input`);
    const preview = document.getElementById(`${type}-preview`);

    if (!dropZone) return;

    dropZone.addEventListener("click", () => input.click());

    dropZone.addEventListener("dragover", e => {
        e.preventDefault();
        dropZone.classList.add("drag-over");
    });

    dropZone.addEventListener("dragleave", () => {
        dropZone.classList.remove("drag-over");
    });

    dropZone.addEventListener("drop", e => {
        e.preventDefault();
        dropZone.classList.remove("drag-over");
        if (e.dataTransfer.files.length) {
            handleFile(e.dataTransfer.files[0], type, preview);
        }
    });

    input.addEventListener("change", e => {
        if (e.target.files.length) {
            handleFile(e.target.files[0], type, preview);
        }
    });
}

// Mirrors the server's MAX_UPLOAD_MB default so users get instant feedback
// instead of uploading a large file only to receive a 413.
const MAX_UPLOAD_MB = 10;

function validateFile(file, type) {
    // Drag-and-drop bypasses the input's `accept` filter, so check here too.
    if (!file.type.startsWith(`${type}/`)) {
        return `Please choose a ${type} file (got ${file.type || "unknown type"}).`;
    }
    if (file.size > MAX_UPLOAD_MB * 1024 * 1024) {
        return `File is too large (max ${MAX_UPLOAD_MB} MB).`;
    }
    if (file.size === 0) {
        return "File is empty.";
    }
    return null;
}

function handleFile(file, type, previewEl) {
    const problem = validateFile(file, type);
    if (problem) {
        showToast(problem);
        return;
    }

    files[type] = file;

    // Release the previous preview's blob URL so repeated uploads don't leak memory.
    if (previewEl.src.startsWith("blob:")) URL.revokeObjectURL(previewEl.src);
    const url = URL.createObjectURL(file);
    previewEl.src = url;
    previewEl.style.display = "block";

    const icon = previewEl.parentElement.querySelector("i");
    if (icon) icon.style.display = "none";

    previewEl.parentElement.querySelectorAll("p, h3")
        .forEach(el => el.style.display = "none");

    showToast(`${file.name} uploaded successfully`);
}

// ----------------------------
// Reset
// ----------------------------
function resetUpload(type) {
    files[type] = null;

    const input = document.getElementById(`${type}-input`);
    const preview = document.getElementById(`${type}-preview`);
    const resultBox = document.getElementById(`${type}-result`);
    const dropZone = document.getElementById(`${type}-drop-zone`);

    input.value = "";
    if (preview.src.startsWith("blob:")) URL.revokeObjectURL(preview.src);
    preview.src = "";
    preview.style.display = "none";

    dropZone.querySelectorAll("i, p, h3")
        .forEach(el => el.style.display = "block");

    if (resultBox) resultBox.style.display = "none";

    showToast(`${type.toUpperCase()} reset`);
}

// Init handlers
setupFileHandler("image");
setupFileHandler("video");
setupFileHandler("audio");

// ----------------------------
// REAL Detection Logic
// ----------------------------
// Only image analysis exists on the backend; /analyze answers 415 for
// anything else, so say so up front instead of showing a server error.
const SUPPORTED_DETECTION = new Set(["image"]);

async function runDetection(type) {
    if (!files[type]) {
        showToast("Please upload a file first.");
        return;
    }
    if (!SUPPORTED_DETECTION.has(type)) {
        showToast(`${type[0].toUpperCase()}${type.slice(1)} detection is coming soon. Only images can be analysed for now.`);
        return;
    }

    const btn = document.getElementById(`${type}-detect-btn`);
    const resultBox = document.getElementById(`${type}-result`);
    const badge = document.getElementById(`${type}-badge`);
    const score = document.getElementById(`${type}-score`);
    const infoSection = document.querySelector(`#${type}-tab .info-section`);

    btn.disabled = true;
    btn.innerHTML = `<span class="spinner"></span> Analyzing...`;
    resultBox.style.display = "block";
    score.textContent = "0%";

    const formData = new FormData();
    formData.append("file", files[type]);

    try {
        // Relative URL so it works both locally and on the Hugging Face Space.
        // The API needs no auth header; the browser sets the multipart
        // Content-Type (with boundary) itself.
        const res = await fetch("/analyze", {
            method: "POST",
            body: formData
        });

        if (!res.ok) {
            // Surface the API's explanation (e.g. unsupported type, too large)
            let detail = `Request failed (${res.status})`;
            try {
                const body = await res.json();
                if (body && body.detail) detail = body.detail;
            } catch (_) { /* non-JSON error body */ }
            throw new Error(detail);
        }

        const data = await res.json();

        // ----------------------------
        // Score & Risk
        // ----------------------------
        const confidence = data.overall_score;
        const risk = data.risk_level;

        score.textContent = `${confidence}%`;

        if (risk.includes("High")) {
            badge.textContent = "High Risk – Possible Deepfake";
            badge.className = "result-badge result-fake";
            score.style.color = "var(--accent-red)";
        } else if (risk.includes("Medium")) {
            badge.textContent = "Medium Risk – Inconclusive";
            badge.className = "result-badge";
            score.style.color = "orange";
        } else {
            badge.textContent = "Low Risk – Likely Authentic";
            badge.className = "result-badge result-real";
            score.style.color = "var(--accent-green)";
        }

        // ----------------------------
        // Indicators
        // ----------------------------
        const old = infoSection.querySelector(".indicators");
        if (old) old.remove();

        // Build with DOM APIs + textContent rather than innerHTML so API
        // values can never be interpreted as markup.
        const indicators = document.createElement("div");
        indicators.className = "indicators";

        const title = document.createElement("div");
        title.className = "section-title";
        title.textContent = "Indicators";
        indicators.appendChild(title);

        (data.indicators || []).forEach(ind => {
            const row = document.createElement("p");
            const name = document.createElement("strong");
            name.textContent = `${ind.name}:`;
            row.append(name, ` ${ind.score}%`);
            indicators.appendChild(row);
        });

        infoSection.appendChild(indicators);

        showToast("Analysis complete.");
    } catch (err) {
        console.error(err);
        showToast(err.message || "Server error. Check backend.");
        resultBox.style.display = "none";
    } finally {
        // Always restore the button, even if rendering the result throws.
        btn.disabled = false;
        btn.innerHTML = `<span>Detect Forgery</span>`;
    }
}

// ----------------------------
// Toast Notification
// ----------------------------
let toastTimer = null;

function showToast(message) {
    const toast = document.getElementById("toast");
    toast.textContent = message;
    toast.classList.add("show");
    // Restart the timer so a new toast isn't hidden early by an older one.
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => toast.classList.remove("show"), 3000);
}
