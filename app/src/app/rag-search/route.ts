import { jsonResponse } from "@/lib/snapshot";
import { runStaticSearch } from "@/lib/staticSearch";

export const runtime = "nodejs";
export const maxDuration = 60;

export async function POST(request: Request) {
  let body: { query?: string; sources?: string[] } = {};
  try {
    body = (await request.json()) as { query?: string; sources?: string[] };
  } catch {
    return jsonResponse({ error: "Expected JSON body" }, 400);
  }
  try {
    return jsonResponse(await runStaticSearch(body));
  } catch (err) {
    const message = err instanceof Error ? err.message : "Search failed";
    return jsonResponse({ error: message }, 500);
  }
}
