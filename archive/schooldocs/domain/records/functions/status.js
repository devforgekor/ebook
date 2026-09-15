const { app } = require("@azure/functions");
const { getCosmosContainer } = require("../cosmos");
const { buildRegistryPersonKey } = require("../registry");

function getRegistryContainer() {
    return getCosmosContainer(process.env.COSMOS_REGISTRY_CONTAINER || "registry");
}

function getRecordsContainer() {
    return getCosmosContainer(process.env.COSMOS_CONTAINER || "records");
}

function buildLatestByDocumentType(items, sortField) {
    const latestMap = new Map();

    for (const item of items) {
        const documentType = item.documentType || "unknown";
        const current = latestMap.get(documentType);
        const itemSortValue = item?.[sortField] || "";
        const currentSortValue = current?.[sortField] || "";

        if (!current || itemSortValue > currentSortValue) {
            latestMap.set(documentType, item);
        }
    }

    return Object.fromEntries(latestMap.entries());
}

function buildCountsByDocumentType(items) {
    const counts = {};

    for (const item of items) {
        const documentType = item.documentType || "unknown";
        counts[documentType] = (counts[documentType] || 0) + 1;
    }

    return counts;
}

function buildCurrentStatus(latestRegistryByDocumentType, latestRecordByDocumentType, includeDetails) {
    const documentTypes = new Set([
        ...Object.keys(latestRegistryByDocumentType),
        ...Object.keys(latestRecordByDocumentType)
    ]);

    const summary = {};

    for (const documentType of documentTypes) {
        const registryItem = latestRegistryByDocumentType[documentType] || null;
        const recordItem = latestRecordByDocumentType[documentType] || null;

        const item = {
            documentType,
            registryStatus: registryItem ? registryItem.changeType : null,
            employmentStatus: registryItem ? registryItem.employmentStatus : null,
            submissionStatus: recordItem ? recordItem.status : null,
            canView: recordItem ? recordItem.status === "approved" : false,
            cohortId: recordItem ? recordItem.cohortId : null,
            personId: recordItem ? recordItem.personId : null,
            submittedYear: recordItem ? recordItem.submittedYear : null,
            validUntil: recordItem ? recordItem.validUntil : null,
            reviewedAt: recordItem ? recordItem.reviewedAt || null : null,
            reviewedBy: recordItem ? recordItem.reviewedBy || null : null,
            uploadBatchId: registryItem ? registryItem.uploadBatchId || null : null
        };

        if (includeDetails) {
            item.latestRecord = recordItem;
            item.latestRegistry = registryItem;
        }

        summary[documentType] = item;
    }

    return summary;
}

app.http("status", {
    methods: ["POST"],
    authLevel: "anonymous",
    route: "status",
    handler: async (request, context) => {
        try {
            const body = await request.json().catch(() => ({}));
            const name = typeof body.name === "string" ? body.name.trim() : "";
            const birthdate = typeof body.birthdate === "string" ? body.birthdate.trim() : "";
            const documentType = typeof body.documentType === "string" ? body.documentType.trim() : "";
            const personId = typeof body.personId === "string" ? body.personId.trim() : "";
            const dryRun = body.dryRun === true;
            const includeDetails = body.includeDetails === true;
            const includeCollections = body.includeCollections === true;

            const personKey = buildRegistryPersonKey(name, birthdate);

            if (!personKey) {
                return {
                    status: 400,
                    jsonBody: {
                        code: "INVALID_PERSON_INFO",
                        message: "필수 항목이 누락됐거나 형식이 잘못됐습니다: name, birthdate(YYYY-MM-DD)"
                    }
                };
            }

            if (dryRun) {
                return {
                    status: 200,
                    jsonBody: {
                        message: "status dry-run ok",
                        dryRun,
                        includeDetails,
                        includeCollections,
                        personKey,
                        filters: {
                            documentType: documentType || null,
                            personId: personId || null
                        }
                    }
                };
            }

            const registryContainer = getRegistryContainer();
            const registryQuery = documentType
                ? {
                    query: "SELECT * FROM c WHERE c.personKey = @personKey AND c.documentType = @documentType ORDER BY c.schoolYear DESC",
                    parameters: [
                        { name: "@personKey", value: personKey },
                        { name: "@documentType", value: documentType }
                    ]
                }
                : {
                    query: "SELECT * FROM c WHERE c.personKey = @personKey ORDER BY c.schoolYear DESC",
                    parameters: [{ name: "@personKey", value: personKey }]
                };

            const { resources: registryItems } = await registryContainer.items.query(registryQuery).fetchAll();

            const recordsContainer = getRecordsContainer();
            const recordsQuery = personId
                ? (documentType
                    ? {
                        query: "SELECT * FROM c WHERE c.personId = @personId AND c.documentType = @documentType ORDER BY c.submittedYear DESC",
                        parameters: [
                            { name: "@personId", value: personId },
                            { name: "@documentType", value: documentType }
                        ]
                    }
                    : {
                        query: "SELECT * FROM c WHERE c.personId = @personId ORDER BY c.submittedYear DESC",
                        parameters: [{ name: "@personId", value: personId }]
                    })
                : (documentType
                    ? {
                        query: "SELECT * FROM c WHERE c.personKey = @personKey AND c.documentType = @documentType ORDER BY c.submittedYear DESC",
                        parameters: [
                            { name: "@personKey", value: personKey },
                            { name: "@documentType", value: documentType }
                        ]
                    }
                    : {
                        query: "SELECT * FROM c WHERE c.personKey = @personKey ORDER BY c.submittedYear DESC",
                        parameters: [{ name: "@personKey", value: personKey }]
                    });

            const result = await recordsContainer.items.query(recordsQuery).fetchAll();
            const recordItems = result.resources;

            const latestRegistryByDocumentType = buildLatestByDocumentType(registryItems, "schoolYear");
            const latestRecordByDocumentType = buildLatestByDocumentType(recordItems, "updatedAt");
            const currentStatus = buildCurrentStatus(
                latestRegistryByDocumentType,
                latestRecordByDocumentType,
                includeDetails
            );

            return {
                status: 200,
                jsonBody: {
                    personKey,
                    currentStatus,
                    summary: {
                        includeDetails,
                        includeCollections,
                        registryCountByDocumentType: buildCountsByDocumentType(registryItems),
                        recordCountByDocumentType: buildCountsByDocumentType(recordItems),
                        ...(includeDetails
                            ? {
                                latestRegistryByDocumentType,
                                latestRecordByDocumentType
                            }
                            : {})
                    },
                    ...(includeCollections
                        ? {
                            registry: registryItems,
                            records: recordItems
                        }
                        : {}),
                    counts: {
                        registry: registryItems.length,
                        records: recordItems.length
                    }
                }
            };
        } catch (error) {
            const errorMessage = error && error.message ? error.message : String(error);
            context.error("status error:", errorMessage);

            if (/ECONNREFUSED|timeout|ENOTFOUND|connect|RestError/i.test(errorMessage)) {
                return {
                    status: 503,
                    jsonBody: {
                        code: "STORAGE_UNAVAILABLE",
                        message: "Status storage is unavailable"
                    }
                };
            }

            return {
                status: 500,
                jsonBody: {
                    code: "INTERNAL_SERVER_ERROR",
                    message: "Internal Server Error"
                }
            };
        }
    }
});
