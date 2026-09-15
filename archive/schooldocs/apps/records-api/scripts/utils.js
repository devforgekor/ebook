const fs = require("node:fs/promises");
const path = require("node:path");
const net = require("node:net");
const { spawnSync } = require("node:child_process");
const { BlobServiceClient } = require("@azure/storage-blob");

/**
 * 연결 문자열로 BlobServiceClient 인스턴스를 생성합니다.
 * @param {string} [connectionString] - Azure Storage 연결 문자열.
 *        생략 시 환경변수 STORAGE_CONNECTION_STRING 또는 개발 저장소를 사용합니다.
 * @returns {BlobServiceClient}
 */
function getBlobServiceClientFromConnectionString(connectionString) {
    const connStr =
        connectionString ||
        process.env.STORAGE_CONNECTION_STRING ||
        "UseDevelopmentStorage=true";
    return BlobServiceClient.fromConnectionString(connStr);
}

/**
 * 지정된 컨테이너의 모든 Blob을 삭제합니다.
 * @param {BlobServiceClient} blobServiceClient
 * @param {string} containerName
 */
async function clearBlobContainer(blobServiceClient, containerName) {
    const containerClient = blobServiceClient.getContainerClient(containerName);
    const exists = await containerClient.exists();
    if (!exists) {
        return;
    }
    for await (const blob of containerClient.listBlobsFlat()) {
        await containerClient.deleteBlob(blob.name, {
            deleteSnapshots: "include",
        });
    }
}

/**
 * Base64 인코딩된 데이터를 Blob으로 업로드합니다.
 * @param {BlobServiceClient} blobServiceClient
 * @param {string} containerName
 * @param {string} blobName
 * @param {string} contentBase64
 * @param {string} [contentType="application/pdf"]
 */
async function uploadSeedBlob(
    blobServiceClient,
    containerName,
    blobName,
    contentBase64,
    contentType = "application/pdf"
) {
    const containerClient = blobServiceClient.getContainerClient(containerName);
    await containerClient.createIfNotExists();
    const blobClient = containerClient.getBlockBlobClient(blobName);
    await blobClient.uploadData(Buffer.from(contentBase64, "base64"), {
        overwrite: true,
        blobHTTPHeaders: { blobContentType: contentType },
    });
}

/**
 * JSON 데이터를 파일로 저장합니다.
 * @param {string} dataDir
 * @param {string} fileName
 * @param {any} value
 */
async function writeJson(dataDir, fileName, value) {
    await fs.mkdir(dataDir, { recursive: true });
    const filePath = path.join(dataDir, fileName);
    await fs.writeFile(filePath, `${JSON.stringify(value, null, 2)}\n`, "utf8");
}

/**
 * 로컬 데이터 디렉터리를 삭제합니다.
 * @param {string} dataDir
 */
async function removeLocalDataDir(dataDir) {
    await fs.rm(dataDir, { recursive: true, force: true });
}

/**
 * 감사 항목 객체를 생성합니다.
 * @param {string} at - ISO 타임스탬프
 * @param {string} action - 작업 유형 (예: "SUBMIT", "REVIEW_STATUS_CHANGED")
 * @param {string} actor - 수행자 식별자
 * @param {object} details - 추가 세부 정보
 * @returns {object}
 */
function auditEntry(at, action, actor, details) {
    return { at, action, actor, details };
}

/**
 * Node.js 버전 문자열에서 주 버전 번호를 추출합니다.
 * @param {string} version - Node.js 버전 문자열 (예: "22.11.0")
 * @returns {number} 주 버전 번호
 */
function getMajor(version) {
    return Number(String(version).split(".")[0]);
}

/**
 * Node.js 버전을 검사합니다.
 * @param {number[]} [supportedMajors=[20, 22]] - 지원되는 Node.js 주 버전 목록
 */
function checkNodeVersion(supportedMajors = [20, 22]) {
    const major = getMajor(process.versions.node);
    if (!supportedMajors.includes(major)) {
        console.error(
            `Unsupported Node.js version v${process.versions.node}. Use Node ${supportedMajors.join(' or ')}.`
        );
        process.exit(1);
    }
    if (major === 20) {
        console.warn(`Node.js v${process.versions.node} is allowed, but Node 22 is recommended.`);
    } else {
        console.log(`Node.js version ok: v${process.versions.node}`);
    }
}

/**
 * 인수 배열에 --port 또는 -p 옵션이 포함되어 있는지 확인합니다.
 * @param {string[]} args
 * @returns {boolean}
 */
function hasPortArg(args) {
    return args.includes("--port") || args.includes("-p");
}

/**
 * 지정된 포트가 사용 가능한지 확인합니다.
 * @param {number} port
 * @returns {Promise<boolean>}
 */
function isPortAvailable(port) {
    return new Promise((resolve) => {
        // macOS/Homebrew environments are more reliable with lsof for port ownership checks.
        const lsofResult = spawnSync("lsof", ["-nP", `-iTCP:${port}`, "-sTCP:LISTEN", "-t"], {
            encoding: "utf8"
        });

        if (lsofResult.status === 0 && String(lsofResult.stdout || "").trim()) {
            resolve(false);
            return;
        }

        const server = net.createServer();

        server.once("error", () => resolve(false));
        server.once("listening", () => {
            server.close(() => resolve(true));
        });

        // Do not pin host so we detect conflicts on IPv4/IPv6 and any-address bindings.
        server.listen(port);
    });
}

/**
 * 사용자 인수에서 포트 옵션이 없으면 사용 가능한 포트를 찾아 추가합니다.
 * @param {string[]} userArgs
 * @returns {Promise<string[]>}
 */
async function resolvePortArgs(userArgs) {
    if (hasPortArg(userArgs)) {
        return userArgs;
    }

    const candidates = [7072, 7071, 7073];

    for (const port of candidates) {
        const available = await isPortAvailable(port);
        if (available) {
            console.log(`Using available port ${port}.`);
            return [...userArgs, "--port", String(port)];
        }
    }

    console.warn("No preferred ports available (7072, 7071, 7073). Falling back to default func port behavior.");
    return userArgs;
}

module.exports = {
    getBlobServiceClientFromConnectionString,
    clearBlobContainer,
    uploadSeedBlob,
    writeJson,
    removeLocalDataDir,
    auditEntry,
    getMajor,
    checkNodeVersion,
    hasPortArg,
    isPortAvailable,
    resolvePortArgs,
};