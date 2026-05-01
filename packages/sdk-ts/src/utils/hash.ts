/**
 * Cross-runtime SHA-256 of a JSON-stringified value.
 */

function canonical(obj: unknown): string {
  return JSON.stringify(obj, Object.keys(obj as object ?? {}).sort())
}

export async function hashJson(value: unknown): Promise<string> {
  const text = canonical(value)
  const bytes = new TextEncoder().encode(text)

  // Web Crypto (modern Node 20+, browsers, Workers)
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const subtle = (globalThis.crypto as any)?.subtle
  if (subtle) {
    const digest = await subtle.digest('SHA-256', bytes)
    return toHex(new Uint8Array(digest))
  }

  // Fallback: dynamic Node `crypto` import
  const { createHash } = await import('node:crypto')
  return createHash('sha256').update(bytes).digest('hex')
}

function toHex(bytes: Uint8Array): string {
  const chars = '0123456789abcdef'
  let out = ''
  for (const b of bytes) {
    out += chars.charAt(b >> 4) + chars.charAt(b & 0xf)
  }
  return out
}
