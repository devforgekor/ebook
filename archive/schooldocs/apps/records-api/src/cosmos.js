const { CosmosClient } = require("@azure/cosmos");
const { createLocalContainer } = require("./localCosmos");

let cosmosClient;
const localContainers = new Map();

function isLocalDataStoreEnabled() {
    return process.env.LOCAL_DATA_STORE === "true";
}

function getCosmosClient() {
    if (!cosmosClient) {
        cosmosClient = new CosmosClient(process.env.DATABASE_CONNECTION_STRING);
    }

    return cosmosClient;
}

function getCosmosContainer(containerName = process.env.COSMOS_CONTAINER) {
    if (isLocalDataStoreEnabled()) {
        if (!localContainers.has(containerName)) {
            localContainers.set(containerName, createLocalContainer(containerName));
        }

        return localContainers.get(containerName);
    }

    return getCosmosClient()
        .database(process.env.COSMOS_DATABASE)
        .container(containerName);
}

module.exports = {
    getCosmosClient,
    getCosmosContainer
};