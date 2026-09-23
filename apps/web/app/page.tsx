'use client';

import { useEffect, useMemo, useState } from 'react';
import {
  ShieldCheck,
  Sparkles,
  FileText,
  MessageSquare,
  BarChart3,
  Settings,
  Check,
  X,
  Pencil,
  RotateCcw,
  Clock3,
  Search,
  SlidersHorizontal,
} from 'lucide-react';

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

const STORAGE_KEY = 'brand-os-token';

type ApprovalStatus = 'PENDING' | 'EDITED' | 'REGENERATED' | 'APPROVED' | 'REJECTED' | 'EXECUTED';

type ApprovalItem = {
  id: number;
  status: ApprovalStatus;
  action_type: string;
  reason: string | null;
  content: string;
};

type Profile = {
  display_name: string;
  tone?: string;
  role?: string;
};

const statusTone: Record<string, { bg: string; color: string }> = {
  PENDING: { bg: '#ecfdf5', color: '#067647' },
  EDITED: { bg: '#fff4e5', color: '#b54708' },
  REGENERATED: { bg: '#eef2ff', color: '#3730a3' },
  APPROVED: { bg: '#ecfdf5', color: '#067647' },
  REJECTED: { bg: '#fee4e2', color: '#b42318' },
  EXECUTED: { bg: '#e0f2fe', color: '#075985' },
};

export default function Home() {
  const [token, setToken] = useState<string | null>(null);
  const [profile, setProfile] = useState<Profile>({ display_name: 'User', role: 'owner' });
  const [queue, setQueue] = useState<ApprovalItem[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [statusFilter, setStatusFilter] = useState<'all' | 'PENDING' | 'EDITED' | 'REGENERATED'>('all');
  const [searchTerm, setSearchTerm] = useState('');
  const [editedBody, setEditedBody] = useState('');
  const [reviewNote, setReviewNote] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [isBusy, setIsBusy] = useState(false);
  const [email, setEmail] = useState('kanishka.utsav@gmail.com');
  const [linkedinUrl, setLinkedinUrl] = useState('https://www.linkedin.com/in/kanishkautsav/');

  useEffect(() => {
    const savedToken = window.localStorage.getItem(STORAGE_KEY);
    if (savedToken) {
      setToken(savedToken);
    }
  }, []);

  const fetchData = async (authToken: string | null = token) => {
    if (!authToken) {
      setQueue([]);
      setSelectedId(null);
      return;
    }

    try {
      const headers = { Authorization: `Bearer ${authToken}` };
      const [profileRes, approvalsRes] = await Promise.all([
        fetch(`${API_BASE}/api/auth/me`, { headers }),
        fetch(`${API_BASE}/api/dashboard/approvals`, { headers }),
      ]);

      if (!profileRes.ok) throw new Error('Authentication failed');
      if (!approvalsRes.ok) throw new Error('Failed to load approval queue');

      const profileJson = await profileRes.json();
      const approvalsJson = await approvalsRes.json();

      const nextQueue: ApprovalItem[] = (approvalsJson.pending_approvals || []).map((item: any) => ({
        id: item.id,
        status: item.status,
        action_type: item.action_type,
        reason: item.reason,
        content: item.content || '',
      }));

      setProfile({
        display_name: profileJson.display_name || 'User',
        tone: profileJson.role || 'owner',
        role: profileJson.role || 'owner',
      });
      setQueue(nextQueue);
      if (!selectedId && nextQueue.length) {
        setSelectedId(nextQueue[0].id);
      }
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : 'Unable to load dashboard data');
    }
  };

  useEffect(() => {
    fetchData(token);
  }, [token]);

  useEffect(() => {
    if (!selectedId && queue.length) {
      setSelectedId(queue[0].id);
      return;
    }

    const selected = queue.find((item) => item.id === selectedId);
    if (selected) {
      setEditedBody(selected.content || '');
      setReviewNote(selected.reason || '');
    }
  }, [selectedId, queue]);

  const filteredQueue = useMemo(() => {
    const query = searchTerm.trim().toLowerCase();
    return queue.filter((item) => {
      const matchesStatus = statusFilter === 'all' || item.status === statusFilter;
      const haystack = `${item.action_type} ${item.content} ${item.reason || ''}`.toLowerCase();
      const matchesSearch = !query || haystack.includes(query);
      return matchesStatus && matchesSearch;
    });
  }, [queue, searchTerm, statusFilter]);

  const selectedApproval = filteredQueue.find((item) => item.id === selectedId) ?? queue.find((item) => item.id === selectedId) ?? null;

  const summary = useMemo(
    () => ({
      pending: queue.filter((item) => ['PENDING', 'EDITED', 'REGENERATED'].includes(item.status)).length,
      reviewed: queue.filter((item) => item.status === 'APPROVED').length,
      rejected: queue.filter((item) => item.status === 'REJECTED').length,
      executed: queue.filter((item) => item.status === 'EXECUTED').length,
    }),
    [queue],
  );

  const runApprovalAction = async (action: 'approve' | 'edit' | 'reject' | 'regenerate', payload?: Record<string, string>) => {
    if (!selectedApproval) return;

    setIsBusy(true);
    setError(null);

    try {
      const res = await fetch(`${API_BASE}/api/approvals/${selectedApproval.id}/${action}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload || {}),
      });

      if (!res.ok) {
        const errorJson = await res.json().catch(() => ({}));
        throw new Error(errorJson.detail || `Action failed: ${action}`);
      }

      await fetchData();
      setReviewNote('');
    } catch (actionError) {
      setError(actionError instanceof Error ? actionError.message : 'Approval action failed');
    } finally {
      setIsBusy(false);
    }
  };

  const handleApprove = () => runApprovalAction('approve');
  const handleEdit = () => runApprovalAction('edit', { edited_body: editedBody, reason: reviewNote || 'Tightened for clarity and audience fit.' });
  const handleReject = () => runApprovalAction('reject', { reason: reviewNote || 'Rejected by reviewer.' });
  const handleRegenerate = () => runApprovalAction('regenerate', { reason: reviewNote || 'Regenerated after review feedback.' });

  const handleLogin = async () => {
    setIsBusy(true);
    setError(null);

    try {
      const res = await fetch(`${API_BASE}/api/auth/linkedin/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, linkedin_url: linkedinUrl }),
      });

      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || 'LinkedIn login is not allowed for this account');
      }

      window.localStorage.setItem(STORAGE_KEY, data.token);
      setToken(data.token);
      setProfile({ display_name: data.display_name || 'User', role: data.role || 'owner' });
    } catch (loginError) {
      setError(loginError instanceof Error ? loginError.message : 'LinkedIn login failed');
    } finally {
      setIsBusy(false);
    }
  };

  if (!token) {
    return (
      <main style={{ minHeight: '100vh', display: 'grid', placeItems: 'center', background: '#f4f7fb', padding: 24 }}>
        <div style={{ background: '#fff', border: '1px solid #e4e7ec', borderRadius: 16, padding: 28, width: '100%', maxWidth: 520 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 8 }}>
            <ShieldCheck size={18} color="#111827" />
            <strong>LinkedIn dashboard access</strong>
          </div>
          <p style={{ color: '#667085', marginTop: 0 }}>Only whitelisted LinkedIn identities can access this dashboard.</p>

          <div style={{ display: 'grid', gap: 14 }}>
            <label style={{ display: 'grid', gap: 6 }}>
              <span style={{ fontWeight: 600 }}>Email</span>
              <input value={email} onChange={(e) => setEmail(e.target.value)} style={{ border: '1px solid #d0d5dd', borderRadius: 10, padding: '10px 12px' }} />
            </label>

            <label style={{ display: 'grid', gap: 6 }}>
              <span style={{ fontWeight: 600 }}>LinkedIn profile URL</span>
              <input value={linkedinUrl} onChange={(e) => setLinkedinUrl(e.target.value)} style={{ border: '1px solid #d0d5dd', borderRadius: 10, padding: '10px 12px' }} />
            </label>

            {error ? <div style={{ background: '#fee4e2', color: '#b42318', padding: 12, borderRadius: 8 }}>{error}</div> : null}

            <button
              type="button"
              disabled={isBusy}
              onClick={handleLogin}
              style={{ background: '#111827', color: '#fff', border: 0, borderRadius: 10, padding: '12px 16px', cursor: 'pointer', fontWeight: 600 }}
            >
              {isBusy ? 'Checking access…' : 'Login with LinkedIn'}
            </button>
          </div>

          <div style={{ marginTop: 18, color: '#667085', fontSize: 12 }}>
            Whitelisted accounts: kanishka.utsav@gmail.com / Kanishka Utsav, pranaybeatking@gmail.com / Kumar Pranay.
          </div>
        </div>
      </main>
    );
  }

  return (
    <main style={{ display: 'grid', gridTemplateColumns: '240px 1fr', minHeight: '100vh', background: '#f4f7fb' }}>
      <aside style={{ background: '#111827', color: '#fff', padding: 24 }}>
        <h2 style={{ marginTop: 0 }}>Brand OS</h2>
        <p style={{ color: '#9ca3af' }}>Personal Brand Manager</p>

        {[['Dashboard', Sparkles], ['Content', FileText], ['Engagement', MessageSquare], ['Analytics', BarChart3], ['Settings', Settings]].map(([label, Icon]: any) => (
          <div key={label} style={{ padding: '12px 8px', display: 'flex', gap: 10, alignItems: 'center', color: '#d1d5db' }}>
            <Icon size={17} />
            {label}
          </div>
        ))}

        <div style={{ marginTop: 32, padding: 12, border: '1px solid #374151', borderRadius: 10, fontSize: 13 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <ShieldCheck size={17} />
            <strong>HITL gate</strong>
          </div>
          <div style={{ marginTop: 8, color: '#d1d5db' }}>External actions are only allowed after approval.</div>
        </div>
      </aside>

      <section style={{ padding: 36, maxWidth: 1200 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div>
            <h1 style={{ margin: '0 0 6px' }}>Good morning, {profile.display_name}</h1>
            <p style={{ color: '#667085', margin: 0 }}>Your AI prepared {summary.pending} items for review.</p>
          </div>
          <button style={{ background: '#b42318', color: '#fff', border: 0, borderRadius: 8, padding: '10px 14px', cursor: 'pointer' }}>
            Emergency Stop
          </button>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, minmax(0, 1fr))', gap: 14, marginTop: 24 }}>
          {[
            { label: 'Pending approval', value: summary.pending },
            { label: 'Reviewed', value: summary.reviewed },
            { label: 'Rejected', value: summary.rejected },
            { label: 'Executed', value: summary.executed },
          ].map((card) => (
            <div key={card.label} style={{ background: '#fff', padding: 18, borderRadius: 12, border: '1px solid #e4e7ec' }}>
              <div style={{ fontSize: 25, fontWeight: 700 }}>{card.value}</div>
              <div style={{ color: '#667085' }}>{card.label}</div>
            </div>
          ))}
        </div>

        <div style={{ marginTop: 28, background: '#fff', border: '1px solid #e4e7ec', borderRadius: 14, padding: 24 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16, gap: 12, flexWrap: 'wrap' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '8px 10px', borderRadius: 999, background: '#eef2ff', color: '#3730a3' }}>
                <Clock3 size={15} />
                Queue
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '8px 10px', borderRadius: 8, border: '1px solid #e4e7ec' }}>
                <Search size={15} />
                <input
                  value={searchTerm}
                  onChange={(e) => setSearchTerm(e.target.value)}
                  placeholder="Search queue"
                  style={{ border: 0, outline: 'none', minWidth: 160, background: 'transparent' }}
                />
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '8px 10px', borderRadius: 8, border: '1px solid #e4e7ec' }}>
                <SlidersHorizontal size={15} />
                <select
                  value={statusFilter}
                  onChange={(e) => setStatusFilter(e.target.value as 'all' | 'PENDING' | 'EDITED' | 'REGENERATED')}
                  style={{ border: 0, outline: 'none', background: 'transparent', color: '#344054' }}
                >
                  <option value="all">All</option>
                  <option value="PENDING">Pending</option>
                  <option value="EDITED">Edited</option>
                  <option value="REGENERATED">Regenerated</option>
                </select>
              </div>
            </div>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 12 }}>
            {filteredQueue.length === 0 ? (
              <div style={{ padding: 18, border: '1px dashed #d0d5dd', borderRadius: 10, color: '#667085' }}>No approvals match the current filter.</div>
            ) : (
              filteredQueue.map((item) => (
                <button
                  key={item.id}
                  type="button"
                  onClick={() => setSelectedId(item.id)}
                  style={{
                    textAlign: 'left',
                    background: selectedApproval?.id === item.id ? '#eef2ff' : '#f8fafc',
                    padding: 14,
                    borderRadius: 10,
                    border: selectedApproval?.id === item.id ? '1px solid #c7d2fe' : '1px solid #e4e7ec',
                    cursor: 'pointer',
                    color: '#111827',
                  }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8 }}>
                    <span style={{ fontSize: 12, color: '#667085' }}>POST #{item.id}</span>
                    <span
                      style={{
                        fontSize: 12,
                        padding: '4px 8px',
                        borderRadius: 999,
                        background: statusTone[item.status]?.bg || '#eef2ff',
                        color: statusTone[item.status]?.color || '#3730a3',
                      }}
                    >
                      {item.status}
                    </span>
                  </div>
                  <div style={{ fontWeight: 700, marginBottom: 8 }}>{item.action_type}</div>
                  <div style={{ fontSize: 12, color: '#667085', marginBottom: 6 }}>{item.reason || 'No review note yet'}</div>
                  <div style={{ fontSize: 12, color: '#667085' }}>
                    {item.content ? item.content.slice(0, 80) + (item.content.length > 80 ? '…' : '') : 'No draft content available.'}
                  </div>
                </button>
              ))
            )}
          </div>
        </div>

        <div style={{ marginTop: 28, background: '#fff', border: '1px solid #e4e7ec', borderRadius: 14, padding: 24 }}>
          {selectedApproval ? (
            <>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
                <div>
                  <span style={{ fontSize: 12, color: '#667085' }}>POST #{selectedApproval.id} · {selectedApproval.action_type}</span>
                  <h2 style={{ margin: '8px 0 0' }}>{selectedApproval.action_type}</h2>
                </div>
                <span
                  style={{
                    background: statusTone[selectedApproval.status]?.bg || '#fff4e5',
                    color: statusTone[selectedApproval.status]?.color || '#b54708',
                    padding: '6px 10px',
                    borderRadius: 20,
                    height: 22,
                    fontSize: 12,
                    display: 'inline-flex',
                    alignItems: 'center',
                  }}
                >
                  {selectedApproval.status}
                </span>
              </div>

              <textarea
                value={editedBody}
                onChange={(e) => setEditedBody(e.target.value)}
                style={{ width: '100%', minHeight: 200, marginTop: 18, padding: 16, borderRadius: 10, border: '1px solid #d0d5dd', resize: 'vertical', fontFamily: 'inherit' }}
              />

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14, marginTop: 18 }}>
                <div>
                  <b>Why this?</b>
                  <p style={{ color: '#667085', margin: '8px 0 0' }}>
                    The draft aligns with your expertise and keeps the message practical, grounded, and audience-focused.
                  </p>
                </div>
                <div>
                  <b>Guardrails</b>
                  <p style={{ color: '#667085', margin: '8px 0 0' }}>Identity: passed · Brand: passed · Duplicate: passed · Claim risk: low</p>
                </div>
              </div>

              <div style={{ marginTop: 18 }}>
                <label style={{ display: 'block', fontWeight: 600, marginBottom: 8 }}>Review note</label>
                <textarea
                  value={reviewNote}
                  onChange={(e) => setReviewNote(e.target.value)}
                  placeholder="Add context for the next decision..."
                  style={{ width: '100%', minHeight: 90, padding: 12, borderRadius: 10, border: '1px solid #d0d5dd', resize: 'vertical', fontFamily: 'inherit' }}
                />
              </div>

              {error ? (
                <div style={{ marginTop: 16, color: '#b42318', background: '#fee4e2', borderRadius: 8, padding: 12 }}>{error}</div>
              ) : null}

              <div style={{ display: 'flex', gap: 10, marginTop: 20, flexWrap: 'wrap' }}>
                {[
                  { label: 'Approve', action: handleApprove, color: '#067647', icon: Check },
                  { label: 'Edit', action: handleEdit, color: '#344054', icon: Pencil },
                  { label: 'Regenerate', action: handleRegenerate, color: '#344054', icon: RotateCcw },
                  { label: 'Reject', action: handleReject, color: '#b42318', icon: X },
                ].map(({ label, action, color, icon: Icon }) => (
                  <button
                    key={label}
                    type="button"
                    disabled={isBusy}
                    onClick={action}
                    style={{
                      display: 'flex',
                      gap: 7,
                      alignItems: 'center',
                      padding: '10px 14px',
                      borderRadius: 8,
                      border: '1px solid #d0d5dd',
                      background: label === 'Approve' ? '#067647' : '#fff',
                      color: label === 'Approve' ? '#fff' : color,
                      cursor: isBusy ? 'not-allowed' : 'pointer',
                      opacity: isBusy ? 0.75 : 1,
                    }}
                  >
                    <Icon size={16} />
                    {label}
                  </button>
                ))}
              </div>
            </>
          ) : (
            <div style={{ color: '#667085' }}>Select an item from the queue to review it.</div>
          )}
        </div>
      </section>
    </main>
  );
}
