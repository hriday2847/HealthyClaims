'use client';

import { useState, useEffect } from 'react';
import { apiGet, apiPost } from '@/lib/api';

const CATEGORIES = [
  { value: 'CONSULTATION', label: 'Consultation' },
  { value: 'DIAGNOSTIC', label: 'Diagnostic' },
  { value: 'PHARMACY', label: 'Pharmacy' },
  { value: 'DENTAL', label: 'Dental' },
  { value: 'VISION', label: 'Vision' },
  { value: 'ALTERNATIVE_MEDICINE', label: 'Alternative Medicine' },
];

export default function SubmitClaim() {
  const [members, setMembers] = useState([]);
  const [form, setForm] = useState({
    member_id: '',
    claim_category: 'CONSULTATION',
    treatment_date: '2024-11-01',
    claimed_amount: '',
    hospital_name: '',
  });
  const [documents, setDocuments] = useState([
    { file_id: 'DOC_1', actual_type: 'PRESCRIPTION', content_json: '' },
    { file_id: 'DOC_2', actual_type: 'HOSPITAL_BILL', content_json: '' },
  ]);
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    apiGet('/api/members')
      .then(data => setMembers(data.members || []))
      .catch(() => setMembers([]));
  }, []);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    setResult(null);

    try {
      const docs = documents.map(d => {
        const doc = {
          file_id: d.file_id,
          actual_type: d.actual_type,
        };
        if (d.content_json.trim()) {
          try {
            doc.content = JSON.parse(d.content_json);
          } catch {
            doc.content = null;
          }
        }
        return doc;
      }).filter(d => d.actual_type);

      const submission = {
        ...form,
        claimed_amount: parseFloat(form.claimed_amount) || 0,
        policy_id: 'PLUM_GHI_2024',
        documents: docs,
      };

      const data = await apiPost('/api/claims', submission);
      setResult(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setSubmitting(false);
    }
  };

  const addDocument = () => {
    setDocuments([
      ...documents,
      { file_id: `DOC_${documents.length + 1}`, actual_type: '', content_json: '' },
    ]);
  };

  const removeDocument = (idx) => {
    setDocuments(documents.filter((_, i) => i !== idx));
  };

  const updateDocument = (idx, field, value) => {
    const updated = [...documents];
    updated[idx] = { ...updated[idx], [field]: value };
    setDocuments(updated);
  };

  function DecisionBadge({ decision, status }) {
    if (status === 'DOCUMENT_ERROR') return <span className="badge badge-document-error">⚠ Document Error</span>;
    if (!decision) return <span className="badge badge-pending">Pending</span>;
    const map = {
      APPROVED: 'badge-approved',
      PARTIAL: 'badge-partial',
      REJECTED: 'badge-rejected',
      MANUAL_REVIEW: 'badge-manual-review',
    };
    return <span className={`badge ${map[decision] || 'badge-pending'}`}>{decision?.replace('_', ' ')}</span>;
  }

  return (
    <>
      <div className="page-header">
        <h1>Submit a Claim</h1>
        <p>Fill in the claim details and attach supporting documents</p>
      </div>

      <div className="grid-2">
        {/* Form */}
        <form onSubmit={handleSubmit}>
          <div className="glass-card glass-card--no-hover">
            <h3 style={{ fontSize: '1rem', fontWeight: 700, marginBottom: 20 }}>Claim Details</h3>

            <div className="form-group">
              <label className="form-label">Member</label>
              <select
                className="form-select"
                value={form.member_id}
                onChange={e => setForm({ ...form, member_id: e.target.value })}
                required
              >
                <option value="">Select member…</option>
                {members.map(m => (
                  <option key={m.member_id} value={m.member_id}>
                    {m.member_id} — {m.name} ({m.relationship})
                  </option>
                ))}
              </select>
            </div>

            <div className="form-grid">
              <div className="form-group">
                <label className="form-label">Category</label>
                <select
                  className="form-select"
                  value={form.claim_category}
                  onChange={e => setForm({ ...form, claim_category: e.target.value })}
                >
                  {CATEGORIES.map(c => (
                    <option key={c.value} value={c.value}>{c.label}</option>
                  ))}
                </select>
              </div>
              <div className="form-group">
                <label className="form-label">Treatment Date</label>
                <input
                  type="date"
                  className="form-input"
                  value={form.treatment_date}
                  onChange={e => setForm({ ...form, treatment_date: e.target.value })}
                  required
                />
              </div>
            </div>

            <div className="form-grid">
              <div className="form-group">
                <label className="form-label">Claimed Amount (₹)</label>
                <input
                  type="number"
                  className="form-input"
                  value={form.claimed_amount}
                  onChange={e => setForm({ ...form, claimed_amount: e.target.value })}
                  placeholder="e.g. 1500"
                  required
                />
              </div>
              <div className="form-group">
                <label className="form-label">Hospital Name (optional)</label>
                <input
                  type="text"
                  className="form-input"
                  value={form.hospital_name}
                  onChange={e => setForm({ ...form, hospital_name: e.target.value })}
                  placeholder="e.g. Apollo Hospitals"
                />
              </div>
            </div>
          </div>

          {/* Documents */}
          <div className="glass-card glass-card--no-hover mt-16">
            <div className="flex items-center justify-between mb-16">
              <h3 style={{ fontSize: '1rem', fontWeight: 700 }}>Documents</h3>
              <button type="button" className="btn btn-secondary btn-sm" onClick={addDocument}>
                + Add Document
              </button>
            </div>

            {documents.map((doc, idx) => (
              <div key={idx} style={{
                padding: 16,
                background: 'var(--bg-glass)',
                borderRadius: 'var(--radius-sm)',
                border: '1px solid var(--surface-border)',
                marginBottom: 12,
              }}>
                <div className="flex items-center justify-between mb-8">
                  <span className="text-mono text-xs text-secondary">{doc.file_id}</span>
                  {documents.length > 1 && (
                    <button
                      type="button"
                      onClick={() => removeDocument(idx)}
                      style={{
                        background: 'none',
                        border: 'none',
                        color: 'var(--accent-rose)',
                        cursor: 'pointer',
                        fontSize: '0.8rem',
                      }}
                    >
                      ✗ Remove
                    </button>
                  )}
                </div>
                <div className="form-group" style={{ marginBottom: 8 }}>
                  <select
                    className="form-select"
                    value={doc.actual_type}
                    onChange={e => updateDocument(idx, 'actual_type', e.target.value)}
                  >
                    <option value="">Select type…</option>
                    <option value="PRESCRIPTION">Prescription</option>
                    <option value="HOSPITAL_BILL">Hospital Bill</option>
                    <option value="LAB_REPORT">Lab Report</option>
                    <option value="PHARMACY_BILL">Pharmacy Bill</option>
                    <option value="DENTAL_REPORT">Dental Report</option>
                    <option value="DISCHARGE_SUMMARY">Discharge Summary</option>
                  </select>
                </div>
                <div className="form-group" style={{ marginBottom: 0 }}>
                  <textarea
                    className="form-textarea"
                    value={doc.content_json}
                    onChange={e => updateDocument(idx, 'content_json', e.target.value)}
                    placeholder='Optional: paste document content as JSON, e.g. {"patient_name": "Rajesh Kumar", "total": 1500}'
                    rows={3}
                    style={{ fontSize: '0.8rem', fontFamily: 'var(--font-mono)' }}
                  />
                </div>
              </div>
            ))}
          </div>

          <button
            type="submit"
            className="btn btn-primary btn-lg mt-16"
            disabled={submitting}
            style={{ width: '100%' }}
          >
            {submitting ? (
              <><div className="spinner" style={{ width: 16, height: 16 }}></div> Processing…</>
            ) : (
              '🚀 Submit Claim'
            )}
          </button>
        </form>

        {/* Result */}
        <div>
          {error && (
            <div className="glass-card" style={{ borderColor: 'rgba(244, 63, 94, 0.3)' }}>
              <h3 className="text-rose" style={{ marginBottom: 8 }}>Error</h3>
              <p className="text-secondary">{error}</p>
            </div>
          )}

          {result && (
            <div className="glass-card glass-card--no-hover">
              <div className="flex items-center justify-between mb-16">
                <h3 style={{ fontSize: '1rem', fontWeight: 700 }}>Decision</h3>
                <DecisionBadge decision={result.result?.decision} status={result.status} />
              </div>

              {/* Document Errors */}
              {result.result?.document_errors?.length > 0 && (
                <div className="mb-16">
                  {result.result.document_errors.map((err, i) => (
                    <div key={i} className="doc-error">
                      <div className="doc-error-type">{err.error_type}</div>
                      <div className="doc-error-message">{err.message}</div>
                      <div className="doc-error-action">📎 {err.required_action}</div>
                    </div>
                  ))}
                </div>
              )}

              {/* Amounts */}
              {result.result?.decision && (
                <div className="mb-16">
                  <div className="flex items-center gap-16 mb-8">
                    <div>
                      <div className="text-xs text-tertiary" style={{ textTransform: 'uppercase', letterSpacing: '0.06em', fontWeight: 600 }}>Approved Amount</div>
                      <div className="text-mono" style={{ fontSize: '1.8rem', fontWeight: 800, color: 'var(--accent-emerald)' }}>
                        ₹{(result.result.approved_amount || 0).toLocaleString()}
                      </div>
                    </div>
                    <div>
                      <div className="text-xs text-tertiary" style={{ textTransform: 'uppercase', letterSpacing: '0.06em', fontWeight: 600 }}>Confidence</div>
                      <div className="text-mono" style={{ fontSize: '1.8rem', fontWeight: 800, color: 'var(--accent-blue)' }}>
                        {((result.result.confidence_score || 0) * 100).toFixed(0)}%
                      </div>
                    </div>
                  </div>
                </div>
              )}

              {/* Summary */}
              {result.result?.summary && (
                <div style={{ padding: 12, background: 'var(--bg-glass)', borderRadius: 'var(--radius-sm)', marginBottom: 16 }}>
                  <p className="text-secondary text-sm">{result.result.summary}</p>
                </div>
              )}

              {/* Rejection Reasons */}
              {result.result?.rejection_reasons?.length > 0 && (
                <div className="mb-16">
                  <div className="text-xs text-tertiary mb-8" style={{ fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.06em' }}>Rejection Reasons</div>
                  {result.result.rejection_reasons.map((r, i) => (
                    <span key={i} className="badge badge-rejected" style={{ marginRight: 8, marginBottom: 4 }}>{r}</span>
                  ))}
                </div>
              )}

              {/* Link to full detail */}
              {result.id && (
                <a href={`/claims/${result.id}`} className="btn btn-secondary" style={{ width: '100%' }}>
                  View Full Trace →
                </a>
              )}
            </div>
          )}
        </div>
      </div>
    </>
  );
}
