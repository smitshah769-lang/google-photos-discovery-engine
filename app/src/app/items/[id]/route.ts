import { jsonResponse, readSnapshot } from "@/lib/snapshot";

export const runtime = "nodejs";

export async function GET(_request: Request, ctx: { params: Promise<{ id: string }> }) {
  const { id } = await ctx.params;
  const items = readSnapshot<Record<string, unknown>>("items.json");
  const item = items[id];
  if (!item) return jsonResponse({ error: "Item not found" }, 404);
  return jsonResponse(item);
}
