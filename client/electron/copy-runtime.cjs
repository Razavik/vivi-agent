const fs = require("node:fs");
const path = require("node:path");

const projectRoot = path.resolve(__dirname, "..", "..");
const outputDir = path.join(projectRoot, "dist-app");
const unpackedDir = path.join(outputDir, "win-unpacked");
const appDir = path.join(outputDir, "Vivi");
const sourceVenv = path.join(projectRoot, ".venv");
const targetVenv = path.join(appDir, ".venv");

if (!fs.existsSync(unpackedDir)) {
	console.error(`Build output not found: ${unpackedDir}`);
	process.exit(1);
}

fs.rmSync(appDir, { recursive: true, force: true });
fs.renameSync(unpackedDir, appDir);
console.log(`Renamed build output to ${appDir}`);

if (!fs.existsSync(sourceVenv)) {
	console.warn(`Python venv not found, packaged app will use system Python: ${sourceVenv}`);
	process.exit(0);
}

fs.rmSync(targetVenv, { recursive: true, force: true });
fs.cpSync(sourceVenv, targetVenv, {
	recursive: true,
	filter: (source) => {
		const normalized = source.replaceAll("\\", "/");
		return !normalized.includes("/__pycache__/") && !normalized.endsWith(".pyc");
	},
});

console.log(`Copied Python runtime to ${targetVenv}`);
