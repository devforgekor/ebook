const fs = require("node:fs/promises");
const path = require("node:path");

function getBaseDir() {
    return path.resolve(process.cwd(), ".localdata", process.env.COSMOS_DATABASE || "localdb");
}

async function ensureContainerFile(containerName) {
    const baseDir = getBaseDir();
    await fs.mkdir(baseDir, { recursive: true });

    const filePath = path.join(baseDir, `${containerName}.json`);

    try {
        await fs.access(filePath);
    } catch {
        await fs.writeFile(filePath, "[]\n", "utf8");
    }

    return filePath;
}

async function loadDocuments(containerName) {
    const filePath = await ensureContainerFile(containerName);
    const content = await fs.readFile(filePath, "utf8");

    try {
        const parsed = JSON.parse(content);
        return Array.isArray(parsed) ? parsed : [];
    } catch {
        return [];
    }
}

async function saveDocuments(containerName, documents) {
    const filePath = await ensureContainerFile(containerName);
    await fs.writeFile(filePath, `${JSON.stringify(documents, null, 2)}\n`, "utf8");
}

function getParameterMap(parameters = []) {
    return new Map(parameters.map((item) => [item.name, item.value]));
}

function resolveFieldValue(document, fieldExpression) {
    const normalized = fieldExpression
        .replace(/^LOWER\(/i, "")
        .replace(/\)$/i, "")
        .replace(/^c\./i, "")
        .trim();

    const value = document?.[normalized];
    return /LOWER\(/i.test(fieldExpression) ? String(value || "").toLowerCase() : value;
}

function parseLiteral(raw) {
    if (/^'.*'$/.test(raw)) {
        return raw.slice(1, -1);
    }

    if (/^@/.test(raw)) {
        return { parameter: raw };
    }

    if (/^\d+$/.test(raw)) {
        return Number(raw);
    }

    return raw;
}

function buildPredicate(expression, parameterMap) {
    const trimmed = expression.trim();

    if (!trimmed) {
        return () => true;
    }

    if (/^IS_DEFINED\(c\.[^)]+\)$/i.test(trimmed)) {
        const field = trimmed.match(/^IS_DEFINED\(c\.([^)]+)\)$/i)[1];
        return (document) => document[field] !== undefined;
    }

    const comparisonMatch = trimmed.match(/^(LOWER\(c\.[^)]+\)|c\.[A-Za-z0-9_]+)\s*=\s*(.+)$/i);
    if (!comparisonMatch) {
        return () => true;
    }

    const [, left, rightRaw] = comparisonMatch;
    const parsedRight = parseLiteral(rightRaw.trim());

    return (document) => {
        const leftValue = resolveFieldValue(document, left);
        const rightValue = parsedRight && parsedRight.parameter
            ? parameterMap.get(parsedRight.parameter)
            : parsedRight;

        return leftValue === rightValue;
    };
}

function evaluateWhere(document, whereClause, parameterMap) {
    if (!whereClause) {
        return true;
    }

    const orParts = whereClause.split(/\s+OR\s+/i);
    return orParts.some((orPart) => {
        const andParts = orPart.split(/\s+AND\s+/i);
        return andParts.every((andPart) => buildPredicate(andPart, parameterMap)(document));
    });
}

function applyQuery(documents, querySpec = {}) {
    const query = querySpec.query || "";
    const parameterMap = getParameterMap(querySpec.parameters);

    const whereMatch = query.match(/WHERE\s+(.+?)(ORDER BY|$)/i);
    const whereClause = whereMatch ? whereMatch[1].trim() : "";

    let results = documents.filter((document) => evaluateWhere(document, whereClause, parameterMap));

    const orderMatch = query.match(/ORDER BY\s+c\.([A-Za-z0-9_]+)\s+(ASC|DESC)/i);
    if (orderMatch) {
        const [, field, direction] = orderMatch;
        results = [...results].sort((left, right) => {
            const leftValue = left?.[field] ?? "";
            const rightValue = right?.[field] ?? "";

            if (leftValue === rightValue) {
                return 0;
            }

            const compare = leftValue > rightValue ? 1 : -1;
            return direction.toUpperCase() === "DESC" ? compare * -1 : compare;
        });
    }

    const topMatch = query.match(/SELECT\s+TOP\s+(@[A-Za-z0-9_]+|\d+)/i);
    if (topMatch) {
        const rawTop = topMatch[1];
        const topValue = rawTop.startsWith("@") ? parameterMap.get(rawTop) : Number(rawTop);
        results = results.slice(0, Number(topValue) || results.length);
    }

    return results;
}

function matchesPartitionKey(document, partitionKey) {
    if (partitionKey === undefined || partitionKey === null) {
        return true;
    }

    return [document.id, document.email, document.cohortId].includes(partitionKey);
}

function createLocalContainer(containerName) {
    return {
        items: {
            upsert: async (document) => {
                const documents = await loadDocuments(containerName);
                const index = documents.findIndex((item) => item.id === document.id);

                if (index >= 0) {
                    documents[index] = document;
                } else {
                    documents.push(document);
                }

                await saveDocuments(containerName, documents);
                return { resource: document };
            },
            query: (querySpec) => ({
                fetchAll: async () => {
                    const documents = await loadDocuments(containerName);
                    return { resources: applyQuery(documents, querySpec) };
                }
            })
        },
        item: (id, partitionKey) => ({
            read: async () => {
                const documents = await loadDocuments(containerName);
                const resource = documents.find((item) => item.id === id && matchesPartitionKey(item, partitionKey)) || null;
                return { resource };
            },
            delete: async () => {
                const documents = await loadDocuments(containerName);
                const nextDocuments = documents.filter((item) => !(item.id === id && matchesPartitionKey(item, partitionKey)));
                await saveDocuments(containerName, nextDocuments);
                return {};
            }
        })
    };
}

module.exports = {
    createLocalContainer
};