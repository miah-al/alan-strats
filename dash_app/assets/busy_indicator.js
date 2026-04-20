// Global busy indicator for Dash callbacks.
// Counts in-flight /_dash-update-component requests and toggles the
// `busy` class on #app-busy-indicator accordingly.
(function () {
    let pending = 0;

    function update() {
        const el = document.getElementById("app-busy-indicator");
        if (el) {
            el.classList.toggle("busy", pending > 0);
        }
        // Toggle a body class so CSS can gray-out & block interactive controls.
        if (document.body) {
            document.body.classList.toggle("app-busy", pending > 0);
        }
    }

    function isDashUpdate(url) {
        if (!url) return false;
        const s = typeof url === "string" ? url : (url.url || "");
        return s.indexOf("_dash-update-component") !== -1;
    }

    // Hook fetch
    const origFetch = window.fetch;
    if (origFetch) {
        window.fetch = function (input, init) {
            const tracked = isDashUpdate(input);
            if (tracked) {
                pending++;
                update();
            }
            const p = origFetch.apply(this, arguments);
            if (tracked) {
                p.then(() => {
                    pending = Math.max(0, pending - 1);
                    update();
                }, () => {
                    pending = Math.max(0, pending - 1);
                    update();
                });
            }
            return p;
        };
    }

    // Hook XHR as a safety net (Dash uses fetch, but older plugins may use XHR)
    const origOpen = XMLHttpRequest.prototype.open;
    XMLHttpRequest.prototype.open = function (method, url) {
        this._dashTracked = isDashUpdate(url);
        return origOpen.apply(this, arguments);
    };
    const origSend = XMLHttpRequest.prototype.send;
    XMLHttpRequest.prototype.send = function () {
        if (this._dashTracked) {
            pending++;
            update();
            const done = () => {
                if (!this._dashCounted) {
                    this._dashCounted = true;
                    pending = Math.max(0, pending - 1);
                    update();
                }
            };
            this.addEventListener("loadend", done);
            this.addEventListener("error", done);
            this.addEventListener("abort", done);
        }
        return origSend.apply(this, arguments);
    };
})();
