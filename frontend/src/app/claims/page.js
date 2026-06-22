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
  return <span className={`badge ${map[decision] || 'badge-pending'}`}>{decision?.replace('_', ' ')}</span>;
}

export default function ClaimsList() {
  const [claims, setClaims] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    apiGet('/api/claims')
      .then(data => setClaims(data.claims || []))
      .catch(() => setClaims([]))
      .finally(() => setLoading(false));
  }, []);

  return (
    <>
      <div className="page-header">
        <h1>All Claims</h1>
        <p>Complete history of processed claims</p>
      </div>

      <div className="glass-card glass-card--no-hover">
        {loading ? (
          <div className="flex items-center justify-center gap-12" style={{ padding: 48 }}>
            <div className="spinner"></div>
            <span className="text-secondary">Loading claims…</span>
          </div>
        ) : claims.length === 0 ? (
          <div className="empty-state">
            <div className="empty-state-icon">📂</div>
            <div className="empty-state-title">No claims found</div>
            <div className="empty-state-desc">Claims will appear here once they are submitted</div>
          </div>
        ) : (
          <table className="claims-table">
            <thead>
              <tr>
                <th>ID</th>
                <th>Date</th>
                <th>Member</th>
                <th>Category</th>
                <th>Amount (₹)</th>
                <th>Decision</th>
                <th>Confidence</th>
              </tr>
            </thead>
            <tbody>
              {claims.map(claim => (
                <tr key={claim.id} onClick={() => window.location.href = `/claims/${claim.id}`}>
                  <td className="text-mono text-blue" style={{ fontWeight: 600 }}>{claim.id}</td>
                  <td className="text-mono text-secondary text-sm">
                    {new Date(claim.created_at).toLocaleString()}
                  </td>
                  <td>{claim.submission?.member_id}</td>
                  <td>{claim.submission?.claim_category}</td>
                  <td className="text-mono">
                    {claim.submission?.claimed_amount?.toLocaleString()}
                  </td>
                  <td>
                    <DecisionBadge decision={claim.result?.decision} status={claim.status} />
                  </td>
                  <td className="text-mono text-secondary text-sm">
                    {claim.result?.confidence_score
                      ? `${(claim.result.confidence_score * 100).toFixed(0)}%`
                      : '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </>
  );
}
