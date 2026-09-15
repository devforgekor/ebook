const { app } = require("@azure/functions");
const {
    requireDocumentAccess
} = require("../admins");
const { compareRegistrySnapshots } = require("../registry");
const { getCosmosContainer } = require("../cosmos");
const { resolveAdmin } = require("../adminAccess");

function buildRegistryPartitionKey(year) {
    return `registry_${year}`;
}

async function persistRegistryChanges(changes, year, uploadBatchId, documentType) {
    const registryContainer = getCosmosContainer(process.env.COSMOS_REGISTRY_CONTAINER || "registry");
    const partitionKey = buildRegistryPartitionKey(year);
    const now = new Date().toISOString();

    for (const change of changes) {
        await registryContainer.items.upsert({
            id: `${partitionKey}_${change.personKey}`,
            cohortId: partitionKey,
            type: "registry-member",
            uploadBatchId,
            schoolYear: year,
            documentType: documentType || null,
            personKey: change.personKey,
            name: change.name,
            birthdate: change.birthdate,
            phoneNumber: change.phoneNumber,
            changeType: change.changeType,
            employmentStatus: change.changeType === "retired" ? "retired" : "active",
            createdAt: now,
            updatedAt: now
        });
    }
}

app.http("uploadMembers", {
    methods: ["POST"],
    authLevel: "anonymous",
    route: "manage/upload-members",
    handler: async (request, context) => {
        try {
            const body = await request.json().catch(() => ({}));
            const year = Number(body.year);
            const previousEntries = Array.isArray(body.previousEntries) ? body.previousEntries : [];
            const currentEntries = Array.isArray(body.currentEntries) ? body.currentEntries : [];
            const documentType = body.documentType || null;
            const uploadBatchId = body.uploadBatchId || `registry_${year}_${Date.now()}`;
            const dryRun = body.dryRun === true;

            if (!year || currentEntries.length === 0) {
                return {
                    status: 400,
                    body: "필수 항목이 누락됐습니다: year, currentEntries"
                };
            }

            const admin = await resolveAdmin(request);

            if (documentType) {
                requireDocumentAccess(admin, documentType);
            }

            const changes = compareRegistrySnapshots(previousEntries, currentEntries, year);

            if (!dryRun) {
                await persistRegistryChanges(changes, year, uploadBatchId, documentType);
            }

            const summary = changes.reduce((result, item) => {
                result[item.changeType] = (result[item.changeType] || 0) + 1;
                return result;
            }, {});

            return {
                status: 200,
                jsonBody: {
                    message: "명단 업로드 비교가 완료됐습니다.",
                    uploadBatchId,
                    year,
                    documentType,
                    dryRun,
                    summary,
                    totalChanges: changes.length,
                    changes
                }
            };
        } catch (error) {
            const errorMessage = error && error.message ? error.message : String(error);
            context.error("upload-members error:", errorMessage);

            if (error.code === "ADMIN_UNAUTHORIZED") {
                return { status: 401, body: errorMessage };
            }

            if (error.code === "ADMIN_NOT_FOUND" || error.code === "ADMIN_ACCESS_DENIED") {
                return { status: 403, body: errorMessage };
            }

            if (/ECONNREFUSED|timeout|ENOTFOUND|connect|RestError/i.test(errorMessage)) {
                return { status: 503, body: "Registry storage is unavailable" };
            }

            return { status: 500, body: "Internal Server Error" };
        }
    }
});