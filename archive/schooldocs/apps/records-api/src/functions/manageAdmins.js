const { app } = require("@azure/functions");
const {
    ADMIN_TYPES,
    normalizeAdmin,
    normalizeAllowedDocumentTypes
} = require("../admins");
const { getCosmosContainer } = require("../cosmos");
const {
    normalizeEmail,
    resolveAdmin,
    assertSuperAdmin
} = require("../adminAccess");

function getAdminsContainer() {
    return getCosmosContainer(process.env.COSMOS_ADMINS_CONTAINER || "admins");
}

function buildAdminDocument(payload) {
    const email = normalizeEmail(payload.email);

    if (!email) {
        const error = new Error("email is required");
        error.code = "ADMIN_BAD_REQUEST";
        throw error;
    }

    const type = payload.type === ADMIN_TYPES.SUPER ? ADMIN_TYPES.SUPER : ADMIN_TYPES.SUB;
    const doc = {
        id: email,
        email,
        type,
        name: typeof payload.name === "string" ? payload.name.trim() : "",
        updatedAt: new Date().toISOString(),
        updatedBy: payload.updatedBy || "system"
    };

    if (type === ADMIN_TYPES.SUB) {
        doc.allowedDocumentTypes = normalizeAllowedDocumentTypes(payload.allowedDocumentTypes);
        if (doc.allowedDocumentTypes.length === 0) {
            const error = new Error("sub admin requires allowedDocumentTypes");
            error.code = "ADMIN_BAD_REQUEST";
            throw error;
        }
    }

    return doc;
}

async function listAdmins(type) {
    const adminsContainer = getAdminsContainer();

    const querySpec = type
        ? {
            query: "SELECT * FROM c WHERE c.type = @type ORDER BY c.email",
            parameters: [{ name: "@type", value: type }]
        }
        : {
            query: "SELECT * FROM c ORDER BY c.email",
            parameters: []
        };

    const { resources } = await adminsContainer.items.query(querySpec).fetchAll();
    return resources.map((item) => normalizeAdmin(item));
}

async function upsertAdmin(payload, actorEmail) {
    const adminDoc = buildAdminDocument({
        ...payload,
        updatedBy: actorEmail
    });

    const adminsContainer = getAdminsContainer();
    await adminsContainer.items.upsert({
        ...adminDoc,
        createdAt: adminDoc.updatedAt
    });

    return adminDoc;
}

async function deleteAdmin(targetEmail) {
    const email = normalizeEmail(targetEmail);

    if (!email) {
        const error = new Error("email is required");
        error.code = "ADMIN_BAD_REQUEST";
        throw error;
    }

    const adminsContainer = getAdminsContainer();
    await adminsContainer.item(email, email).delete();
    return email;
}

app.http("manageAdmins", {
    methods: ["GET", "POST"],
    authLevel: "anonymous",
    route: "manage/admins",
    handler: async (request, context) => {
        try {
            const admin = await resolveAdmin(request);
            assertSuperAdmin(admin);

            if (request.method === "GET") {
                const url = new URL(request.url);
                const type = url.searchParams.get("type") || "";
                const admins = await listAdmins(type || null);
                return { status: 200, jsonBody: { items: admins } };
            }

            const body = await request.json().catch(() => ({}));
            const action = body.action || "upsert";
            const dryRun = body.dryRun === true;

            if (action === "delete") {
                const email = normalizeEmail(body.email);

                if (!email) {
                    return { status: 400, body: "email is required" };
                }

                if (email === admin.email) {
                    return { status: 400, body: "cannot delete current admin" };
                }

                if (dryRun) {
                    return { status: 200, jsonBody: { message: "dry-run delete ok", email, dryRun } };
                }

                await deleteAdmin(email);
                return { status: 200, jsonBody: { message: "admin deleted", email } };
            }

            const payload = {
                email: body.email,
                type: body.type,
                name: body.name,
                allowedDocumentTypes: body.allowedDocumentTypes
            };

            const normalizedPreview = buildAdminDocument({
                ...payload,
                updatedBy: admin.email
            });

            if (dryRun) {
                return {
                    status: 200,
                    jsonBody: {
                        message: "dry-run upsert ok",
                        dryRun,
                        admin: normalizedPreview
                    }
                };
            }

            const saved = await upsertAdmin(payload, admin.email);
            return {
                status: 200,
                jsonBody: {
                    message: "admin upserted",
                    admin: saved
                }
            };
        } catch (error) {
            const errorMessage = error && error.message ? error.message : String(error);
            context.error("manage-admins error:", errorMessage);

            if (error.code === "ADMIN_UNAUTHORIZED") {
                return { status: 401, body: errorMessage };
            }

            if (
                error.code === "ADMIN_NOT_FOUND" ||
                error.code === "ADMIN_SUPER_REQUIRED" ||
                error.code === "ADMIN_ACCESS_DENIED"
            ) {
                return { status: 403, body: errorMessage };
            }

            if (error.code === "ADMIN_BAD_REQUEST") {
                return { status: 400, body: errorMessage };
            }

            if (/ECONNREFUSED|timeout|ENOTFOUND|connect|RestError/i.test(errorMessage)) {
                return { status: 503, body: "Admin storage is unavailable" };
            }

            return { status: 500, body: "Internal Server Error" };
        }
    }
});
