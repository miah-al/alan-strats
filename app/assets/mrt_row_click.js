/* mrt_row_click.js
 * Bridges row-click events from dash-mantine-react-table back into Dash.
 *
 * dash-mantine-react-table v0.0.1 does not expose a click prop to Dash. This
 * shim watches the DOM for tables that live inside elements marked with the
 * data-attribute  `data-mrt-clickable="1"`  and  data-mrt-target="<store-id>"
 * — for each such wrapper it attaches a delegated click handler on the inner
 * tbody. When a row is clicked, it sets the value of the corresponding
 * hidden Dash dcc.Input (id = data-mrt-target) to the JSON-stringified row
 * data. Dash callbacks then react to that Input as if it were a normal
 * value change.
 *
 * Wrapper markup pattern:
 *
 *     html.Div(
 *         children=[
 *             mrt_grid(...),
 *             dcc.Input(id="my-grid-clicked", type="hidden", value=""),
 *         ],
 *         **{"data-mrt-clickable": "1", "data-mrt-target": "my-grid-clicked"},
 *     )
 *
 * The clicked row's data dict is JSON-stringified into the input's value.
 * Each click writes a fresh value (with a timestamp suffix) so repeated
 * clicks on the same row also fire the callback.
 */
(function () {
    "use strict";

    function pushToDash(targetId, payload) {
        // Modern Dash (2.17+) lets us push values directly into a component's
        // state from clientside JS. This actually triggers callbacks listening
        // to that component's prop — unlike setting input.value, which bypasses
        // React and Dash never sees the change.
        if (window.dash_clientside && window.dash_clientside.set_props) {
            window.dash_clientside.set_props(targetId, { value: payload });
            return true;
        }
        return false;
    }

    function attach(wrapper) {
        if (wrapper.__mrtClickAttached) return;
        // Find the first table that belongs to this wrapper (skip if MRT
        // hasn't rendered yet — observer will retry)
        const table = wrapper.querySelector("table");
        const tbody = table && table.querySelector("tbody");
        if (!tbody) return;

        const targetId = wrapper.getAttribute("data-mrt-target");
        if (!targetId) return;

        wrapper.__mrtClickAttached = true;

        tbody.addEventListener("click", function (ev) {
            const row = ev.target.closest("tr");
            if (!row) return;
            const rows = Array.from(tbody.querySelectorAll(":scope > tr"));
            const rowIndex = rows.indexOf(row);
            if (rowIndex < 0) return;

            // Extract cell text content (useful for callbacks that want to
            // route on label rather than data lookup)
            const cells = row.querySelectorAll("td");
            const cellTexts = Array.from(cells).map((c) => c.innerText.trim());

            const payload = JSON.stringify({
                rowIndex: rowIndex,
                cellTexts: cellTexts,
                timestamp: Date.now(),
            });
            const ok = pushToDash(targetId, payload);
            if (!ok) {
                console.warn("[mrt_row_click] dash_clientside.set_props unavailable; row click ignored");
            }
        });
    }

    function scanAndAttach() {
        document
            .querySelectorAll('[data-mrt-clickable="1"]')
            .forEach(attach);
    }

    // Initial scan + observe future DOM mutations (Dash often re-renders)
    function init() {
        scanAndAttach();
        const observer = new MutationObserver(() => {
            scanAndAttach();
        });
        observer.observe(document.body, { childList: true, subtree: true });
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
})();
