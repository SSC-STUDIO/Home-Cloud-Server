document.addEventListener("DOMContentLoaded", () => {
    if (window.bootstrap) {
        document.querySelectorAll('[data-bs-toggle="tooltip"]').forEach((element) => {
            new bootstrap.Tooltip(element);
        });

        document.querySelectorAll('[data-bs-toggle="popover"]').forEach((element) => {
            new bootstrap.Popover(element);
        });
    }

    const currentLocation = window.location.pathname;
    document.querySelectorAll(".sidebar .nav-link").forEach((link) => {
        if (link.getAttribute("href") === currentLocation) {
            link.classList.add("active");
        }
    });

    document.querySelectorAll('.dropdown-item[href^="/language/"]').forEach((item) => {
        item.addEventListener("click", async (event) => {
            event.preventDefault();

            try {
                await fetch(item.getAttribute("href"), {
                    method: "GET",
                    headers: {
                        "X-Requested-With": "XMLHttpRequest",
                    },
                });
                window.location.reload();
            } catch (error) {
                console.error("Failed to switch language", error);
            }
        });
    });
});
