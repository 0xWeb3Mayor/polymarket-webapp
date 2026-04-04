import { NextResponse } from 'next/server'

const BACKEND =
  process.env.API_URL ??
  process.env.NEXT_PUBLIC_API_URL ??
  'http://localhost:8000'

export async function GET() {
  try {
    const res = await fetch(`${BACKEND}/wallet/balance`, { cache: 'no-store' })
    const data = await res.json()
    return NextResponse.json(data, { status: res.status })
  } catch {
    return NextResponse.json(
      { address: null, usdc: null, usdc_e: null, total: null, chain: 'polygon' },
      { status: 200 }
    )
  }
}
