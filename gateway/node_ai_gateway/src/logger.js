import { mkdirSync, appendFileSync } from 'node:fs';
import { dirname } from 'node:path';

export function writeAuditLog(path, payload) {
  if (!path) return;
  try {
    mkdirSync(dirname(path), { recursive: true });
    appendFileSync(path, `${JSON.stringify(payload)}\n`, { encoding: 'utf8' });
  } catch {
    // Optional file sink should never break request handling.
  }
}
