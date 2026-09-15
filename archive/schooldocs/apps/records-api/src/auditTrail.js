function createAuditEntry(action, actor, details = {}) {
    return {
        at: new Date().toISOString(),
        action,
        actor: typeof actor === "string" && actor.trim() ? actor.trim().toLowerCase() : "system",
        details
    };
}

function appendAuditTrail(document, entry, maxItems = 20) {
    const current = Array.isArray(document.auditTrail) ? document.auditTrail : [];
    const next = [...current, entry];

    if (next.length <= maxItems) {
        return next;
    }

    return next.slice(next.length - maxItems);
}

module.exports = {
    createAuditEntry,
    appendAuditTrail
};
