const { app } = require('@azure/functions');
const { CosmosClient } = require('@azure/cosmos');
const { SecretClient } = require('@azure/keyvault-secrets');
const { DefaultAzureCredential } = require('@azure/identity');
const { BlobServiceClient, generateBlobSASQueryParameters, BlobSASPermissions, StorageSharedKeyCredential } = require('@azure/storage-blob');

let cosmosContainer = null;
let storageAccountName = null;
let credential = null;

async function initializeClients() {
  if (!cosmosContainer) {
    const vaultUrl = process.env.KEYVAULT_URI;
    const secretClient = new SecretClient(vaultUrl, new DefaultAzureCredential());
    
    // Cosmos DB 연결 문자열 (키리스 전환 전까지 임시 사용)
    const dbConnStr = (await secretClient.getSecret('connection-string-database')).value;
    
    // Storage 계정명만 가져오기 (연결 문자열 대신)
    const storageConnStr = (await secretClient.getSecret('connection-string-storage')).value;
    const accountNameMatch = storageConnStr.match(/AccountName=([^;]+)/);
    if (accountNameMatch) storageAccountName = accountNameMatch[1];

    credential = new DefaultAzureCredential();

    const cosmosClient = new CosmosClient(dbConnStr);
    const database = cosmosClient.database(process.env.COSMOS_DATABASE);
    cosmosContainer = database.container(process.env.COSMOS_CONTAINER);
  }
}

/**
 * User Delegation SAS URL 생성 (키리스 방식)
 */
async function generateSasUrl(blobName) {
  const containerName = process.env.STORAGE_CONTAINER_NAME || 'record-files';
  const blobServiceClient = new BlobServiceClient(
    `https://${storageAccountName}.blob.core.windows.net`,
    credential
  );

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

app.http('view', {
  methods: ['GET'],
  route: 'view/{recordId}',
  authLevel: 'anonymous',
  handler: async (request, context) => {
    try {
      await initializeClients();

      const recordId = request.params.recordId;
      const cohortId = recordId.split(':')[0];

      const { resource } = await cosmosContainer.item(recordId, cohortId).read();

      if (!resource || !resource.thumbnailPath) {
        return { status: 404, body: 'Image not found' };
      }

      const sasUrl = await generateSasUrl(resource.thumbnailPath);

      return {
        status: 302,
        headers: { Location: sasUrl }
      };
    } catch (err) {
      if (err.code === 404) {
        return { status: 404, body: 'Image not found' };
      }
      context.error(err);
      return { status: 500, body: 'Server error' };
    }
  }
});
