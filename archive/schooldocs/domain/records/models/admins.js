const ADMIN_TYPES = {
    SUPER: "super",
    SUB: "sub"
};

function normalizeAllowedDocumentTypes(allowedDocumentTypes) {
    if (!Array.isArray(allowedDocumentTypes)) {
        return [];
    }

    return [...new Set(
        allowedDocumentTypes
            .filter((value) => typeof value === "string")
            .map((value) => value.trim().toLowerCase())
            .filter(Boolean)
    )];
}

function normalizeAdmin(admin) {
    if (!admin || typeof admin !== "object") {
        return null;
    }

    const allowedDocumentTypes = normalizeAllowedDocumentTypes([
        ...(Array.isArray(admin.allowedDocumentTypes) ? admin.allowedDocumentTypes : []),
        ...(Array.isArray(admin.allowedCertificateTypes) ? admin.allowedCertificateTypes : [])
    ]);

    return {
        ...admin,
        email: typeof admin.email === "string" ? admin.email.trim().toLowerCase() : "",
        type: admin.type === ADMIN_TYPES.SUPER ? ADMIN_TYPES.SUPER : ADMIN_TYPES.SUB,
        allowedDocumentTypes
    };
}

function canAccessDocumentType(admin, documentType) {
    const normalizedAdmin = normalizeAdmin(admin);

    if (!normalizedAdmin || !documentType) {
        return false;
    }

    if (normalizedAdmin.type === ADMIN_TYPES.SUPER) {
        return true;
    }

    return normalizedAdmin.allowedDocumentTypes.includes(documentType);
}

function requireDocumentAccess(admin, documentType) {
    if (!canAccessDocumentType(admin, documentType)) {
        const error = new Error(`Access denied to document type: ${documentType}`);
        error.code = "ADMIN_ACCESS_DENIED";
        throw error;
    }

    return true;
}

module.exports = {
    ADMIN_TYPES,
    normalizeAllowedDocumentTypes,
    normalizeAdmin,
    canAccessDocumentType,
    requireDocumentAccess
};