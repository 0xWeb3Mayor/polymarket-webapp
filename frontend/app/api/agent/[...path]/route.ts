/**
 * Proxy all /api/agent/* calls to the Railway backend.
 * Uses API_URL (server-only) → NEXT_PUBLIC_API_URL → localhost fallback.
 * Never throws — always returns JSON so the client can handle errors gracefully.
 */
import { NextRequest, NextResponse } from 'next/server'

// API_URL is server-only (no NEXT_PUBLIC_ prefix needed for server-side calls).
// Set this in Vercel environment variables to your Railway backend URL.
const BACKEND =
  process.env.API_URL ??
  process.env.NEXT_PUBLIC_API_URL ??
  'http://localhost:8000'

interface RouteParams {
  params: Promise<{ path: string[] }>
}

async function proxy(req: NextRequest, { params }: RouteParams) {
  const { path } = await params
  const url = `${BACKEND}/agent/${path.join('/')}${req.nextUrl.search}`

  try {
    const isGet = req.method === 'GET'
    const body = isGet ? undefined : await req.text()

    const res = await fetch(url, {
      method: req.method,
      headers: { 'Content-Type': 'application/json' },
      body: body || undefined,
      cache: 'no-store',
    })

    const data = await res.json().catch(() => ({ status: 'error', detail: 'Invalid response from backend' }))
    return NextResponse.json(data, { status: res.status })

  } catch (err) {
    const message = err instanceof Error ? err.message : String(err)
    console.error(`[agent proxy] ${req.method} ${url} failed: ${message}`)
    // Return 200 so the frontend can read the body and show a real error
    return NextResponse.json(
      { status: 'error', detail: `Backend unreachable — check API_URL in Vercel env vars (${message})` },
      { status: 200 }
    )
  }
}

export const GET = proxy
export const POST = proxy
