const { app } = require("@azure/functions");
const { BlobServiceClient } = require("@azure/storage-blob");
const { createHash } = require("node:crypto");
const path = require("node:path");
const { getCosmosContainer } = require("../cosmos");
const {
    getDocumentPolicy,
    calculateValidUntil,
    getCohortId,
    buildRecordId
} = require("../documentTypes");
const { buildRegistryPersonKey } = require("../registry");
const { createAuditEntry } = require("../auditTrail");

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

async function assertCohortIsOpen(cohortId) {
    const registryContainer = getCosmosContainer(process.env.COSMOS_REGISTRY_CONTAINER || "registry");
    const { resource } = await registryContainer.item(`cohort_${cohortId}`).read();

    if (resource && resource.active === false) {
        const error = new Error(`closed cohort: ${cohortId}`);
        error.code = "COHORT_CLOSED";
        throw error;
    }
}

app.http("submit", {
    methods: ["GET", "POST"],
    authLevel: "anonymous",
    route: "submit",
    handler: async (request, context) => {
        try {
            if (request.method === "POST") {
                return await handlePost(request, context);
            } else {
                return await handleGet(request, context);
            }
        } catch (err) {
            context.error("records-api error:", err.message);

            if (err.code === "COHORT_CLOSED") {
                return jsonError(409, "COHORT_CLOSED", err.message);
            }

            if (/ECONNREFUSED|timeout|ENOTFOUND|connect|RestError/i.test(String(err.message || ""))) {
                return jsonError(503, "STORAGE_UNAVAILABLE", "Records storage is unavailable");
            }

            return jsonError(500, "INTERNAL_SERVER_ERROR", "Internal Server Error");
        }
    }
});

async function handlePost(request, context) {
    const body = await request.json().catch(() => ({}));
    const personId = body.personId || body.studentId;
    const documentType = body.documentType || body.recordType;
    const { fileName, fileContent } = body;
    const name = typeof body.name === "string" ? body.name.trim() : "";
    const birthdate = typeof body.birthdate === "string" ? body.birthdate.trim() : "";
    const submittedYear = Number(body.submittedYear || new Date().getUTCFullYear());

    if (!personId || !documentType || !fileName || !fileContent) {
        return jsonError(
            400,
            "MISSING_REQUIRED_FIELDS",
            "필수 항목이 누락됐습니다: personId(or studentId), documentType(or recordType), fileName, fileContent"
        );
    }

    const policy = getDocumentPolicy(documentType);

    if (!policy) {
        return jsonError(
            400,
            "INVALID_DOCUMENT_TYPE",
            `지원하지 않는 documentType 입니다: ${documentType}`,
            {
                documentType
            }
        );
    }

    const uploadedAt = new Date().toISOString();
    const validUntil = calculateValidUntil(uploadedAt, policy.validityYears);
    const cohortId = getCohortId(documentType, submittedYear);
    const fileBuffer = Buffer.from(fileContent, "base64");
    const fileHash = createHash("sha256").update(fileBuffer).digest("hex");
    const recordId = buildRecordId(personId, documentType, submittedYear);
    const personKey = buildRegistryPersonKey(name, birthdate) || null;
    const extension = path.extname(fileName) || ".bin";

    await assertCohortIsOpen(cohortId);

    const blobServiceClient = BlobServiceClient.fromConnectionString(
        process.env.STORAGE_CONNECTION_STRING
    );
    const blobContainer = blobServiceClient.getContainerClient(
        process.env.STORAGE_CONTAINER
    );
    await blobContainer.createIfNotExists();

    const blobName = `${documentType}/${submittedYear}/${personId}/${recordId}${extension}`;
    const blockBlobClient = blobContainer.getBlockBlobClient(blobName);
    await blockBlobClient.uploadData(fileBuffer, { overwrite: true });

    const record = {
        id: recordId,
        studentId: personId,
        personId,
        documentType,
        recordType: documentType,
        policyVersion: 1,
        submittedYear,
        cohortId,
        validUntil,
        fileHash,
        personKey: personKey || undefined,
        name: name || undefined,
        birthdate: birthdate || undefined,
        status: "approved",
        fileName,
        blobName,
        uploadedAt,
        createdAt: uploadedAt,
        createdBy: "system",
        updatedAt: uploadedAt,
        updatedBy: "system",
        auditTrail: [
            createAuditEntry("SUBMIT", "system", {
                recordId,
                documentType,
                submittedYear
            })
        ]
    };
    await getCosmosContainer().items.upsert(record);

    return {
        status: 201,
        jsonBody: {
            message: "레코드가 저장됐습니다.",
            recordId: record.id,
            documentType,
            validUntil,
            cohortId
        }
    };
}

async function handleGet(request, context) {
    const url = new URL(request.url);
    const studentId = url.searchParams.get("studentId") || url.searchParams.get("personId");
    const documentType = url.searchParams.get("documentType") || url.searchParams.get("recordType");

    if (!studentId) {
        return jsonError(400, "MISSING_STUDENT_ID", "studentId 쿼리 파라미터가 필요합니다.");
    }

    const query = documentType
        ? {
            query: "SELECT * FROM c WHERE c.studentId = @studentId AND c.documentType = @documentType ORDER BY c.uploadedAt DESC",
            parameters: [
                { name: "@studentId", value: studentId },
                { name: "@documentType", value: documentType }
            ]
        }
        : {
            query: "SELECT * FROM c WHERE c.studentId = @studentId ORDER BY c.uploadedAt DESC",
            parameters: [{ name: "@studentId", value: studentId }]
        };
    const { resources } = await getCosmosContainer().items.query(query).fetchAll();

    return { status: 200, jsonBody: resources };
}
