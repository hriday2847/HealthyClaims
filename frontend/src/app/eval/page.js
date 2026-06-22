'use client';

import { useState } from 'react';
import { apiPost } from '@/lib/api';

function DecisionBadge({ decision }) {
  if (!decision) return <span className="badge badge-document-error">Doc Error</span>;
  const map = {
    APPROVED: 'badge-approved',
    PARTIAL: 'badge-partial',
    REJECTED: 'badge-rejected',
    MANUAL_REVIEW: 'badge-manual-review',
  };
  return <span className={`badge ${map[decision] || 'badge-pending'}`}>{decision.replace('_', ' ')}</span>;
}

export default function EvalReport() {
  const [evalData, setEvalData] = useState(null);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState(null);

  const runEval = async () => {
    setRunning(true);
    setError(null);
    try {
      const data = await apiPost('/api/eval', {});
      setEvalData(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setRunning(false);
    }
  };

  return (
    <>
      <div className="page-header flex justify-between items-center">
        <div>
          <h1>Eval Report</h1>
          <p>Run the 12 assignment test cases against the pipeline</p>
        </div>
        <button className="btn btn-primary btn-lg" onClick={runEval} disabled={running}>
          {running ? 'Running Tests...' : '▶ Run Eval Suite'}
        </button>
      </div>

      {error && (
        <div className="glass-card mb-24" style={{ borderColor: 'var(--accent-rose)' }}>
          <h3 className="text-rose mb-8">Error running evaluation</h3>
          <p className="text-secondary">{error}</p>
        </div>
      )}

      {evalData && (
        <>
          <div className="stats-grid mb-32">
            <div className="glass-card stat-card stat-card--blue">
              <div className="stat-label">Total Cases</div>
              <div className="stat-value stat-value--blue">{evalData.summary.total}</div>
            </div>
            <div className="glass-card stat-card stat-card--emerald">
              <div className="stat-label">Passed</div>
              <div className="stat-value stat-value--emerald">{evalData.summary.passed}</div>
            </div>
            <div className="glass-card stat-card stat-card--rose">
              <div className="stat-label">Failed</div>
              <div className="stat-value stat-value--rose">{evalData.summary.failed}</div>
            </div>
            <div className="glass-card stat-card stat-card--violet">
              <div className="stat-label">Pass Rate</div>
              <div className="stat-value stat-value--violet">{evalData.summary.pass_rate}</div>
            </div>
          </div>

          <div className="space-y-16">
            {evalData.results.map(res => {
              const passed = res.match.passed;
              return (
                <div key={res.case_id} className="glass-card eval-case" style={{ padding: 0, overflow: 'hidden', borderLeft: `4px solid ${passed ? 'var(--accent-emerald)' : 'var(--accent-rose)'}` }}>
                  <div 
                    className="eval-case-header" 
                    onClick={(e) => {
                      const content = e.currentTarget.nextElementSibling;
                      content.style.display = content.style.display === 'none' ? 'block' : 'none';
                    }}
                  >
                    <div className={`eval-pass eval-pass--${passed}`}>
                      {passed ? '✓' : '✗'}
                    </div>
                    <div style={{ flex: 1 }}>
                      <div className="flex items-center gap-12">
                        <span className="eval-case-id">{res.case_id}</span>
                        <span style={{ fontWeight: 600 }}>{res.case_name}</span>
                      </div>
                      <div className="text-sm text-secondary truncate mt-4">{res.description}</div>
                    </div>
                    <div className="text-mono text-xs text-tertiary">{res.processing_time_ms}ms</div>
                  </div>

                  <div style={{ display: 'none', padding: 24, borderTop: '1px solid var(--surface-divider)', background: 'var(--bg-primary)' }}>
                    <div className="grid-2 gap-24 mb-16">
                      {/* Expected */}
                      <div>
                        <div className="text-xs text-tertiary mb-8" style={{ textTransform: 'uppercase', fontWeight: 700 }}>Expected</div>
                        <div className="bg-glass" style={{ padding: 12, borderRadius: 8, border: '1px solid var(--surface-divider)' }}>
                           {res.expected.decision ? (
                             <div className="mb-8"><DecisionBadge decision={res.expected.decision} /></div>
                           ) : (
                             <div className="text-sm text-rose mb-8">Expected Stop (Document Error)</div>
                           )}
                           <pre className="text-xs text-secondary text-mono" style={{ whiteSpace: 'pre-wrap' }}>
                             {JSON.stringify(res.expected, null, 2)}
                           </pre>
                        </div>
                      </div>

                      {/* Actual */}
                      <div>
                        <div className="text-xs text-tertiary mb-8" style={{ textTransform: 'uppercase', fontWeight: 700 }}>Actual</div>
                        <div className="bg-glass" style={{ padding: 12, borderRadius: 8, border: '1px solid var(--surface-divider)' }}>
                           {res.actual_decision.decision ? (
                             <div className="mb-8"><DecisionBadge decision={res.actual_decision.decision} /></div>
                           ) : (
                             <div className="text-sm text-rose mb-8">Stopped (Document Error)</div>
                           )}
                           <div className="text-sm mb-8">{res.actual_decision.summary}</div>
                           <a href={`/claims/${res.claim_id}`} className="text-blue text-sm" target="_blank" rel="noreferrer">
                             View Full Trace ↗
                           </a>
                        </div>
                      </div>
                    </div>

                    {/* Match Checks */}
                    <div>
                       <div className="text-xs text-tertiary mb-8" style={{ textTransform: 'uppercase', fontWeight: 700 }}>Evaluation Checks</div>
                       <div className="bg-glass" style={{ padding: '12px 16px', borderRadius: 8, border: '1px solid var(--surface-divider)' }}>
                         {res.match.checks.map((check, i) => (
                           <div key={i} className="flex items-center gap-8 mb-4">
                             <span className={check.passed ? 'text-emerald' : 'text-rose'}>
                               {check.passed ? '✓' : '✗'}
                             </span>
                             <span className="text-sm font-medium">{check.check}</span>
                             {!check.passed && check.detail && (
                               <span className="text-xs text-rose ml-8">({check.detail})</span>
                             )}
                           </div>
                         ))}
                       </div>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </>
      )}
    </>
  );
}
