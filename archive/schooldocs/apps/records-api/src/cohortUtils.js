function parseDocumentTypeFromCohortId(cohortId) {
    if (typeof cohortId !== "string") {
        return "";
    }

    const value = cohortId.trim();
    if (!value) {
        return "";
    }

    const [documentType] = value.split("_");
    return (documentType || "").trim().toLowerCase();
}

function normalizeCohortId(value) {
    if (typeof value !== "string") {
        return "";
    }

    return value.trim();
}

module.exports = {
    parseDocumentTypeFromCohortId,
    normalizeCohortId
};
