const { app } = require("@azure/functions");
const { requireDocumentAccess } = require("../admins");
const { getCosmosContainer } = require("../cosmos");
const { resolveAdmin } = require("../adminAccess");
const { createAuditEntry, appendAuditTrail } = require("../auditTrail");

const REVIEWABLE_STATUSES = new Set(["pending", "pending_ai", "unknown"]);
const TARGET_STATUSES = new Set(["approved", "rejected"]);
const NOTE_REQUIRED_STATUSES = new Set(["pending_ai", "unknown"]);
const UNKNOWN_REVIEW_REASON_CODES = new Set([
    "manual_verified",
    "external_confirmation",
    "doc_reupload_required",
    "source_unreadable"
]);
const UNKNOWN_REASON_CODES_BY_TARGET_STATUS = {
    approved: new Set(["manual_verified", "external_confirmation"]),
    rejected: new Set(["doc_reupload_required", "source_unreadable"])
};

function getRecordsContainer() {
    return getCosmosContainer(process.env.COSMOS_CONTAINER || "records");
}

function normalizeString(value) {
    if (typeof value !== "string") {
        return "";
    }

    return value.trim();
}

function badRequest(code, message, details) {
    return {
        status: 400,
        jsonBody: {
            code,
            message,
            ...(details ? { details } : {})
        }
    };
}

function validateTransition(fromStatus, toStatus) {
    if (!REVIEWABLE_STATUSES.has(fromStatus)) {
        const error = new Error(`cannot transition from status: ${fromStatus}`);
        error.code = "RECORD_INVALID_STATE";
        throw error;
    }

    if (!TARGET_STATUSES.has(toStatus)) {
        const error = new Error(`invalid target status: ${toStatus}`);
        error.code = "RECORD_INVALID_STATE";
        throw error;
    }
}

async function findRecordById(recordId) {
    const recordsContainer = getRecordsContainer();
    const querySpec = {
        query: "SELECT TOP 1 * FROM c WHERE c.id = @id",
        parameters: [{ name: "@id", value: recordId }]
    };

    const { resources } = await recordsContainer.items.query(querySpec).fetchAll();
    return resources[0] || null;
}

async function saveReviewedRecord(record) {
    const recordsContainer = getRecordsContainer();
    await recordsContainer.items.upsert(record);
}

app.http("approve", {
    methods: ["POST"],
    authLevel: "anonymous",
    route: "manage/approve",
    handler: async (request, context) => {
        try {
            const admin = await resolveAdmin(request);
            const body = await request.json().catch(() => ({}));

            const recordId = normalizeString(body.recordId);
            const targetStatus = normalizeString(body.status).toLowerCase();
            const reviewNote = normalizeString(body.reviewNote);
            const reviewReasonCode = normalizeString(body.reviewReasonCode).toLowerCase();
            const expectedUpdatedAt = normalizeString(body.expectedUpdatedAt);
            const dryRun = body.dryRun === true;

            if (!recordId || !targetStatus) {
                return badRequest(
                    "MISSING_REQUIRED_FIELDS",
                    "필수 항목이 누락됐습니다: recordId, status(approved|rejected)"
                );
            }

            if (!TARGET_STATUSES.has(targetStatus)) {
                return badRequest("INVALID_TARGET_STATUS", "status는 approved 또는 rejected만 가능합니다.");
            }

            if (dryRun) {
                return {
                    status: 200,
                    jsonBody: {
                        message: "approve dry-run ok",
                        dryRun,
                        recordId,
                        targetStatus,
                        reviewNote: reviewNote || null,
                        reviewReasonCode: reviewReasonCode || null
                    }
                };
            }

            const record = await findRecordById(recordId);

            if (!record) {
                return { status: 404, body: "record not found" };
            }

            requireDocumentAccess(admin, record.documentType);
            validateTransition(String(record.status || ""), targetStatus);

            if (NOTE_REQUIRED_STATUSES.has(String(record.status || "")) && !reviewNote) {
                return badRequest(
                    "REVIEW_NOTE_REQUIRED",
                    "pending_ai 또는 unknown 상태는 reviewNote가 필수입니다."
                );
            }

            if (String(record.status || "") === "unknown") {
                if (!reviewReasonCode) {
                    return badRequest(
                        "REVIEW_REASON_CODE_REQUIRED",
                        "unknown 상태는 reviewReasonCode가 필수입니다."
                    );
                }

                if (!UNKNOWN_REVIEW_REASON_CODES.has(reviewReasonCode)) {
                    return badRequest(
                        "INVALID_REVIEW_REASON_CODE",
                        "reviewReasonCode는 manual_verified, external_confirmation, doc_reupload_required, source_unreadable 중 하나여야 합니다.",
                        {
                            allowedReviewReasonCodes: Array.from(UNKNOWN_REVIEW_REASON_CODES)
                        }
                    );
                }

                const allowedReasonCodes = UNKNOWN_REASON_CODES_BY_TARGET_STATUS[targetStatus] || new Set();
                if (!allowedReasonCodes.has(reviewReasonCode)) {
                    return badRequest(
                        "INVALID_REASON_CODE_FOR_TARGET_STATUS",
                        targetStatus === "approved"
                            ? "unknown 상태를 approved로 바꿀 때 reviewReasonCode는 manual_verified 또는 external_confirmation만 가능합니다."
                            : "unknown 상태를 rejected로 바꿀 때 reviewReasonCode는 doc_reupload_required 또는 source_unreadable만 가능합니다.",
                        {
                            targetStatus,
                            allowedReviewReasonCodes: Array.from(allowedReasonCodes)
                        }
                    );
                }
            }

            if (expectedUpdatedAt && expectedUpdatedAt !== String(record.updatedAt || "")) {
                return {
                    status: 409,
                    body: "record was updated by another process"
                };
            }

            const reviewedAt = new Date().toISOString();
            const nextRecord = {
                ...record,
                status: targetStatus,
                reviewedAt,
                reviewedBy: admin.email,
                reviewNote: reviewNote || null,
                reviewReasonCode: reviewReasonCode || null,
                updatedAt: reviewedAt,
                updatedBy: admin.email,
                auditTrail: appendAuditTrail(
                    record,
                    createAuditEntry("REVIEW_STATUS_CHANGED", admin.email, {
                        recordId,
                        fromStatus: record.status,
                        toStatus: targetStatus,
                        reviewNote: reviewNote || null,
                        reviewReasonCode: reviewReasonCode || null
                    })
                )
            };

            await saveReviewedRecord(nextRecord);

            return {
                status: 200,
                jsonBody: {
                    message: "record reviewed",
                    recordId: nextRecord.id,
                    previousStatus: record.status,
                    status: nextRecord.status,
                    reviewNote: nextRecord.reviewNote,
                    reviewReasonCode: nextRecord.reviewReasonCode,
                    reviewedAt,
                    reviewedBy: nextRecord.reviewedBy
                }
            };
        } catch (error) {
            const errorMessage = error && error.message ? error.message : String(error);
            context.error("approve error:", errorMessage);

            if (error.code === "ADMIN_UNAUTHORIZED") {
                return { status: 401, body: errorMessage };
            }

            if (error.code === "ADMIN_NOT_FOUND" || error.code === "ADMIN_ACCESS_DENIED") {
                return { status: 403, body: errorMessage };
            }

            if (error.code === "RECORD_INVALID_STATE") {
                return badRequest("RECORD_INVALID_STATE", errorMessage);
            }

            if (/ECONNREFUSED|timeout|ENOTFOUND|connect|RestError/i.test(errorMessage)) {
                return { status: 503, body: "Records storage is unavailable" };
            }

            return { status: 500, body: "Internal Server Error" };
        }
    }
});
