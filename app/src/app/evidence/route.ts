import { queryEvidence } from "@/lib/evidenceQuery";
import { jsonResponse } from "@/lib/snapshot";

export const runtime = "nodejs";

export function GET(request: Request) {
  const params = new URL(request.url).searchParams;
  return jsonResponse(queryEvidence(params));
}
