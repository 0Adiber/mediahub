const input = document.getElementById("search-input");
const results = document.getElementById("search-results");

let timeout = null;

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
                li.textContent = item.title;
                li.style.cursor = "pointer";

                li.addEventListener("click", () => {
                    if (item.type === "folder") {
                        window.location.href = `/library/${item.lib_slug}/?folder=${item.id}`;
                    } else {
                        window.location.href = `/media/player/?path=${encodeURIComponent(item.file_path)}&lib=${item.lib_slug}`;
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