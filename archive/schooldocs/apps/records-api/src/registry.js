function normalizeName(name) {
    return String(name || "")
        .trim()
        .replace(/\s+/g, "")
        .normalize("NFC");
}

function normalizeBirthdate(birthdate) {
    const value = String(birthdate || "").trim();

    if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) {
        return "";
    }

    return value;
}

function normalizePhoneNumber(phoneNumber) {
    return String(phoneNumber || "").replace(/\D/g, "");
}

function buildRegistryPersonKey(name, birthdate) {
    const normalizedName = normalizeName(name);
    const normalizedBirthdate = normalizeBirthdate(birthdate);

    if (!normalizedName || !normalizedBirthdate) {
        return "";
    }

    return `${normalizedName}|${normalizedBirthdate}`;
}

function normalizeRegistryEntry(entry, year) {
    const normalizedName = normalizeName(entry?.name);
    const normalizedBirthdate = normalizeBirthdate(entry?.birthdate);
    const normalizedPhoneNumber = normalizePhoneNumber(entry?.phoneNumber);
    const personKey = buildRegistryPersonKey(normalizedName, normalizedBirthdate);

    if (!personKey) {
        return null;
    }

    return {
        name: normalizedName,
        birthdate: normalizedBirthdate,
        phoneNumber: normalizedPhoneNumber,
        year,
        personKey
    };
}

function compareRegistrySnapshots(previousEntries, currentEntries, year) {
    const previousMap = new Map();
    const currentMap = new Map();

    for (const entry of previousEntries || []) {
        const normalizedEntry = normalizeRegistryEntry(entry, year - 1);
        if (normalizedEntry) {
            previousMap.set(normalizedEntry.personKey, normalizedEntry);
        }
    }

    for (const entry of currentEntries || []) {
        const normalizedEntry = normalizeRegistryEntry(entry, year);
        if (normalizedEntry) {
            currentMap.set(normalizedEntry.personKey, normalizedEntry);
        }
    }

    const changes = [];
    const allKeys = new Set([...previousMap.keys(), ...currentMap.keys()]);

    for (const personKey of allKeys) {
        const previousEntry = previousMap.get(personKey);
        const currentEntry = currentMap.get(personKey);

        if (!previousEntry && currentEntry) {
            changes.push({
                ...currentEntry,
                changeType: "new"
            });
            continue;
        }

        if (previousEntry && currentEntry) {
            changes.push({
                ...currentEntry,
                changeType: "active"
            });
            continue;
        }

        if (previousEntry && !currentEntry) {
            changes.push({
                ...previousEntry,
                year,
                changeType: "retired"
            });
        }
    }

    return changes.sort((left, right) => left.personKey.localeCompare(right.personKey));
}

module.exports = {
    normalizeName,
    normalizeBirthdate,
    normalizePhoneNumber,
    buildRegistryPersonKey,
    normalizeRegistryEntry,
    compareRegistrySnapshots
};