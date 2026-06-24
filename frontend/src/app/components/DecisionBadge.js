'use client';

/**
 * DecisionBadge — Shared component for rendering claim decision status badges.
 *
 * Used across Dashboard, Claims List, Claim Detail, Submit, and Eval pages.
 */
export default function DecisionBadge({ decision, status, large = false }) {
  if (status === 'DOCUMENT_ERROR')
    return (
      <span
        className="badge badge-document-error"
        style={large ? { fontSize: '1rem', padding: '6px 16px' } : undefined}
      >
        ⚠ Doc Error
      </span>
    );

  if (!decision)
    return (
      <span
        className="badge badge-pending"
        style={large ? { fontSize: '1rem', padding: '6px 16px' } : undefined}
      >
        Pending
      </span>
    );

  const classMap = {
    APPROVED: 'badge-approved',
    PARTIAL: 'badge-partial',
    REJECTED: 'badge-rejected',
    MANUAL_REVIEW: 'badge-manual-review',
  };

  const icons = {
    APPROVED: '✓',
    PARTIAL: '◐',
    REJECTED: '✗',
    MANUAL_REVIEW: '⚑',
  };

  return (
    <span
      className={`badge ${classMap[decision] || 'badge-pending'}`}
      style={large ? { fontSize: '1rem', padding: '6px 16px' } : undefined}
    >
      {icons[decision] || ''} {decision?.replace('_', ' ')}
    </span>
  );
}
