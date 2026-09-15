const { CosmosClient } = require("@azure/cosmos");
const { DefaultAzureCredential } = require("@azure/identity");

let client = null;

function getCosmosClient() {
  if (!client) {
    const endpoint = process.env.COSMOS_ENDPOINT;
    if (!endpoint) {
      throw new Error("COSMOS_ENDPOINT 환경 변수가 설정되지 않았습니다.");
    }
    client = new CosmosClient({
      endpoint,
      aadCredentials: new DefaultAzureCredential()
    });
  }
  return client;
}

function getCosmosContainer(containerName) {
  const databaseName = process.env.COSMOS_DATABASE || 'CertificateSystem';
  return getCosmosClient().database(databaseName).container(containerName);
}

module.exports = { getCosmosClient, getCosmosContainer };
