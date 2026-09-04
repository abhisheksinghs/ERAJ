import type { BackendResult } from "@/lib/tenant";

/**
 * Renders the right message for a failed backend call. 402 (subscription
 * inactive) gets a dedicated renewal CTA — the PDF spec calls this out by
 * name. 403 (module not licensed) and everything else keep the plain notice.
 */
export function StatusNotice({ result }: { result: Extract<BackendResult<unknown>, { ok: false }> }) {
  if (result.status === 402) {
    return (
      <div className="notice notice--renewal">
        <h2>Subscription inactive</h2>
        <p>This institution&apos;s plan has lapsed or been suspended. Renew to restore access.</p>
        <a className="renew-cta" href="mailto:billing@eraj.example?subject=Renew%20subscription">
          Contact billing to renew
        </a>
      </div>
    );
  }
  return <div className="notice">{result.error}</div>;
}
