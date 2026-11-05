import { Ajv2020, type ValidateFunction } from "ajv/dist/2020.js";
import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";

const DIR = join(import.meta.dirname, "..", "..", "..", "contracts");
const BASE = "https://todoimplementer.local/contracts/";

let shared: Ajv2020 | undefined;

/** One Ajv for the whole test file: building it and compiling a schema is the slow part, so both happen once. */
export function contractAjv(): Ajv2020 {
  if (shared === undefined) {
    shared = new Ajv2020({ allErrors: true, strict: false });
    for (const name of readdirSync(DIR)) {
      if (name.endsWith(".schema.json")) shared.addSchema(JSON.parse(readFileSync(join(DIR, name), "utf8")) as object);
    }
  }
  return shared;
}

export function contractValidator(file: string, def?: string): ValidateFunction {
  const suffix = def === undefined ? "" : `#/$defs/${def}`;
  const key = `${BASE}${file}.schema.json${suffix}`;
  const found = contractAjv().getSchema(key);
  if (found === undefined) throw new Error(`no contract ${key}`);
  return found;
}

const HELPER_DEFS = new Set(["ab_build", "ab_metric", "agent_group", "base", "carry_row", "session_row", "ts"]);

/** Panel name -> the tokens-panels-* contract file (no extension) that defines it; helper defs are left out. */
export function panelContracts(): Map<string, string> {
  const found = new Map<string, string>();
  const panelFiles = readdirSync(DIR).filter((f) => f.startsWith("tokens-panels-"));
  for (const file of panelFiles) {
    const raw = JSON.parse(readFileSync(join(DIR, file), "utf8")) as { $defs: Record<string, unknown> };
    for (const name of Object.keys(raw.$defs)) {
      if (!HELPER_DEFS.has(name)) found.set(name, file.replace(".schema.json", ""));
    }
  }
  return found;
}

export function contractEnum(file: string, def: string): string[] {
  const raw = JSON.parse(readFileSync(join(DIR, `${file}.schema.json`), "utf8")) as {
    $defs: Record<string, { enum: string[] }>;
  };
  return raw.$defs[def]?.enum ?? [];
}
