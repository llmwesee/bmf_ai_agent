import { build } from "esbuild";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const rootDir = path.resolve(__dirname, "..");

await build({
  entryPoints: [path.join(rootDir, "frontend", "src", "main.jsx")],
  bundle: true,
  format: "esm",
  jsx: "automatic",
  target: "es2020",
  minify: true,
  define: {
    "process.env.NODE_ENV": "\"production\"",
  },
  outfile: path.join(rootDir, "src", "bfm_agent", "static", "app.js"),
});
