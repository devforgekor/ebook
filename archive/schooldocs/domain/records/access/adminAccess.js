const { ADMIN_TYPES, normalizeAdmin } = require("./admins");
const { getCosmosContainer } = require("./cosmos");

function normalizeEmail(value) {
    if (typeof value !== "string") {
        return "";
    }

    return value.trim().toLowerCase();
}

function parseAllowedTypesHeader(value) {
    if (typeof value !== "string" || !value.trim()) {
        return [];
    }

    return value
        .split(",")
        .map((item) => item.trim())
        .filter(Boolean);
}

async function findAdminByEmail(adminsContainer, email) {
    const normalizedEmail = normalizeEmail(email);

    if (!normalizedEmail) {
        return null;
    }

    try {
        const { resource } = await adminsContainer.item(normalizedEmail, normalizedEmail).read();
        if (resource) {
            return resource;
        }
    } catch (error) {
        // Query fallback handles schema and partition-key differences.
    }

    const querySpec = {
        query: "SELECT TOP 1 * FROM c WHERE LOWER(c.email) = @email OR LOWER(c.id) = @email",
        parameters: [{ name: "@email", value: normalizedEmail }]
    };

    const { resources } = await adminsContainer.items.query(querySpec).fetchAll();
    return resources[0] || null;
}

async function resolveAdmin(request) {
    if (process.env.LOCAL_ADMIN_BYPASS === "true") {
        return normalizeAdmin({
            email: normalizeEmail(request.headers.get("x-admin-email") || "local-admin@example.com"),
            type: request.headers.get("x-admin-type") || ADMIN_TYPES.SUPER,
            allowedDocumentTypes: parseAllowedTypesHeader(request.headers.get("x-admin-allowed-types"))
        });
    }

    const email = normalizeEmail(request.headers.get("x-ms-client-principal-name"));

    if (!email) {
        const error = new Error("Unauthorized");
        error.code = "ADMIN_UNAUTHORIZED";
        throw error;
    }

    const adminsContainer = getCosmosContainer(process.env.COSMOS_ADMINS_CONTAINER || "admins");
    const resource = await findAdminByEmail(adminsContainer, email);

    if (!resource) {
        const error = new Error("Admin not found");
        error.code = "ADMIN_NOT_FOUND";
        throw error;
    }

    return normalizeAdmin(resource);
}

function assertSuperAdmin(admin) {
    if (!admin || admin.type !== ADMIN_TYPES.SUPER) {
        const error = new Error("Super admin only");
        error.code = "ADMIN_SUPER_REQUIRED";
        throw error;
    }
}

module.exports = {
    normalizeEmail,
    findAdminByEmail,
    resolveAdmin,
    assertSuperAdmin
};
