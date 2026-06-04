import { mkdir, rm, cp, copyFile } from "node:fs/promises";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { spawn } from "node:child_process";

const root = dirname(dirname(fileURLToPath(import.meta.url)));
const dist = join(root, "dist");

const run = (command, args) => new Promise((resolve, reject) => {
  const child = spawn(command, args, { cwd: root, shell: process.platform === "win32", stdio: "inherit" });
  child.on("exit", (code) => {
    if (code === 0) resolve();
    else reject(new Error(`${command} ${args.join(" ")} exited with ${code}`));
  });
});

await rm(dist, { recursive: true, force: true });
await mkdir(join(dist, "js", "vendor"), { recursive: true });

await copyFile(join(root, "index.html"), join(dist, "index.html"));
await cp(join(root, "public", "css"), join(dist, "css"), { recursive: true });
await cp(join(root, "public", "assets"), join(dist, "assets"), { recursive: true });
await cp(join(root, "public", "screenshots"), join(dist, "screenshots"), { recursive: true });
await cp(join(root, "public", "downloads"), join(dist, "downloads"), { recursive: true });

await copyFile(
  join(root, "node_modules", "react", "umd", "react.production.min.js"),
  join(dist, "js", "vendor", "react.production.min.js"),
);
await copyFile(
  join(root, "node_modules", "react-dom", "umd", "react-dom.production.min.js"),
  join(dist, "js", "vendor", "react-dom.production.min.js"),
);

await run("npx", [
  "babel",
  "public/js",
  "--extensions",
  ".jsx",
  "--out-dir",
  "dist/js",
  "--presets",
  "@babel/preset-react",
]);
