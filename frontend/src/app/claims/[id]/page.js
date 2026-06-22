'use client';

import { useState, useEffect } from 'react';
import { apiGet } from '@/lib/api';

function DecisionBadge({ decision, status }) {
  if (status === 'DOCUMENT_ERROR') return <span className="badge badge-document-error">⚠ Doc Error</span>;
  if (!decision) return <span className="badge badge-pending">Pending</span>;
  const map = {
    APPROVED: 'badge-approved',
    PARTIAL: 'badge-partial',
    REJECTED: 'badge-rejected',
    MANUAL_REVIEW: 'badge-manual-review',
  };
  return <span className={`badge ${map[decision] || 'badge-pending'}`} style={{ fontSize: '1rem', padding: '6px 16px' }}>{decision?.replace('_', ' ')}</span>;
}

export default function ClaimDetail({ params }) {
  const [claim, setClaim] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    apiGet(`/api/claims/${params.id}`)
      .then(setClaim)
      .catch(err => setError(err.message))
      .finally(() => setLoading(false));
  }, [params.id]);

  if (loading) return <div className="loading-overlay"><div className="spinner"></div><div className="loading-text">Loading claim details…</div></div>;
  if (error || !claim) return <div className="page-content"><div className="glass-card"><h2 className="text-rose">Error</h2><p>{error || 'Claim not found'}</p></div></div>;

  const { submission, result } = claim;

  return (
    <>
      <div className="mb-24 flex items-center justify-between">
        <div>
          <a href="/claims" className="text-secondary text-sm hover:text-white" style={{ display: 'inline-block', marginBottom: 8 }}>← Back to Claims</a>
          <h1 style={{ fontSize: '2rem', fontWeight: 800, background: 'var(--gradient-brand)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent' }}>
            Claim {claim.id}
          </h1>
        </div>
        <DecisionBadge decision={result?.decision} status={claim.status} />
      </div>

      <div className="grid-2 mb-24">
        {/* Submission Details */}
        <div className="glass-card glass-card--no-hover">
          <h3 style={{ fontSize: '1.1rem', fontWeight: 700, marginBottom: 16 }}>Submission Details</h3>
          <div className="grid-2 gap-16">
            <div>
              <div className="text-xs text-tertiary" style={{ textTransform: 'uppercase', letterSpacing: '0.05em', fontWeight: 600 }}>Member ID</div>
              <div style={{ fontWeight: 500 }}>{submission.member_id}</div>
            </div>
            <div>
              <div className="text-xs text-tertiary" style={{ textTransform: 'uppercase', letterSpacing: '0.05em', fontWeight: 600 }}>Category</div>
              <div style={{ fontWeight: 500 }}>{submission.claim_category}</div>
            </div>
            <div>
              <div className="text-xs text-tertiary" style={{ textTransform: 'uppercase', letterSpacing: '0.05em', fontWeight: 600 }}>Treatment Date</div>
              <div className="text-mono text-sm">{submission.treatment_date}</div>
            </div>
            <div>
              <div className="text-xs text-tertiary" style={{ textTransform: 'uppercase', letterSpacing: '0.05em', fontWeight: 600 }}>Claimed Amount</div>
              <div className="text-mono" style={{ fontWeight: 700 }}>₹{submission.claimed_amount?.toLocaleString()}</div>
            </div>
          </div>
          <div className="mt-16">
             <div className="text-xs text-tertiary mb-4" style={{ textTransform: 'uppercase', letterSpacing: '0.05em', fontWeight: 600 }}>Documents ({submission.documents?.length})</div>
             {submission.documents?.map((d, i) => (
               <div key={i} className="text-sm text-secondary bg-glass" style={{ padding: '4px 8px', borderRadius: 4, display: 'inline-block', marginRight: 8, marginBottom: 8, border: '1px solid var(--surface-divider)' }}>
                 {d.actual_type}
               </div>
             ))}
          </div>
        </div>

        {/* Decision Summary */}
        <div className="glass-card glass-card--no-hover">
          <h3 style={{ fontSize: '1.1rem', fontWeight: 700, marginBottom: 16 }}>Decision Summary</h3>
          
          {result?.document_errors?.length > 0 ? (
            <div>
               {result.document_errors.map((err, i) => (
                  <div key={i} className="doc-error">
                    <div className="doc-error-type">{err.error_type}</div>
                    <div className="doc-error-message">{err.message}</div>
                    <div className="doc-error-action">📎 {err.required_action}</div>
                  </div>
                ))}
            </div>
          ) : (
            <>
              <div className="flex justify-between items-center mb-16 pb-16" style={{ borderBottom: '1px solid var(--surface-divider)' }}>
                <div>
                  <div className="text-xs text-tertiary" style={{ textTransform: 'uppercase', letterSpacing: '0.05em', fontWeight: 600 }}>Approved Amount</div>
                  <div className="text-mono" style={{ fontSize: '2rem', fontWeight: 800, color: 'var(--accent-emerald)', lineHeight: 1 }}>
                    ₹{(result?.approved_amount || 0).toLocaleString()}
                  </div>
                </div>
                <div style={{ textAlign: 'right' }}>
                  <div className="text-xs text-tertiary" style={{ textTransform: 'uppercase', letterSpacing: '0.05em', fontWeight: 600 }}>Confidence</div>
                  <div className="text-mono" style={{ fontSize: '2rem', fontWeight: 800, color: 'var(--accent-blue)', lineHeight: 1 }}>
                    {((result?.confidence_score || 0) * 100).toFixed(0)}%
                  </div>
                </div>
              </div>

              {result?.summary && (
                <p className="text-secondary mb-16">{result.summary}</p>
              )}

              {result?.rejection_reasons?.length > 0 && (
                <div className="mb-16">
                  {result.rejection_reasons.map(r => <span key={r} className="badge badge-rejected" style={{ marginRight: 8, marginBottom: 8 }}>{r}</span>)}
                </div>
              )}

              {result?.recommendations?.length > 0 && (
                <div style={{ padding: 12, background: 'var(--accent-amber-dim)', border: '1px solid rgba(245, 158, 11, 0.2)', borderRadius: 8 }}>
                  <div className="text-amber text-xs" style={{ fontWeight: 700, textTransform: 'uppercase', marginBottom: 4 }}>Recommendations</div>
                  <ul style={{ paddingLeft: 16, fontSize: '0.85rem', color: 'var(--text-primary)' }}>
                    {result.recommendations.map((rec, i) => <li key={i}>{rec}</li>)}
                  </ul>
                </div>
              )}
            </>
          )}
        </div>
      </div>

      {/* Amount Breakdown Table */}
      {result?.amount_breakdown && (
        <div className="glass-card glass-card--no-hover mb-24">
          <h3 style={{ fontSize: '1.1rem', fontWeight: 700, marginBottom: 16 }}>Financial Breakdown</h3>
          <div style={{ maxWidth: 600 }}>
             <table className="breakdown-table text-sm">
                <tbody>
                  <tr>
                    <td className="text-secondary">Claimed Amount</td>
                    <td>₹{result.amount_breakdown.claimed_amount.toLocaleString()}</td>
                  </tr>
                  {result.amount_breakdown.eligible_amount !== result.amount_breakdown.claimed_amount && (
                    <tr>
                      <td className="text-secondary">Eligible Amount (after exclusions)</td>
                      <td>₹{result.amount_breakdown.eligible_amount.toLocaleString()}</td>
                    </tr>
                  )}
                  {result.amount_breakdown.network_discount > 0 && (
                    <tr>
                      <td className="text-secondary">Network Discount</td>
                      <td className="text-emerald">- ₹{result.amount_breakdown.network_discount.toLocaleString()}</td>
                    </tr>
                  )}
                  {result.amount_breakdown.sub_limit_cap > 0 && (
                    <tr>
                      <td className="text-secondary">Sub-limit Cap Applied</td>
                      <td className="text-rose">Capped at ₹{result.amount_breakdown.sub_limit_cap.toLocaleString()}</td>
                    </tr>
                  )}
                  {result.amount_breakdown.copay_amount > 0 && (
                    <tr>
                      <td className="text-secondary">Co-pay Deducted</td>
                      <td className="text-rose">- ₹{result.amount_breakdown.copay_amount.toLocaleString()}</td>
                    </tr>
                  )}
                  <tr>
                    <td style={{ color: 'var(--text-primary)' }}>Final Approved Amount</td>
                    <td className="text-emerald">₹{result.amount_breakdown.approved_amount.toLocaleString()}</td>
                  </tr>
                </tbody>
             </table>
          </div>
        </div>
      )}

      {/* Trace Timeline */}
      <div className="glass-card glass-card--no-hover">
        <h3 style={{ fontSize: '1.1rem', fontWeight: 700, marginBottom: 24 }}>Execution Trace</h3>
        
        <div className="trace-timeline">
          {result?.trace?.map((step, idx) => (
            <div key={idx} className="trace-step">
              <div className={`trace-dot trace-dot--${step.status.toLowerCase()}`}></div>
              <div className="glass-card" style={{ padding: 0, overflow: 'hidden' }}>
                <div className="trace-step-header" onClick={(e) => {
                  const content = e.currentTarget.nextElementSibling;
                  content.style.display = content.style.display === 'none' ? 'block' : 'none';
                }}>
                  <div className="flex items-center gap-12">
                    <span className="trace-agent-name">{step.agent_name}</span>
                    <span className={`badge badge-${step.status === 'SUCCESS' ? 'approved' : step.status === 'FAILED' ? 'rejected' : 'manual-review'}`}>
                      {step.status}
                    </span>
                  </div>
                  <span className="trace-duration">{step.duration_ms}ms</span>
                </div>
                
                <div className="trace-checks" style={{ borderTop: '1px solid var(--surface-divider)' }}>
                  {step.error && (
                    <div className="text-rose text-sm mb-8" style={{ padding: 8, background: 'var(--accent-rose-dim)', borderRadius: 4 }}>
                      <strong>Error:</strong> {step.error}
                    </div>
                  )}
                  {step.warnings?.length > 0 && (
                     <div className="mb-8">
                       {step.warnings.map((w, i) => (
                         <div key={i} className="text-amber text-xs" style={{ padding: '4px 8px', background: 'var(--accent-amber-dim)', borderRadius: 4, marginBottom: 4 }}>
                           ⚠ {w}
                         </div>
                       ))}
                     </div>
                  )}
                  
                  {step.checks?.length === 0 ? (
                    <div className="text-tertiary text-sm italic py-4">No specific checks recorded.</div>
                  ) : (
                    step.checks?.map((check, i) => (
                      <div key={i} className="trace-check">
                        <div className={`trace-check-icon ${check.passed ? 'text-emerald' : 'text-rose'}`}>
                          {check.passed ? '✓' : '✗'}
                        </div>
                        <div>
                          <div className="trace-check-name">{check.check_name}</div>
                          <div className="trace-check-detail">{check.detail}</div>
                        </div>
                      </div>
                    ))
                  )}
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </>
  );
}
