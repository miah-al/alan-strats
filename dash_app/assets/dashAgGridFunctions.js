var dagfuncs = window.dashAgGridFunctions = window.dashAgGridFunctions || {};

dagfuncs.pnlStyle = function(params) {
    var val = params.data ? params.data._net : null;
    if (val == null) return {};
    if (val > 0) return { color: '#10b981' };
    if (val < 0) return { color: '#ef4444' };
    return { color: '#9ca3af' };
};

dagfuncs.pnlStrStyle = function(params) {
    var v = params.value || '';
    if (v.startsWith('+')) return { color: '#10b981' };
    if (v.startsWith('-')) return { color: '#ef4444' };
    return { color: '#9ca3af' };
};

dagfuncs.resultStyle = function(params) {
    if (params.value === 'WIN')  return { color: '#10b981' };
    if (params.value === 'LOSS') return { color: '#ef4444' };
    return { color: '#9ca3af' };
};
