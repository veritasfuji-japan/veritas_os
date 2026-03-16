import { afterEach, describe, expect, it, vi } from 'vitest';

import {
  buildCspEnforced,
  buildCspReportOnly,
  generateNonce,
  middleware,
  shouldEnforceNonceCsp
} from './middleware';

describe('middleware CSP', () => {
  afterEach(() => {
    vi.unstubAllEnvs();
  });
  it('generates a nonce string', () => {
    const nonce = generateNonce();

    expect(nonce.length).toBeGreaterThan(10);
  });

  it('builds enforced CSP in compatibility mode with unsafe-inline script-src', () => {
    const csp = buildCspEnforced('sample-nonce', false);
    const scriptDirective = csp
      .split(';')
      .find((directive) => directive.trim().startsWith('script-src'));

    expect(csp).toContain("default-src 'self'");
    expect(scriptDirective).toContain("'unsafe-inline'");
  });

  it('builds enforced CSP in strict mode without unsafe-inline in script-src', () => {
    const csp = buildCspEnforced('sample-nonce', true);
    const scriptDirective = csp
      .split(';')
      .find((directive) => directive.trim().startsWith('script-src'));

    expect(csp).toContain("default-src 'self'");
    expect(scriptDirective).toContain("'nonce-sample-nonce'");
    expect(scriptDirective).not.toContain("'unsafe-inline'");
  });

  it('builds nonce-based report-only CSP without unsafe-inline in script-src', () => {
    const csp = buildCspReportOnly('sample-nonce');
    const scriptDirective = csp
      .split(';')
      .find((directive) => directive.trim().startsWith('script-src'));

    expect(csp).toContain("default-src 'self'");
    expect(scriptDirective).toContain("'nonce-sample-nonce'");
    expect(scriptDirective).not.toContain("'unsafe-inline'");
  });

  it('defaults nonce enforcement flag to false in non-production profile', () => {
    vi.stubEnv('VERITAS_ENV', 'development');

    expect(shouldEnforceNonceCsp()).toBe(false);
  });

  it('enables nonce enforcement only when explicitly opted in', () => {
    vi.stubEnv('VERITAS_CSP_ENFORCE_NONCE', 'true');

    expect(shouldEnforceNonceCsp()).toBe(true);
  });



  it('enables nonce enforcement in production profile by default', () => {
    vi.stubEnv('VERITAS_ENV', 'production');

    expect(shouldEnforceNonceCsp()).toBe(true);
  });

  it('sets CSP headers and forwards nonce to the Next.js request', () => {
    const response = middleware({ headers: new Headers() } as never);
    const csp = response.headers.get('Content-Security-Policy') ?? '';
    const cspReportOnly = response.headers.get('Content-Security-Policy-Report-Only') ?? '';
    const nonce = response.headers.get('x-veritas-nonce') ?? '';
    const forwardedNonce = response.headers.get('x-middleware-request-x-nonce') ?? '';

    const scriptDirective = csp
      .split(';')
      .find((directive) => directive.trim().startsWith('script-src'));
    const reportOnlyScriptDirective = cspReportOnly
      .split(';')
      .find((directive) => directive.trim().startsWith('script-src'));

    expect(nonce).not.toBe('');
    expect(scriptDirective).toContain("'unsafe-inline'");
    expect(reportOnlyScriptDirective).toContain(`'nonce-${nonce}'`);
    expect(reportOnlyScriptDirective).not.toContain("'unsafe-inline'");
    expect(forwardedNonce).toBe(nonce);
  });
});
