/**
 * Proxy all /api/agent/* calls to the Railway backend.
 * Runs server-side — no CORS issues, no localhost fallback in browser.
 */
import { NextRequest, NextResponse } from 'next/server'

const BACKEND = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'

interface RouteParams {
  params: Promise<{ path: string[] }>
}

async function proxy(req: NextRequest, { params }: RouteParams) {
  const { path } = await params
  const url = `${BACKEND}/agent/${path.join('/')}${req.nextUrl.search}`

  const isGet = req.method === 'GET'
  const body = isGet ? undefined : await req.text()

  const res = await fetch(url, {
    method: req.method,
    headers: { 'Content-Type': 'application/json' },
    body: body || undefined,
    cache: 'no-store',
  })

  const data = await res.json()
  return NextResponse.json(data, { status: res.status })
}

export const GET = proxy
export const POST = proxy
