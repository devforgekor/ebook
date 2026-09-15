const path = require("node:path");
const {
    getBlobServiceClientFromConnectionString,
    clearBlobContainer,
    removeLocalDataDir,
} = require("./utils");

const ROOT_DIR = path.resolve(__dirname, "..");
const DATABASE_NAME = process.env.COSMOS_DATABASE || "CertificateSystem";
const DATA_DIR = path.join(ROOT_DIR, ".localdata", DATABASE_NAME);
const CONTAINER_NAME = process.env.STORAGE_CONTAINER || "record-files";

async function main() {
    await removeLocalDataDir(DATA_DIR);
    const blobServiceClient = getBlobServiceClientFromConnectionString();
    await clearBlobContainer(blobServiceClient, CONTAINER_NAME);
    console.log(`Reset local data at ${DATA_DIR}`);
}

main().catch((error) => {
    console.error(error);
    process.exitCode = 1;
});