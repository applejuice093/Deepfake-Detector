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

function handleFile(file, type, previewEl) {
    files[type] = file;

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
async function runDetection(type) {
    if (!files[type]) {
        showToast("Please upload a file first.");
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
        // 🔑 IMPORTANT: relative URL (works locally + HF)
        const res = await fetch("/analyze", {
            method: "POST",
            headers: {
                "x-api-key": "local-dev-key-123" // dev only
            },
            body: formData
        });

        if (!res.ok) throw new Error("Backend error");

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

        let html = `
            <div class="indicators">
                <div class="section-title">Indicators</div>
        `;

        data.indicators.forEach(ind => {
            html += `
                <p><strong>${ind.name}:</strong> ${ind.score}%</p>
            `;
        });

        html += `</div>`;
        infoSection.insertAdjacentHTML("beforeend", html);

        showToast("Analysis complete.");
    } catch (err) {
        console.error(err);
        showToast("Server error. Check backend.");
    }

    btn.disabled = false;
    btn.innerHTML = `<span>Detect Forgery</span>`;
}

// ----------------------------
// Toast Notification
// ----------------------------
function showToast(message) {
    const toast = document.getElementById("toast");
    toast.textContent = message;
    toast.classList.add("show");
    setTimeout(() => toast.classList.remove("show"), 3000);
}
