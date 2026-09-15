const path = require("node:path");
const {
    getBlobServiceClientFromConnectionString,
    uploadSeedBlob,
    writeJson,
    auditEntry,
} = require("./utils");

const ROOT_DIR = path.resolve(__dirname, "..");
const DATABASE_NAME = process.env.COSMOS_DATABASE || "CertificateSystem";
const DATA_DIR = path.join(ROOT_DIR, ".localdata", DATABASE_NAME);
const CONTAINER_NAME = process.env.STORAGE_CONTAINER || "record-files";

async function main() {
    const admins = [
        {
            id: "superadmin@example.com",
            email: "superadmin@example.com",
            type: "super",
            name: "총관리자",
            createdAt: "2026-04-11T09:00:00.000Z",
            updatedAt: "2026-04-11T09:00:00.000Z",
            updatedBy: "seed",
        },
        {
            id: "subsafe@example.com",
            email: "subsafe@example.com",
            type: "sub",
            name: "안전부관리자",
            allowedDocumentTypes: ["safety"],
            createdAt: "2026-04-11T09:00:00.000Z",
            updatedAt: "2026-04-11T09:00:00.000Z",
            updatedBy: "seed",
        },
    ];

    const records = [
        {
            id: "safety_teacher-001_2026",
            studentId: "teacher-001",
            personId: "teacher-001",
            documentType: "safety",
            recordType: "safety",
            policyVersion: 1,
            submittedYear: 2026,
            cohortId: "safety_2024-2026",
            validUntil: "2028-12-31T23:59:59.999Z",
            fileHash: "seed-hash-safety-001",
            personKey: "홍길동|1990-01-01",
            name: "홍길동",
            birthdate: "1990-01-01",
            status: "approved",
            fileName: "seed-safety.pdf",
            blobName: "safety/2026/teacher-001/safety_teacher-001_2026.pdf",
            uploadedAt: "2026-04-11T09:10:00.000Z",
            createdAt: "2026-04-11T09:10:00.000Z",
            createdBy: "seed",
            updatedAt: "2026-04-11T09:20:00.000Z",
            updatedBy: "superadmin@example.com",
            reviewedAt: "2026-04-11T09:20:00.000Z",
            reviewedBy: "superadmin@example.com",
            reviewNote: "seed approved",
            auditTrail: [
                auditEntry("2026-04-11T09:10:00.000Z", "SUBMIT", "seed", {
                    recordId: "safety_teacher-001_2026",
                    documentType: "safety",
                    submittedYear: 2026,
                }),
                auditEntry("2026-04-11T09:20:00.000Z", "REVIEW_STATUS_CHANGED", "superadmin@example.com", {
                    recordId: "safety_teacher-001_2026",
                    fromStatus: "pending",
                    toStatus: "approved",
                }),
            ],
        },
        {
            id: "integrity_teacher-002_2026",
            studentId: "teacher-002",
            personId: "teacher-002",
            documentType: "integrity",
            recordType: "integrity",
            policyVersion: 1,
            submittedYear: 2026,
            cohortId: "integrity_2026",
            validUntil: "2026-12-31T23:59:59.999Z",
            fileHash: "seed-hash-integrity-002",
            personKey: "김영희|1992-02-02",
            name: "김영희",
            birthdate: "1992-02-02",
            status: "pending",
            fileName: "seed-integrity.pdf",
            blobName: "integrity/2026/teacher-002/integrity_teacher-002_2026.pdf",
            uploadedAt: "2026-04-11T09:30:00.000Z",
            createdAt: "2026-04-11T09:30:00.000Z",
            createdBy: "seed",
            updatedAt: "2026-04-11T09:30:00.000Z",
            updatedBy: "seed",
            auditTrail: [
                auditEntry("2026-04-11T09:30:00.000Z", "SUBMIT", "seed", {
                    recordId: "integrity_teacher-002_2026",
                    documentType: "integrity",
                    submittedYear: 2026,
                }),
            ],
        },
        {
            id: "mandatory_teacher-003_2026",
            studentId: "teacher-003",
            personId: "teacher-003",
            documentType: "mandatory",
            recordType: "mandatory",
            policyVersion: 1,
            submittedYear: 2026,
            cohortId: "mandatory_2026",
            validUntil: "2026-12-31T23:59:59.999Z",
            fileHash: "seed-hash-mandatory-003",
            personKey: "박철수|1987-07-07",
            name: "박철수",
            birthdate: "1987-07-07",
            status: "rejected",
            fileName: "seed-mandatory.pdf",
            blobName: "mandatory/2026/teacher-003/mandatory_teacher-003_2026.pdf",
            uploadedAt: "2026-04-11T09:40:00.000Z",
            createdAt: "2026-04-11T09:40:00.000Z",
            createdBy: "seed",
            updatedAt: "2026-04-11T09:50:00.000Z",
            updatedBy: "superadmin@example.com",
            reviewedAt: "2026-04-11T09:50:00.000Z",
            reviewedBy: "superadmin@example.com",
            reviewNote: "seed rejected",
            auditTrail: [
                auditEntry("2026-04-11T09:40:00.000Z", "SUBMIT", "seed", {
                    recordId: "mandatory_teacher-003_2026",
                    documentType: "mandatory",
                    submittedYear: 2026,
                }),
                auditEntry("2026-04-11T09:50:00.000Z", "REVIEW_STATUS_CHANGED", "superadmin@example.com", {
                    recordId: "mandatory_teacher-003_2026",
                    fromStatus: "pending",
                    toStatus: "rejected",
                    reviewNote: "seed rejected",
                }),
            ],
        },
        {
            id: "safety_teacher-004_2026",
            studentId: "teacher-004",
            personId: "teacher-004",
            documentType: "safety",
            recordType: "safety",
            policyVersion: 1,
            submittedYear: 2026,
            cohortId: "safety_2024-2026",
            validUntil: "2028-12-31T23:59:59.999Z",
            fileHash: "seed-hash-safety-004",
            personKey: "이민수|1985-05-05",
            name: "이민수",
            birthdate: "1985-05-05",
            status: "pending_ai",
            fileName: "seed-safety-ai.pdf",
            blobName: "safety/2026/teacher-004/safety_teacher-004_2026.pdf",
            uploadedAt: "2026-04-11T09:55:00.000Z",
            createdAt: "2026-04-11T09:55:00.000Z",
            createdBy: "seed",
            updatedAt: "2026-04-11T09:55:00.000Z",
            updatedBy: "seed",
            auditTrail: [
                auditEntry("2026-04-11T09:55:00.000Z", "SUBMIT", "seed", {
                    recordId: "safety_teacher-004_2026",
                    documentType: "safety",
                    submittedYear: 2026,
                }),
            ],
        },
        {
            id: "integrity_teacher-005_2026",
            studentId: "teacher-005",
            personId: "teacher-005",
            documentType: "integrity",
            recordType: "integrity",
            policyVersion: 1,
            submittedYear: 2026,
            cohortId: "integrity_2026",
            validUntil: "2026-12-31T23:59:59.999Z",
            fileHash: "seed-hash-integrity-005",
            personKey: "정수진|1991-11-11",
            name: "정수진",
            birthdate: "1991-11-11",
            status: "unknown",
            fileName: "seed-integrity-unknown.pdf",
            blobName: "integrity/2026/teacher-005/integrity_teacher-005_2026.pdf",
            uploadedAt: "2026-04-11T09:58:00.000Z",
            createdAt: "2026-04-11T09:58:00.000Z",
            createdBy: "seed",
            updatedAt: "2026-04-11T09:58:00.000Z",
            updatedBy: "seed",
            auditTrail: [
                auditEntry("2026-04-11T09:58:00.000Z", "SUBMIT", "seed", {
                    recordId: "integrity_teacher-005_2026",
                    documentType: "integrity",
                    submittedYear: 2026,
                }),
            ],
        },
    ];

    const registry = [
        {
            id: "registry_2026_홍길동|1990-01-01",
            cohortId: "registry_2026",
            type: "registry-member",
            uploadBatchId: "seed_batch_2026_01",
            schoolYear: 2026,
            documentType: "safety",
            personKey: "홍길동|1990-01-01",
            name: "홍길동",
            birthdate: "1990-01-01",
            phoneNumber: "01033334444",
            changeType: "active",
            employmentStatus: "active",
            createdAt: "2026-04-11T09:05:00.000Z",
            updatedAt: "2026-04-11T09:05:00.000Z",
        },
        {
            id: "registry_2026_김영희|1992-02-02",
            cohortId: "registry_2026",
            type: "registry-member",
            uploadBatchId: "seed_batch_2026_01",
            schoolYear: 2026,
            documentType: "integrity",
            personKey: "김영희|1992-02-02",
            name: "김영희",
            birthdate: "1992-02-02",
            phoneNumber: "01055556666",
            changeType: "new",
            employmentStatus: "active",
            createdAt: "2026-04-11T09:05:00.000Z",
            updatedAt: "2026-04-11T09:05:00.000Z",
        },
        {
            id: "cohort_safety_2024-2026",
            type: "cohort",
            cohortId: "safety_2024-2026",
            documentType: "safety",
            active: true,
            title: "안전 1기",
            schoolYear: 2026,
            createdAt: "2026-04-11T09:00:00.000Z",
            updatedAt: "2026-04-11T09:00:00.000Z",
            updatedBy: "seed",
            auditTrail: [
                auditEntry("2026-04-11T09:00:00.000Z", "COHORT_UPSERT", "seed", {
                    cohortId: "safety_2024-2026",
                    documentType: "safety",
                    active: true,
                }),
            ],
        },
        {
            id: "cohort_integrity_2026",
            type: "cohort",
            cohortId: "integrity_2026",
            documentType: "integrity",
            active: true,
            title: "청렴 2026",
            schoolYear: 2026,
            createdAt: "2026-04-11T09:00:00.000Z",
            updatedAt: "2026-04-11T09:00:00.000Z",
            updatedBy: "seed",
            auditTrail: [
                auditEntry("2026-04-11T09:00:00.000Z", "COHORT_UPSERT", "seed", {
                    cohortId: "integrity_2026",
                    documentType: "integrity",
                    active: true,
                }),
            ],
        },
        {
            id: "cohort_mandatory_2026",
            type: "cohort",
            cohortId: "mandatory_2026",
            documentType: "mandatory",
            active: true,
            title: "의무 2026",
            schoolYear: 2026,
            createdAt: "2026-04-11T09:00:00.000Z",
            updatedAt: "2026-04-11T09:00:00.000Z",
            updatedBy: "seed",
            auditTrail: [
                auditEntry("2026-04-11T09:00:00.000Z", "COHORT_UPSERT", "seed", {
                    cohortId: "mandatory_2026",
                    documentType: "mandatory",
                    active: true,
                }),
            ],
        },
    ];

    await writeJson(DATA_DIR, "admins.json", admins);
    await writeJson(DATA_DIR, "records.json", records);
    await writeJson(DATA_DIR, "registry.json", registry);

    const blobServiceClient = getBlobServiceClientFromConnectionString();
    // Minimal PDF-like payloads for local view/download testing.
    await uploadSeedBlob(blobServiceClient, CONTAINER_NAME, "safety/2026/teacher-001/safety_teacher-001_2026.pdf", "JVBERi0xLjQKJUVPRgo=");
    await uploadSeedBlob(blobServiceClient, CONTAINER_NAME, "integrity/2026/teacher-002/integrity_teacher-002_2026.pdf", "JVBERi0xLjQKJUVPRgo=");
    await uploadSeedBlob(blobServiceClient, CONTAINER_NAME, "mandatory/2026/teacher-003/mandatory_teacher-003_2026.pdf", "JVBERi0xLjQKJUVPRgo=");
    await uploadSeedBlob(blobServiceClient, CONTAINER_NAME, "safety/2026/teacher-004/safety_teacher-004_2026.pdf", "JVBERi0xLjQKJUVPRgo=");
    await uploadSeedBlob(blobServiceClient, CONTAINER_NAME, "integrity/2026/teacher-005/integrity_teacher-005_2026.pdf", "JVBERi0xLjQKJUVPRgo=");

    console.log(`Seeded local data at ${DATA_DIR}`);
}

main().catch((error) => {
    console.error(error);
    process.exitCode = 1;
});