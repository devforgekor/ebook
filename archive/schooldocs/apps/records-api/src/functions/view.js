const { app } = require("@azure/functions");
const { BlobServiceClient } = require("@azure/storage-blob");
const { getCosmosContainer } = require("../cosmos");
const { buildRegistryPersonKey } = require("../registry");

function jsonError(status, code, message, details) {
    return {
        status,
        jsonBody: {
            code,
            message,
            ...(details ? { details } : {})
        }
    };
}

function getRecordsContainer() {
    return getCosmosContainer(process.env.COSMOS_CONTAINER || "records");
}

function getBlobContainer() {
    const blobServiceClient = BlobServiceClient.fromConnectionString(
        process.env.STORAGE_CONNECTION_STRING
    );

    return blobServiceClient.getContainerClient(process.env.STORAGE_CONTAINER);
}

app.http("view", {
    methods: ["GET"],
    authLevel: "anonymous",
    route: "view/{cohortId}/{personId}",
    handler: async (request, context) => {
        try {
            const cohortId = (request.params?.cohortId || "").trim();
            const personId = (request.params?.personId || "").trim();
            const url = new URL(request.url);
            const documentType = (url.searchParams.get("documentType") || "").trim();
            const name = (url.searchParams.get("name") || "").trim();
            const birthdate = (url.searchParams.get("birthdate") || "").trim();
            const download = url.searchParams.get("download") === "true";
            const dryRun = url.searchParams.get("dryRun") === "true";
            const personKey = buildRegistryPersonKey(name, birthdate);

            if (!cohortId || !personId) {
                return jsonError(400, "MISSING_PATH_PARAMS", "cohortId와 personId가 필요합니다.");
            }

            if (!personKey) {
                return jsonError(400, "PERSON_VERIFICATION_REQUIRED", "name과 birthdate(YYYY-MM-DD)가 필요합니다.");
            }

            if (dryRun) {
                return {
                    status: 200,
                    jsonBody: {
                        message: "view dry-run ok",
                        dryRun,
                        cohortId,
                        personId,
                        documentType: documentType || null,
                        personKey,
                        download
                    }
                };
            }

            const recordsContainer = getRecordsContainer();
            const querySpec = documentType
                ? {
                    query: "SELECT * FROM c WHERE c.cohortId = @cohortId AND c.personId = @personId AND c.documentType = @documentType AND c.status = 'approved' ORDER BY c.updatedAt DESC",
                    parameters: [
                        { name: "@cohortId", value: cohortId },
                        { name: "@personId", value: personId },
                        { name: "@documentType", value: documentType }
                    ]
                }
                : {
                    query: "SELECT * FROM c WHERE c.cohortId = @cohortId AND c.personId = @personId AND c.status = 'approved' ORDER BY c.updatedAt DESC",
                    parameters: [
                        { name: "@cohortId", value: cohortId },
                        { name: "@personId", value: personId }
                    ]
                };

            const { resources } = await recordsContainer.items.query(querySpec).fetchAll();

            if (resources.length === 0) {
                return jsonError(404, "APPROVED_RECORD_NOT_FOUND", "approved record not found");
            }

            const record = resources[0];

            if (record.personKey && record.personKey !== personKey) {
                return jsonError(403, "PERSON_VERIFICATION_FAILED", "person verification failed");
            }

            if (!record.personKey) {
                const recordPersonKey = buildRegistryPersonKey(record.name, record.birthdate);
                if (!recordPersonKey || recordPersonKey !== personKey) {
                    return jsonError(403, "PERSON_VERIFICATION_FAILED", "person verification failed");
                }
            }

            const blobContainer = getBlobContainer();
            const blobClient = blobContainer.getBlockBlobClient(record.blobName);

            if (!(await blobClient.exists())) {
                return jsonError(404, "FILE_BLOB_NOT_FOUND", "file blob not found");
            }

            const buffer = await blobClient.downloadToBuffer();
            return {
                status: 200,
                headers: {
                    "Content-Type": "application/pdf",
                    "Content-Disposition": `${download ? "attachment" : "inline"}; filename="${record.fileName}"`,
                    "X-Record-Id": record.id,
                    "X-Document-Type": record.documentType
                },
                body: buffer
            };
        } catch (error) {
            const errorMessage = error && error.message ? error.message : String(error);
            context.error("view error:", errorMessage);

            if (/ECONNREFUSED|timeout|ENOTFOUND|connect|RestError/i.test(errorMessage)) {
                return jsonError(503, "VIEW_STORAGE_UNAVAILABLE", "View storage is unavailable");
            }

            return jsonError(500, "INTERNAL_SERVER_ERROR", "Internal Server Error");
        }
    }
});
