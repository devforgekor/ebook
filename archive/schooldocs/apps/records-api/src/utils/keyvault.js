const { SecretClient } = require('@azure/keyvault-secrets');
const { DefaultAzureCredential } = require('@azure/identity');

const vaultUrl = process.env.KEYVAULT_URI;
if (!vaultUrl) {
  throw new Error('KEYVAULT_URI environment variable is not set');
}
const client = new SecretClient(vaultUrl, new DefaultAzureCredential());

async function getSecret(secretName) {
  const secret = await client.getSecret(secretName);
  return secret.value;
}

module.exports = { getSecret };
