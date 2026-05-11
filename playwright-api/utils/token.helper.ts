/**
 * Mask a JWT or opaque token for logs and reports (never print full value).
 */
export function maskToken(token: string | undefined | null): string {
  if (!token) {
    return "";
  }
  if (token.length <= 12) {
    return "***";
  }
  return `${token.slice(0, 4)}…${token.slice(-4)}`;
}

export interface JwtPayload {
  sub?: string;
  role?: string;
  exp?: number;
  iat?: number;
  [key: string]: unknown;
}

/** Decode JWT payload without verifying signature (debugging only). */
export function decodeJwtPayload(token: string): JwtPayload | null {
  try {
    const parts = token.split(".");
    if (parts.length < 2) {
      return null;
    }
    const payload = parts[1];
    const b64 = payload.replace(/-/g, "+").replace(/_/g, "/");
    const padded = b64.padEnd(b64.length + ((4 - (b64.length % 4)) % 4), "=");
    const json = Buffer.from(padded, "base64").toString("utf8");
    return JSON.parse(json) as JwtPayload;
  } catch {
    return null;
  }
}
