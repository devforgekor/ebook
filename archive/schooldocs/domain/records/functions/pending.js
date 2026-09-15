const { app } = require("@azure/functions");
const { ADMIN_TYPES, requireDocumentAccess } = require("../admins");
const { getCosmosContainer } = require("../cosmos");
const { resolveAdmin } = require("../adminAccess");

const UNKNOWN_REVIEW_REASON_CODES = [
    "manual_verified",
    "external_confirmation",
    "doc_reupload_required",
    "source_unreadable"
];
const UNKNOWN_REASON_CODES_BY_TARGET_STATUS = {
    approved: ["manual_verified", "external_confirmation"],
    rejected: ["doc_reupload_required", "source_unreadable"]
};
const APPROVE_VALIDATION_ERROR_CODES = {
    missingRequiredFields: "MISSING_REQUIRED_FIELDS",
    invalidTargetStatus: "INVALID_TARGET_STATUS",
    reviewNoteRequired: "REVIEW_NOTE_REQUIRED",
    reviewReasonCodeRequired: "REVIEW_REASON_CODE_REQUIRED",
    invalidReviewReasonCode: "INVALID_REVIEW_REASON_CODE",
    invalidReasonCodeForTargetStatus: "INVALID_REASON_CODE_FOR_TARGET_STATUS",
    recordInvalidState: "RECORD_INVALID_STATE"
};

function getRecordsContainer() {
    return getCosmosContainer(process.env.COSMOS_CONTAINER || "records");
}

function normalizeLimit(value, fallback) {
    const parsed = Number(value);
    if (!Number.isFinite(parsed) || parsed <= 0) {
        return fallback;
    }

    return Math.min(parsed, 200);
}

function getReviewRequirements(item) {
    const currentStatus = String(item?.status || "");
    const requiresReviewNote = currentStatus === "pending_ai" || currentStatus === "unknown";
    const requiresReviewReasonCode = currentStatus === "unknown";

    return {
        requiresReviewNote,
        requiresReviewReasonCode,
        allowedReviewReasonCodes: requiresReviewReasonCode ? UNKNOWN_REVIEW_REASON_CODES : [],
        allowedReviewReasonCodesByTargetStatus: requiresReviewReasonCode
            ? UNKNOWN_REASON_CODES_BY_TARGET_STATUS
            : null
    };
}

app.http("pending", {
    methods: ["GET"],
    authLevel: "anonymous",
    route: "manage/pending",
    handler: async (request, context) => {
        try {
            const admin = await resolveAdmin(request);
            const url = new URL(request.url);

            const status = (url.searchParams.get("status") || "pending").trim();
            const documentType = (url.searchParams.get("documentType") || "").trim();
            const dryRun = url.searchParams.get("dryRun") === "true";
            const limit = normalizeLimit(url.searchParams.get("limit"), 50);

            if (documentType) {
                requireDocumentAccess(admin, documentType);
            }

            if (dryRun) {
                return {
                    status: 200,
                    jsonBody: {
                        message: "pending dry-run ok",
                        dryRun,
                        admin: {
                            email: admin.email,
                            type: admin.type,
                            allowedDocumentTypes: admin.allowedDocumentTypes
                        },
                        filters: {
                            status,
                            documentType: documentType || null,
                            limit
                        }
                    }
                };
            }

            const recordsContainer = getRecordsContainer();
            const querySpec = documentType
                ? {
                    query: `SELECT TOP ${limit} * FROM c WHERE c.status = @status AND c.documentType = @documentType ORDER BY c.uploadedAt DESC`,
                    parameters: [
                        { name: "@status", value: status },
                        { name: "@documentType", value: documentType }
                    ]
                }
                : {
                    query: `SELECT TOP ${limit} * FROM c WHERE c.status = @status ORDER BY c.uploadedAt DESC`,
                    parameters: [
                        { name: "@status", value: status }
                    ]
                };

            const { resources } = await recordsContainer.items.query(querySpec).fetchAll();

            const filtered = admin.type === ADMIN_TYPES.SUPER
                ? resources
                : resources.filter((item) => admin.allowedDocumentTypes.includes(item.documentType));

            const items = filtered.map((item) => ({
                ...item,
                reviewRequirements: getReviewRequirements(item)
            }));

            return {
                status: 200,
                jsonBody: {
                    items,
                    count: items.length,
                    reviewPolicy: {
                        approveValidationErrorCodes: APPROVE_VALIDATION_ERROR_CODES,
                        unknownReasonCodesByTargetStatus: UNKNOWN_REASON_CODES_BY_TARGET_STATUS
                    }
                }
            };
        } catch (error) {
            const errorMessage = error && error.message ? error.message : String(error);
            context.error("pending error:", errorMessage);

            if (error.code === "ADMIN_UNAUTHORIZED") {
                return { status: 401, body: errorMessage };
            }

            if (error.code === "ADMIN_NOT_FOUND" || error.code === "ADMIN_ACCESS_DENIED") {
                return { status: 403, body: errorMessage };
            }

            if (/ECONNREFUSED|timeout|ENOTFOUND|connect|RestError/i.test(errorMessage)) {
                return { status: 503, body: "Records storage is unavailable" };
            }

            return { status: 500, body: "Internal Server Error" };
        }
    }
});
