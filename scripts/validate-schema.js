import { readFileSync } from "node:fs";
import { resolve, relative } from "node:path";
import { glob } from "glob";
import Ajv from "ajv";
import matter from "gray-matter";

const ROOT = resolve(import.meta.dirname, "..");
const SCHEMA_PATH = resolve(ROOT, "schema", "pattern.schema.json");
const PATTERNS_GLOB = "site/src/content/docs/patterns/**/*.{md,mdx}";

const schema = JSON.parse(readFileSync(SCHEMA_PATH, "utf-8"));
const ajv = new Ajv({ allErrors: true });
const validate = ajv.compile(schema);

const files = await glob(PATTERNS_GLOB, { cwd: ROOT, absolute: true });

if (files.length === 0) {
  console.log("No pattern files found to validate.");
  process.exit(0);
}

let hasErrors = false;

for (const filePath of files) {
  const relPath = relative(ROOT, filePath);
  const content = readFileSync(filePath, "utf-8");

  let frontmatter;
  try {
    const parsed = matter(content);
    frontmatter = parsed.data;
  } catch (err) {
    console.error(`FAIL ${relPath}: Invalid YAML frontmatter - ${err.message}`);
    hasErrors = true;
    continue;
  }

  const valid = validate(frontmatter);

  if (!valid) {
    hasErrors = true;
    console.error(`FAIL ${relPath}:`);
    for (const error of validate.errors) {
      const path = error.instancePath || "(root)";
      console.error(`  - ${path}: ${error.message}`);
    }
  } else {
    const expectedPillar = relPath.split("/").at(-2);
    if (frontmatter.pillar !== expectedPillar) {
      console.warn(
        `WARN ${relPath}: pillar "${frontmatter.pillar}" does not match directory "${expectedPillar}"`
      );
    }
    console.log(`PASS ${relPath}`);
  }
}

if (hasErrors) {
  console.error("\nValidation failed. Fix the errors above.");
  process.exit(1);
}

console.log(`\nAll ${files.length} pattern(s) passed validation.`);
