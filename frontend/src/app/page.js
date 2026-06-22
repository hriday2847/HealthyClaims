'use client';

import { useState, useEffect } from 'react';
import { apiGet, apiPost } from '@/lib/api';

function DecisionBadge({ decision, status }) {
  if (status === 'DOCUMENT_ERROR') return <span className="badge badge-document-error">⚠ Doc Error</span>;
  if (!decision) return <span className="badge badge-pending">Pending</span>;
  const map = {
    APPROVED: 'badge-approved',
    PARTIAL: 'badge-partial',
    REJECTED: 'badge-rejected',
    MANUAL_REVIEW: 'badge-manual-review',
  };
  const icons = { APPROVED: '✓', PARTIAL: '◐', REJECTED: '✗', MANUAL_REVIEW: '⚑' };
  return (
    <span className={`badge ${map[decision] || 'badge-pending'}`}>
      {icons[decision] || ''} {decision?.replace('_', ' ')}
    </span>
  );
}

export default function Dashboard() {
  const [claims, setClaims] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    apiGet('/api/claims')
      .then(data => setClaims(data.claims || []))
      .catch(() => setClaims([]))
      .finally(() => setLoading(false));
  }, []);

  const stats = {
    total: claims.length,
    approved: claims.filter(c => c.result?.decision === 'APPROVED').length,
    rejected: claims.filter(c => c.result?.decision === 'REJECTED').length,
    partial: claims.filter(c => c.result?.decision === 'PARTIAL').length,
    manual: claims.filter(c => c.result?.decision === 'MANUAL_REVIEW').length,
    docErrors: claims.filter(c => c.status === 'DOCUMENT_ERROR').length,
  };

  return (
    <>
      <div className="page-header">
        <h1>Claims Dashboard</h1>
        <p>AI-powered multi-agent health insurance claims processing</p>
      </div>

      {/* Stats */}
      <div className="stats-grid">
        <div className="glass-card stat-card stat-card--blue">
          <div className="stat-label">Total Claims</div>
          <div className="stat-value stat-value--blue">{stats.total}</div>
        </div>
        <div className="glass-card stat-card stat-card--emerald">
          <div className="stat-label">Approved</div>
          <div className="stat-value stat-value--emerald">{stats.approved}</div>
        </div>
        <div className="glass-card stat-card stat-card--rose">
          <div className="stat-label">Rejected</div>
          <div className="stat-value stat-value--rose">{stats.rejected}</div>
        </div>
        <div className="glass-card stat-card stat-card--amber">
          <div className="stat-label">Manual Review</div>
          <div className="stat-value stat-value--amber">{stats.manual}</div>
        </div>
        <div className="glass-card stat-card stat-card--violet">
          <div className="stat-label">Partial</div>
          <div className="stat-value stat-value--violet">{stats.partial}</div>
        </div>
      </div>

      {/* Quick Actions */}
      <div className="flex gap-16 mb-24">
        <a href="/submit" className="btn btn-primary btn-lg">+ Submit New Claim</a>
        <a href="/eval" className="btn btn-secondary btn-lg">⚡ Run Eval Suite</a>
      </div>

      {/* Recent Claims */}
      <div className="glass-card glass-card--no-hover">
        <h2 style={{ fontSize: '1.1rem', fontWeight: 700, marginBottom: 16 }}>Recent Claims</h2>
        {loading ? (
          <div className="flex items-center gap-12" style={{ padding: 32, justifyContent: 'center' }}>
            <div className="spinner"></div>
            <span className="text-secondary">Loading claims…</span>
          </div>
        ) : claims.length === 0 ? (
          <div className="empty-state">
            <div className="empty-state-icon">📋</div>
            <div className="empty-state-title">No claims yet</div>
            <div className="empty-state-desc">Submit a new claim or run the eval suite to get started</div>
            <a href="/submit" className="btn btn-primary">Submit Claim</a>
          </div>
        ) : (
          <table className="claims-table">
            <thead>
              <tr>
                <th>Claim ID</th>
                <th>Member</th>
                <th>Category</th>
                <th>Amount</th>
                <th>Decision</th>
                <th>Confidence</th>
                <th>Time</th>
              </tr>
            </thead>
            <tbody>
              {claims.slice(0, 20).map(claim => (
                <tr key={claim.id} onClick={() => window.location.href = `/claims/${claim.id}`}>
                  <td className="text-mono text-blue" style={{ fontWeight: 600 }}>{claim.id}</td>
                  <td>{claim.submission?.member_id}</td>
                  <td>{claim.submission?.claim_category}</td>
                  <td className="text-mono">₹{claim.submission?.claimed_amount?.toLocaleString()}</td>
                  <td>
                    <DecisionBadge decision={claim.result?.decision} status={claim.status} />
                  </td>
                  <td className="text-mono text-secondary">
                    {claim.result?.confidence_score
                      ? `${(claim.result.confidence_score * 100).toFixed(0)}%`
                      : '—'}
                  </td>
                  <td className="text-mono text-tertiary text-xs">
                    {claim.processing_time_ms ? `${claim.processing_time_ms}ms` : '—'}
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
