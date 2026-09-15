function createAuditEntry(action, actor, details = {}) {
  return {
    action,
    actor,
    details,
    timestamp: new Date().toISOString()
  };
}

module.exports = { createAuditEntry };
