const DOCUMENT_TYPES = {
    safety: {
        type: "safety",
        label: "안전교육 이수증",
        validityYears: 3,
        usesCohort: true
    },
    integrity: {
        type: "integrity",
        label: "청렴교육 이수증",
        validityYears: 1,
        usesCohort: false
    },
    mandatory: {
        type: "mandatory",
        label: "의무교육 이수증",
        validityYears: 1,
        usesCohort: false
    }
};

const SAFETY_COHORT_BASE_YEAR = 2024;

function getDocumentPolicy(documentType) {
    return DOCUMENT_TYPES[documentType] || null;
}

function calculateValidUntil(submittedAt, validityYears) {
    const submittedDate = new Date(submittedAt);
    const validUntil = new Date(Date.UTC(
        submittedDate.getUTCFullYear() + validityYears - 1,
        11,
        31,
        23,
        59,
        59,
        999
    ));

    return validUntil.toISOString();
}

function getCohortId(documentType, submittedYear) {
    const policy = getDocumentPolicy(documentType);

    if (!policy || !policy.usesCohort) {
        return `${documentType}_${submittedYear}`;
    }

    const offset = submittedYear - SAFETY_COHORT_BASE_YEAR;
    const cohortStartYear = SAFETY_COHORT_BASE_YEAR + Math.floor(offset / 3) * 3;
    const cohortEndYear = cohortStartYear + 2;

    return `${documentType}_${cohortStartYear}-${cohortEndYear}`;
}

function buildRecordId(personId, documentType, submittedYear) {
    return `${documentType}_${personId}_${submittedYear}`;
}

module.exports = {
    DOCUMENT_TYPES,
    getDocumentPolicy,
    calculateValidUntil,
    getCohortId,
    buildRecordId
};