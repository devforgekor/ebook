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

app.http("closeCohort", {
    methods: ["POST"],
    authLevel: "anonymous",
    route: "manage/close-cohort",
    handler: async (request, context) => {
        try {
            const admin = await resolveAdmin(request);
            const body = await request.json().catch(() => ({}));

            const cohortId = normalizeCohortId(body.cohortId);
            const deleteRejected = body.deleteRejected === true;
            const dryRun = body.dryRun === true;
            const documentType = parseDocumentTypeFromCohortId(cohortId);

            if (!cohortId) {
                return { status: 400, body: "cohortId가 필요합니다." };
            }

            if (!documentType) {
                return { status: 400, body: "cohortId에서 documentType을 추출할 수 없습니다." };
            }

            requireDocumentAccess(admin, documentType);

            if (dryRun) {
                return {
                    status: 200,
                    jsonBody: {
                        message: "close-cohort dry-run ok",
                        summary: {
                            cohortId,
                            documentType,
                            totalRecords: null,
                            rejectedRecords: null,
                            deleteRejected,
                            dryRun
                        }
                    }
                };
            }

            const recordsContainer = getRecordsContainer();
            const querySpec = {
                query: "SELECT c.id, c.cohortId, c.status, c.documentType FROM c WHERE c.cohortId = @cohortId",
                parameters: [{ name: "@cohortId", value: cohortId }]
            };
            const { resources } = await recordsContainer.items.query(querySpec).fetchAll();

            const rejected = resources.filter((item) => item.status === "rejected");
            const summary = {
                cohortId,
                documentType,
                totalRecords: resources.length,
                rejectedRecords: rejected.length,
                deleteRejected,
                dryRun
            };

            let deletedCount = 0;
            if (deleteRejected) {
                for (const item of rejected) {
                    const partitionKey = item.cohortId || cohortId;
                    await recordsContainer.item(item.id, partitionKey).delete();
                    deletedCount += 1;
                }
            }

            const now = new Date().toISOString();
            const registryContainer = getRegistryContainer();
            await registryContainer.items.upsert({
                id: `cohort_${cohortId}`,
                type: "cohort",
                cohortId,
                documentType,
                active: false,
                closedAt: now,
                closedBy: admin.email,
                deleteRejected,
                deletedCount,
                updatedAt: now,
                updatedBy: admin.email,
                auditTrail: [
                    createAuditEntry("CLOSE_COHORT", admin.email, {
                        cohortId,
                        documentType,
                        deleteRejected,
                        deletedCount
                    })
                ]
            });

            return {
                status: 200,
                jsonBody: {
                    message: "cohort closed",
                    summary: {
                        ...summary,
                        deletedCount
                    }
                }
            };
        } catch (error) {
            const errorMessage = error && error.message ? error.message : String(error);
            context.error("close-cohort error:", errorMessage);

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
