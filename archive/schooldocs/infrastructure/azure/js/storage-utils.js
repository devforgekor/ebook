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

module.exports = {
    getBlobServiceClientFromConnectionString,
    clearBlobContainer,
    uploadSeedBlob,
};