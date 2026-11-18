function setCookie(name, value, expires, path, domain, secure) {
    document.cookie = name + "=" + encodeURIComponent(value) +
        ((expires == null) ? "" : "; expires=" + expires.toUTCString()) +
        ((path == null) ? "" : "; path=" + path) +
        ((domain == null) ? "" : "; domain=" + domain) +
        (secure ? "; secure" : "");
}

function getCookie(name) {
    var cookies = document.cookie.split(";");
    var prefix = name + "=";
    for (var i = 0; i < cookies.length; i++) {
        var cookie = cookies[i].trim();
        if (cookie.indexOf(prefix) === 0) {
            var value = cookie.substring(prefix.length);
            try {
                return decodeURIComponent(value);
            } catch (error) {
                // Preserve compatibility with cookies written using escape().
                return unescape(value);
            }
        }
    }
    return null;
}

function delCookie(name, path, domain) {
    if (getCookie(name) !== null) {
        setCookie(name, "", new Date(0), path, domain);
    }
}

(function () {
    var banner = document.getElementById("barracookies");
    if (banner && getCookie("avisocookies") !== "1") {
        // The existing OK control persists dismissal; loading a page must not.
        banner.style.display = "block";
    }
}());

function initializeSidebar() {
    var toggle = document.querySelector('[data-toggle="offcanvas"]');
    if (!toggle) return;

    var panel = document.getElementById(toggle.getAttribute("aria-controls"));
    if (!panel) {
        toggle.hidden = true;
        return;
    }

    var navbar = toggle.closest(".navbar");
    var mobileLayout = window.matchMedia("(max-width: 767px)");

    function isOpen() {
        return toggle.getAttribute("aria-expanded") === "true";
    }

    function alignPanel() {
        var top = navbar ? Math.max(0, navbar.getBoundingClientRect().bottom) : 0;
        panel.style.setProperty("--sidebar-top", top + "px");
    }

    function showPanel(open) {
        if (open) alignPanel();
        panel.classList.toggle("sidebar-open", open);
        toggle.setAttribute("aria-expanded", String(open));
    }

    toggle.addEventListener("click", function () {
        var open = !isOpen();
        showPanel(open);
        if (open) {
            var firstLink = panel.querySelector("a[href], button:not([disabled])");
            if (firstLink) firstLink.focus();
        }
    });

    document.addEventListener("click", function (event) {
        if (isOpen() && !panel.contains(event.target) && !toggle.contains(event.target)) {
            showPanel(false);
        }
    });

    document.addEventListener("keydown", function (event) {
        if (event.key === "Escape" && isOpen()) {
            showPanel(false);
            toggle.focus();
        }
    });

    window.addEventListener("resize", function () {
        if (!mobileLayout.matches) showPanel(false);
        else if (isOpen()) alignPanel();
    });
}

document.addEventListener("DOMContentLoaded", initializeSidebar);


function initializeSubmenus() {
    var selector = ".dropdown-menu > li > a.trigger";

    function showSubmenu(toggle, open) {
        var menu = toggle.nextElementSibling;
        if (!menu || !menu.classList.contains("dropdown-menu")) return;

        toggle.setAttribute("aria-expanded", String(open));
        if (toggle.id) menu.setAttribute("aria-labelledby", toggle.id);
        menu.classList.toggle("submenu-open", open);
        toggle.classList.toggle("right-caret", !open);
        toggle.classList.toggle("left-caret", open);
    }

    document.querySelectorAll(selector).forEach(function (toggle) {
        if (!toggle.nextElementSibling || !toggle.nextElementSibling.classList.contains("dropdown-menu")) return;
        showSubmenu(toggle, false);

        toggle.addEventListener("click", function (event) {
            event.preventDefault();
            event.stopPropagation();
            var open = toggle.getAttribute("aria-expanded") !== "true";
            toggle.parentElement.parentElement.querySelectorAll(selector).forEach(function (other) {
                if (other !== toggle) showSubmenu(other, false);
            });
            showSubmenu(toggle, open);
        });

        toggle.addEventListener("keydown", function (event) {
            if (event.key === " ") {
                event.preventDefault();
                toggle.click();
            } else if (event.key === "Escape" && toggle.getAttribute("aria-expanded") === "true") {
                event.stopPropagation();
                showSubmenu(toggle, false);
            }
        });
    });

    if (window.jQuery) {
        window.jQuery(document).on("hidden.bs.dropdown", function (event) {
            event.target.querySelectorAll(selector).forEach(function (toggle) {
                showSubmenu(toggle, false);
            });
        });
    }
}

function avoidRepeatedTransition(event) {
    var control = event.target.closest('[data-toggle="collapse"], [data-slide]');
    if (!control) return;

    var target = control.getAttribute("data-target") || control.getAttribute("href");
    if (!target || target.charAt(0) !== "#") return;

    var panel = document.getElementById(target.slice(1));
    if (panel && (panel.classList.contains("collapsing") || panel.querySelector(".carousel-item-next, .carousel-item-prev"))) {
        event.preventDefault();
        event.stopPropagation();
    }
}

document.addEventListener("DOMContentLoaded", initializeSubmenus);
document.addEventListener("click", avoidRepeatedTransition, true);
