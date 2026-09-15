const { BlobServiceClient, generateBlobSASQueryParameters, BlobSASPermissions } = require("@azure/storage-blob");
const { DefaultAzureCredential } = require("@azure/identity");
const fs = require("fs").promises;

let blobServiceClient = null;
let storageAccountName = null;

function getBlobServiceClient() {
  if (!blobServiceClient) {
    storageAccountName = process.env.STORAGE_ACCOUNT_NAME;
    if (!storageAccountName) {
      throw new Error("STORAGE_ACCOUNT_NAME 환경 변수가 설정되지 않았습니다.");
    }
    const blobServiceUrl = `https://${storageAccountName}.blob.core.windows.net`;
    blobServiceClient = new BlobServiceClient(blobServiceUrl, new DefaultAzureCredential());
  }
  return blobServiceClient;
}

async function uploadToBlob(filePath, blobName) {
  const containerName = process.env.STORAGE_CONTAINER_NAME || 'record-files';
  const containerClient = getBlobServiceClient().getContainerClient(containerName);
  const blockBlobClient = containerClient.getBlockBlobClient(blobName);

  const fileBuffer = await fs.readFile(filePath);
  await blockBlobClient.upload(fileBuffer, fileBuffer.length);
  return blobName;
}

async function generateSasUrl(blobName) {
  const containerName = process.env.STORAGE_CONTAINER_NAME || 'record-files';
  const blobServiceClient = getBlobServiceClient();
  const containerClient = blobServiceClient.getContainerClient(containerName);
  const blockBlobClient = containerClient.getBlockBlobClient(blobName);

  // User Delegation Key 가져오기 (유효기간 10분)
  const delegationKey = await blobServiceClient.getUserDelegationKey(
    new Date(Date.now()),
    new Date(Date.now() + 10 * 60 * 1000)
  );

  const sasToken = generateBlobSASQueryParameters({
    containerName,
    blobName,
    permissions: BlobSASPermissions.parse('r'),
    expiresOn: new Date(Date.now() + 10 * 60 * 1000)
  }, delegationKey, storageAccountName).toString();

  return `${blockBlobClient.url}?${sasToken}`;
}

module.exports = { uploadToBlob, generateSasUrl };
