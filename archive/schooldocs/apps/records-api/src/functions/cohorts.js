const { app } = require("@azure/functions");
const { requireDocumentAccess } = require("../admins");
const { getCosmosContainer } = require("../cosmos");
const { resolveAdmin } = require("../adminAccess");
const { createAuditEntry } = require("../auditTrail");
const {
    parseDocumentTypeFromCohortId,
    normalizeCohortId
} = require("../cohortUtils");

function getRecordsContainer() {
    return getCosmosContainer(process.env.COSMOS_CONTAINER || "records");
}

function getRegistryContainer() {
    return getCosmosContainer(process.env.COSMOS_REGISTRY_CONTAINER || "registry");
}

function toBool(value) {
    return value === true || value === "true";
}

function buildCohortSummary(items) {
    const map = new Map();

    for (const item of items) {
        const cohortId = normalizeCohortId(item.cohortId);
        if (!cohortId) {
            continue;
        }

        const docType = parseDocumentTypeFromCohortId(cohortId) || (item.documentType || "").toLowerCase();
        if (!map.has(cohortId)) {
            map.set(cohortId, {
                cohortId,
                documentType: docType,
                total: 0,
                pending: 0,
                approved: 0,
                rejected: 0,
                updatedAt: item.updatedAt || item.createdAt || null
            });
        }

        const summary = map.get(cohortId);
        summary.total += 1;
        if (item.status === "pending" || item.status === "pending_ai" || item.status === "unknown") {
            summary.pending += 1;
        }
        if (item.status === "approved") {
            summary.approved += 1;
        }
        if (item.status === "rejected") {
            summary.rejected += 1;
        }

        const nextUpdatedAt = item.updatedAt || item.createdAt || null;
        if (!summary.updatedAt || (nextUpdatedAt && nextUpdatedAt > summary.updatedAt)) {
            summary.updatedAt = nextUpdatedAt;
        }
    }

    return [...map.values()].sort((a, b) => a.cohortId.localeCompare(b.cohortId));
}

app.http("cohorts", {
    methods: ["GET", "POST"],
    authLevel: "anonymous",
    route: "manage/cohorts",
    handler: async (request, context) => {
        try {
            const admin = await resolveAdmin(request);

            if (request.method === "GET") {
                const url = new URL(request.url);
                const documentType = (url.searchParams.get("documentType") || "").trim().toLowerCase();
                const dryRun = toBool(url.searchParams.get("dryRun"));

                if (documentType) {
                    requireDocumentAccess(admin, documentType);
                }

                if (dryRun) {
                    return {
                        status: 200,
                        jsonBody: {
                            message: "cohorts dry-run ok",
                            dryRun,
                            filters: {
                                documentType: documentType || null
                            }
                        }
                    };
                }

                const recordsContainer = getRecordsContainer();
                const querySpec = documentType
                    ? {
                        query: "SELECT c.cohortId, c.documentType, c.status, c.updatedAt, c.createdAt FROM c WHERE c.documentType = @documentType",
                        parameters: [{ name: "@documentType", value: documentType }]
                    }
                    : {
                        query: "SELECT c.cohortId, c.documentType, c.status, c.updatedAt, c.createdAt FROM c WHERE IS_DEFINED(c.cohortId)",
                        parameters: []
                    };

                const { resources } = await recordsContainer.items.query(querySpec).fetchAll();
                const summaries = buildCohortSummary(resources);
                const filtered = documentType
                    ? summaries
                    : summaries.filter((item) => {
                        if (admin.type === "super") {
                            return true;
                        }

                        return admin.allowedDocumentTypes.includes(item.documentType);
                    });

                return {
                    status: 200,
                    jsonBody: {
                        items: filtered,
                        count: filtered.length
                    }
                };
            }

            const body = await request.json().catch(() => ({}));
            const cohortId = normalizeCohortId(body.cohortId);
            const dryRun = body.dryRun === true;
            const active = body.active !== false;
            const documentType = (body.documentType || parseDocumentTypeFromCohortId(cohortId) || "").trim().toLowerCase();

            if (!cohortId || !documentType) {
                return { status: 400, body: "필수 항목이 누락됐습니다: cohortId, documentType" };
            }

            requireDocumentAccess(admin, documentType);

            const now = new Date().toISOString();
            const cohortDoc = {
                id: `cohort_${cohortId}`,
                type: "cohort",
                cohortId,
                documentType,
                active,
                title: typeof body.title === "string" ? body.title.trim() : "",
                schoolYear: Number(body.schoolYear || new Date().getUTCFullYear()),
                createdAt: now,
                updatedAt: now,
                updatedBy: admin.email,
                auditTrail: [
                    createAuditEntry("COHORT_UPSERT", admin.email, {
                        cohortId,
                        documentType,
                        active
                    })
                ]
            };

            if (dryRun) {
                return { status: 200, jsonBody: { message: "cohort upsert dry-run ok", dryRun, cohort: cohortDoc } };
            }

            const registryContainer = getRegistryContainer();
            await registryContainer.items.upsert(cohortDoc);

            return { status: 200, jsonBody: { message: "cohort upserted", cohort: cohortDoc } };
        } catch (error) {
            const errorMessage = error && error.message ? error.message : String(error);
            context.error("cohorts error:", errorMessage);

            if (error.code === "ADMIN_UNAUTHORIZED") {
                return { status: 401, body: errorMessage };
            }

            if (error.code === "ADMIN_NOT_FOUND" || error.code === "ADMIN_ACCESS_DENIED") {
                return { status: 403, body: errorMessage };
            }

            if (/ECONNREFUSED|timeout|ENOTFOUND|connect|RestError/i.test(errorMessage)) {
                return { status: 503, body: "Cohort storage is unavailable" };
            }

            return { status: 500, body: "Internal Server Error" };
        }
    }
});
