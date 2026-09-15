const { app } = require('@azure/functions');
const { CosmosClient } = require('@azure/cosmos');
const { SecretClient } = require('@azure/keyvault-secrets');
const { DefaultAzureCredential } = require('@azure/identity');
const crypto = require('crypto');

let cosmosContainer = null;
let hmacKey = null;
let aesKey = null;

async function initializeClients() {
  if (!cosmosContainer) {
    const vaultUrl = process.env.KEYVAULT_URI;
    const secretClient = new SecretClient(vaultUrl, new DefaultAzureCredential());
    
    const dbConnStr = (await secretClient.getSecret('connection-string-database')).value;
    
    const hmacHex = (await secretClient.getSecret('encryption-key-hmac')).value;
    hmacKey = Buffer.from(hmacHex, 'hex');
    
    const aesHex = (await secretClient.getSecret('encryption-key-aes')).value;
    aesKey = Buffer.from(aesHex, 'hex');

    const cosmosClient = new CosmosClient(dbConnStr);
    const database = cosmosClient.database(process.env.COSMOS_DATABASE);
    cosmosContainer = database.container(process.env.COSMOS_CONTAINER);
  }
}

function hashPersonId(name, birthdate) {
  const normalizedName = name.normalize('NFC').trim().replace(/\s+/g, ' ');
  const message = `personId|${normalizedName}|${birthdate}`;
  return crypto.createHmac('sha256', hmacKey).update(message).digest('hex');
}

function decrypt(encryptedText) {
  const parts = encryptedText.split(':');
  if (parts.length !== 2) {
    throw new Error('Invalid encrypted format');
  }
  const iv = Buffer.from(parts[0], 'hex');
  const encrypted = parts[1];
  const decipher = crypto.createDecipheriv('aes-256-cbc', aesKey, iv);
  let decrypted = decipher.update(encrypted, 'hex', 'utf8');
  decrypted += decipher.final('utf8');
  return decrypted;
}

function getCohortId(documentType, submittedYear) {
  return `${documentType}_${submittedYear}`;
}

app.http('status', {
  methods: ['POST'],
  authLevel: 'anonymous',
  handler: async (request, context) => {
    try {
      await initializeClients();

      const body = await request.json();
      const { name, birthdate, documentType, submittedYear } = body;

      if (!name || !birthdate || !documentType || !submittedYear) {
        return { status: 400, body: JSON.stringify({ error: '필수 항목 누락' }) };
      }

      const personKey = hashPersonId(name, birthdate);
      const cohortId = getCohortId(documentType, submittedYear);
      const recordId = `${cohortId}:${personKey}`;

      const { resource } = await cosmosContainer.item(recordId, cohortId).read();

      if (!resource || resource.type !== 'submission') {
        return { status: 404, body: JSON.stringify({ message: '제출 내역 없음' }) };
      }

      let decryptedName = null;
      try {
        decryptedName = decrypt(resource.nameEncrypted);
      } catch (decryptErr) {
        context.error('Failed to decrypt name:', decryptErr);
        decryptedName = '[복호화 오류]';
      }

      return {
        status: 200,
        body: JSON.stringify({
          id: resource.id,
          name: decryptedName,
          status: resource.status,
          submittedAt: resource.submittedAt,
          cohortId: resource.cohortId,
          hasImage: !!resource.thumbnailPath
        })
      };
    } catch (err) {
      if (err.code === 404) {
        return { status: 404, body: JSON.stringify({ message: '제출 내역 없음' }) };
      }
      context.error(err);
      return { status: 500, body: JSON.stringify({ error: '서버 오류' }) };
    }
  }
});
