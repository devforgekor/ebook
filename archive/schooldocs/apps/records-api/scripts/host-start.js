const fs = require("node:fs");
const path = require("node:path");
const { spawn } = require("node:child_process");
const { getMajor, hasPortArg, isPortAvailable, resolvePortArgs } = require("./utils");

const SUPPORTED_MAJORS = new Set([20, 22]);

function firstExistingNodeBin(candidates) {
    for (const candidate of candidates) {
        if (fs.existsSync(candidate)) {
            return path.dirname(candidate);
        }
    }

    return null;
}

function resolveNodeBinPrefix() {
    const currentVersion = process.versions.node;
    const currentMajor = getMajor(currentVersion);

    if (SUPPORTED_MAJORS.has(currentMajor)) {
        return null;
    }

    const fallbackDir = firstExistingNodeBin([
        "/opt/homebrew/opt/node@22/bin/node",
        "/opt/homebrew/opt/node@20/bin/node"
    ]);

    if (!fallbackDir) {
        console.error(
            `Unsupported Node.js version v${currentVersion}. Install Node 22 (recommended) or Node 20.`
        );
        process.exit(1);
    }

    console.warn(
        `Current Node.js v${currentVersion} is unsupported for Azure Functions. Using ${fallbackDir}/node for host startup.`
    );

    return fallbackDir;
}

async function main() {
    const fallbackBinDir = resolveNodeBinPrefix();
    const env = { ...process.env };

    if (fallbackBinDir) {
        env.PATH = `${fallbackBinDir}:${env.PATH || ""}`;
    }

    const portResolvedArgs = await resolvePortArgs(process.argv.slice(2));
    const funcArgs = ["host", "start", ...portResolvedArgs];
    const child = spawn("func", funcArgs, {
        stdio: "inherit",
        env
    });

    child.on("exit", (code, signal) => {
        if (signal) {
            process.kill(process.pid, signal);
            return;
        }

        process.exit(code ?? 0);
    });
}

main();