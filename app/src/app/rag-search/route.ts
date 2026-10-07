import { NextRequest } from "next/server";

const API = process.env.DISCOVERY_API_URL || "http://127.0.0.1:8765";

function upstreamHeaders(): HeadersInit {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  const user = process.env.DISCOVERY_BASIC_USER;
  const password = process.env.DISCOVERY_BASIC_PASSWORD;
  const combined = process.env.NEXT_PUBLIC_DISCOVERY_BASIC_AUTH;
  const token = user && password ? `${user}:${password}` : combined;
  if (token) {
    headers.Authorization = `Basic ${Buffer.from(token).toString("base64")}`;
  }
  return headers;
}

export async function POST(request: NextRequest) {
  const body = await request.text();
  const res = await fetch(`${API}/search`, {
    method: "POST",
    headers: upstreamHeaders(),
    body,
  });
  const text = await res.text();
  return new Response(text, {
    status: res.status,
    headers: { "Content-Type": "application/json" },
  });
}
