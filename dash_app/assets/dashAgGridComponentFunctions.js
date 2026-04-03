var dagcomponentfuncs = (window.dashAgGridComponentFunctions =
    window.dashAgGridComponentFunctions || {});

/**
 * DetailButton — renders a small "⋯" button inside an AG Grid cell.
 * Clicking it fires props.setData(tgid), which sets cellRendererData
 * on the AgGrid component and triggers Dash callbacks.
 */
dagcomponentfuncs.DetailButton = function (props) {
    return React.createElement(
        "button",
        {
            style: {
                background: "transparent",
                border: "1px solid #6366f1",
                borderRadius: "4px",
                color: "#6366f1",
                cursor: "pointer",
                fontSize: "15px",
                fontWeight: "700",
                padding: "1px 8px",
                lineHeight: "1.3",
            },
            title: "View position detail",
            onClick: function (e) {
                e.stopPropagation();
                props.setData(props.data._tgid || props.data["Trade Group"] || "");
            },
        },
        "⋯"
    );
};
