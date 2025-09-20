const input = document.getElementById("search-input");
const results = document.getElementById("search-results");

let timeout = null;

const iconMovie = `<svg width="16" height="16" fill="currentColor" class="bi bi-film" viewBox="0 0 16 16">
<path d="M0 1a1 1 0 0 1 1-1h14a1 1 0 0 1 1 1v14a1 1 0 0 1-1 1H1a1 1 0 0 1-1-1zm4 0v6h8V1zm8 8H4v6h8zM1 1v2h2V1zm2 3H1v2h2zM1 7v2h2V7zm2 3H1v2h2zm-2 3v2h2v-2zM15 1h-2v2h2zm-2 3v2h2V4zm2 3h-2v2h2zm-2 3v2h2v-2zm2 3h-2v2h2z"/>
</svg>`;
const iconPic = `<svg width="16" height="16" fill="currentColor" class="bi bi-file-image" viewBox="0 0 16 16">
<path d="M8.002 5.5a1.5 1.5 0 1 1-3 0 1.5 1.5 0 0 1 3 0"/>
<path d="M12 0H4a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h8a2 2 0 0 0 2-2V2a2 2 0 0 0-2-2M3 2a1 1 0 0 1 1-1h8a1 1 0 0 1 1 1v8l-2.083-2.083a.5.5 0 0 0-.76.063L8 11 5.835 9.7a.5.5 0 0 0-.611.076L3 12z"/>
</svg>`;
const iconFolder = `<svg width="16" height="16" fill="currentColor" class="bi bi-folder-fill" viewBox="0 0 16 16">
<path d="M9.828 3h3.982a2 2 0 0 1 1.992 2.181l-.637 7A2 2 0 0 1 13.174 14H2.825a2 2 0 0 1-1.991-1.819l-.637-7a2 2 0 0 1 .342-1.31L.5 3a2 2 0 0 1 2-2h3.672a2 2 0 0 1 1.414.586l.828.828A2 2 0 0 0 9.828 3m-8.322.12q.322-.119.684-.12h5.396l-.707-.707A1 1 0 0 0 6.172 2H2.5a1 1 0 0 0-1 .981z"/>
</svg>`;

function runSearch(query) {
    if (!query) {
        results.innerHTML = "";
        return;
    }
    fetch(`/search/?q=${encodeURIComponent(query)}`)
        .then(res => res.json())
        .then(data => {
            results.innerHTML = "";
            data.forEach(item => {
                const li = document.createElement("li");
                li.className = "list-group-item list-group-item-action";
                li.style.cursor = "pointer";

                if (item.type === "folder") {
                    li.innerHTML = `<span class="me-2">${iconFolder}</span>${item.title}`
                } else if(item.isvideo) {
                    li.innerHTML = `<span class="me-2">${iconMovie}</span>${item.title}`
                } else {
                    li.innerHTML = `<span class="me-2">${iconPic}</span>${item.title}`
                }

                li.addEventListener("click", () => {
                    if (item.type === "folder") {
                        window.location.href = `/library/${item.lib_slug}/?folder=${item.id}`;
                    } else if(item.isvideo) {
                        window.location.href = `/media/player/?path=${encodeURIComponent(item.file_path)}&lib=${item.lib_slug}`;
                    } else {
                        window.location.href = `/media/image/?lib=${item.lib_slug}&id=${item.id}&folder=${item.folder}`
                    }
                });
                results.appendChild(li);
            });
        });
}

input.addEventListener("input", function() {
    clearTimeout(timeout);
    const query = this.value.trim();
    timeout = setTimeout(() => runSearch(query), 300);
});

// Hide results when input loses focus
input.addEventListener("blur", () => {
    setTimeout(() => {
        results.innerHTML = "";
    }, 150);
});

// Restore results on focus if query is not empty
input.addEventListener("focus", () => {
    const query = input.value.trim();
    if (query) {
        runSearch(query);
    }
});