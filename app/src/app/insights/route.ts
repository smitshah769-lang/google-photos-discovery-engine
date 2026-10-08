import { jsonResponse, readSnapshot } from "@/lib/snapshot";

export const runtime = "nodejs";

export function GET() {
  return jsonResponse(readSnapshot("insights.json"));
}
