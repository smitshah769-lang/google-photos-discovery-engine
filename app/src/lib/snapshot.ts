import fs from "fs";
import path from "path";

const cache = new Map<string, unknown>();

export function snapshotPath(name: string): string {
  return path.join(process.cwd(), "snapshot", name);
}

export function readSnapshot<T>(name: string): T {
  const hit = cache.get(name);
  if (hit !== undefined) return hit as T;
  const file = snapshotPath(name);
  if (!fs.existsSync(file)) {
    throw new Error(`Missing snapshot file ${name}. Run scripts/export-static-snapshot.py.`);
  }
  const parsed = JSON.parse(fs.readFileSync(file, "utf8")) as T;
  cache.set(name, parsed);
  return parsed;
}

export function jsonResponse(data: unknown, status = 200): Response {
  return Response.json(data, { status });
}
