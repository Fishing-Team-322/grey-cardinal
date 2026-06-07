import { cp, mkdir, readdir, rm } from "node:fs/promises";
import { spawnSync } from "node:child_process";

async function findScripts(directory) {
  const entries = await readdir(directory, { withFileTypes: true });
  const nested = await Promise.all(entries.map(async (entry) => {
    const path = `${directory}/${entry.name}`;
    if (entry.isDirectory()) return findScripts(path);
    return path.endsWith(".js") ? [path] : [];
  }));
  return nested.flat();
}

const scripts = await findScripts("public");
for (const file of scripts) {
  const result = spawnSync(process.execPath, ["--check", file], { stdio: "inherit" });
  if (result.status !== 0) process.exit(result.status ?? 1);
}

await rm("dist", { recursive: true, force: true });
await mkdir("dist", { recursive: true });
await cp("public", "dist", { recursive: true });
console.log(`Validated ${scripts.length} JavaScript files and built dist/.`);
