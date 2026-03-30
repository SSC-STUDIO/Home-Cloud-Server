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

    /* ── Dark mode toggle ─────────────────────────── */

    const themeToggle = document.getElementById("themeToggle");
    if (themeToggle) {
        themeToggle.addEventListener("click", () => {
            const html = document.documentElement;
            const next = html.getAttribute("data-theme") === "dark" ? "light" : "dark";
            html.setAttribute("data-theme", next);
            localStorage.setItem("hc-theme", next);
            document.querySelector('meta[name="theme-color"]').setAttribute(
                "content",
                next === "dark" ? "#0c1222" : "#0f172a"
            );
        });
    }

    /* ── Mobile sidebar drawer ────────────────────── */

    const sidebar = document.getElementById("appSidebar");
    const overlay = document.getElementById("sidebarOverlay");
    const sidebarToggle = document.getElementById("sidebarToggle");
    const sidebarClose = document.getElementById("sidebarClose");

    function openSidebar() {
        if (!sidebar) return;
        sidebar.classList.add("is-open");
        if (overlay) overlay.classList.add("is-active");
        document.body.style.overflow = "hidden";
    }

    function closeSidebar() {
        if (!sidebar) return;
        sidebar.classList.remove("is-open");
        if (overlay) overlay.classList.remove("is-active");
        document.body.style.overflow = "";
    }

    if (sidebarToggle) sidebarToggle.addEventListener("click", openSidebar);
    if (sidebarClose) sidebarClose.addEventListener("click", closeSidebar);
    if (overlay) overlay.addEventListener("click", closeSidebar);

    function updateSidebarCloseVisibility() {
        if (!sidebarClose) return;
        if (window.innerWidth <= 992) {
            sidebarClose.classList.remove("d-none");
        } else {
            sidebarClose.classList.add("d-none");
            closeSidebar();
        }
    }

    updateSidebarCloseVisibility();
    window.addEventListener("resize", updateSidebarCloseVisibility);
});
