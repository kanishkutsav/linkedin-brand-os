'use client';

import { useEffect, useMemo, useState } from 'react';
import {
  ShieldCheck, Sparkles, FileText, MessageSquare, BarChart3, Settings,
  Check, X, Pencil, RotateCcw, Clock3, Search, SlidersHorizontal,
  Plus, LogOut, Zap, ExternalLink
} from 'lucide-react';

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
const STORAGE_KEY = 'brand-os-token';

type ApprovalStatus = 'PENDING' | 'EDITED' | 'REGENERATED' | 'APPROVED' | 'REJECTED' | 'EXECUTED';
type ApprovalItem = { id: number; status: ApprovalStatus; action_type: string; reason: string | null; content: string };
type Profile = { display_name: string; role?: string };
type LinkedInStatus = { connected: boolean; name?: string | null; email?: string | null; expires_at?: string | null };
type Tab = 'Dashboard' | 'Content' | 'Engagement' | 'Analytics' | 'Settings';

const statusTone: Record<string, { bg: string; color: string }> = {
  PENDING: { bg: '#ecfdf5', color: '#067647' }, EDITED: { bg: '#fff4e5', color: '#b54708' },
  REGENERATED: { bg: '#eef2ff', color: '#3730a3' }, APPROVED: { bg: '#ecfdf5', color: '#067647' },
  REJECTED: { bg: '#fee4e2', color: '#b42318' }, EXECUTED: { bg: '#e0f2fe', color: '#075985' },
};

export default function Home() {
  const [token, setToken] = useState<string | null>(null);
  const [profile, setProfile] = useState<Profile>({ display_name: 'User', role: 'owner' });
  const [linkedin, setLinkedin] = useState<LinkedInStatus>({ connected: false });
  const [queue, setQueue] = useState<ApprovalItem[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [statusFilter, setStatusFilter] = useState<'all' | 'PENDING' | 'EDITED' | 'REGENERATED'>('all');
  const [searchTerm, setSearchTerm] = useState('');
  const [editedBody, setEditedBody] = useState('');
  const [reviewNote, setReviewNote] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [isBusy, setIsBusy] = useState(false);
  const [tab, setTab] = useState<Tab>('Dashboard');
  const [draftTitle, setDraftTitle] = useState('');
  const [draftTopic, setDraftTopic] = useState('');
  const [draftBody, setDraftBody] = useState('');

  const headers = (authToken = token) => authToken ? { Authorization: `Bearer ${authToken}` } : {};

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const code = params.get('linkedin_code');
    const savedToken = window.localStorage.getItem(STORAGE_KEY);

    if (code) {
      window.history.replaceState({}, document.title, window.location.pathname);
      fetch(`${API_BASE}/api/auth/linkedin/exchange`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(code),
      })
        .then(async (res) => {
          const data = await res.json();
          if (!res.ok) throw new Error(data.detail || 'LinkedIn connection failed');
          window.localStorage.setItem(STORAGE_KEY, data.token);
          setToken(data.token);
          setNotice('LinkedIn account connected successfully.');
        })
        .catch((e) => setError(e instanceof Error ? e.message : 'LinkedIn connection failed'));
      return;
    }
    if (savedToken) setToken(savedToken);
  }, []);

  const fetchData = async (authToken: string | null = token) => {
    if (!authToken) return;
    try {
      const [profileRes, approvalsRes, linkedinRes] = await Promise.all([
        fetch(`${API_BASE}/api/auth/me`, { headers: headers(authToken) }),
        fetch(`${API_BASE}/api/dashboard/approvals`, { headers: headers(authToken) }),
        fetch(`${API_BASE}/api/linkedin/status`, { headers: headers(authToken) }),
      ]);
      if (profileRes.status === 401 || approvalsRes.status === 401) {
        window.localStorage.removeItem(STORAGE_KEY);
        setToken(null);
        setQueue([]);
        setLinkedin({ connected: false });
        throw new Error('Your session expired. Please sign in with LinkedIn again.');
      }
      if (!profileRes.ok || !approvalsRes.ok) throw new Error('Unable to load dashboard data.');
      const profileJson = await profileRes.json();
      const approvalsJson = await approvalsRes.json();
      setProfile({ display_name: profileJson.display_name || 'User', role: profileJson.role || 'owner' });
      setLinkedInSafe(linkedinRes.ok ? await linkedinRes.json() : { connected: false });
      const nextQueue: ApprovalItem[] = (approvalsJson.pending_approvals || []).map((item: any) => ({
        id: item.id, status: item.status, action_type: item.action_type, reason: item.reason, content: item.content || '',
      }));
      setQueue(nextQueue);
      if (!selectedId && nextQueue.length) setSelectedId(nextQueue[0].id);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Unable to load dashboard data');
    }
  };

  const setLinkedInSafe = (value: LinkedInStatus) => setLinkedin(value);

  useEffect(() => { fetchData(token); }, [token]);

  useEffect(() => {
    const selected = queue.find((item) => item.id === selectedId);
    if (selected) { setEditedBody(selected.content || ''); setReviewNote(selected.reason || ''); }
  }, [selectedId, queue]);

  const filteredQueue = useMemo(() => {
    const query = searchTerm.trim().toLowerCase();
    return queue.filter((item) => {
      const matchesStatus = statusFilter === 'all' || item.status === statusFilter;
      const haystack = `${item.action_type} ${item.content} ${item.reason || ''}`.toLowerCase();
      return matchesStatus && (!query || haystack.includes(query));
    });
  }, [queue, searchTerm, statusFilter]);

  const selectedApproval = queue.find((item) => item.id === selectedId) ?? null;
  const summary = useMemo(() => ({
    pending: queue.filter((i) => ['PENDING', 'EDITED', 'REGENERATED'].includes(i.status)).length,
    reviewed: queue.filter((i) => i.status === 'APPROVED').length,
    rejected: queue.filter((i) => i.status === 'REJECTED').length,
    executed: queue.filter((i) => i.status === 'EXECUTED').length,
  }), [queue]);

  const connectLinkedIn = () => {
    window.location.href = `${API_BASE}/api/auth/linkedin/start`;
  };

  const logout = () => {
    window.localStorage.removeItem(STORAGE_KEY);
    setToken(null);
    setQueue([]);
    setLinkedin({ connected: false });
  };

  const runApprovalAction = async (action: 'approve' | 'edit' | 'reject' | 'regenerate', payload?: Record<string, string>) => {
    if (!selectedApproval || !token) return;
    setIsBusy(true); setError(null); setNotice(null);
    try {
      const res = await fetch(`${API_BASE}/api/approvals/${selectedApproval.id}/${action}`, {
        method: 'POST',
        headers: { ...headers(), 'Content-Type': 'application/json' },
        body: JSON.stringify(payload || {}),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || `Action failed: ${action}`);
      await fetchData();
      setReviewNote('');
      setNotice(`${action.charAt(0).toUpperCase() + action.slice(1)} completed.`);
    } catch (e) { setError(e instanceof Error ? e.message : 'Approval action failed'); }
    finally { setIsBusy(false); }
  };

  const createDraft = async () => {
    if (!token || !draftTitle.trim() || !draftTopic.trim() || !draftBody.trim()) {
      setError('Title, topic and draft body are required.'); return;
    }
    setIsBusy(true); setError(null); setNotice(null);
    try {
      const res = await fetch(`${API_BASE}/api/content/drafts`, {
        method: 'POST',
        headers: { ...headers(), 'Content-Type': 'application/json' },
        body: JSON.stringify({ title: draftTitle, topic: draftTopic, pillar: 'Expertise', body: draftBody }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || 'Draft creation failed');
      setDraftTitle(''); setDraftTopic(''); setDraftBody('');
      setTab('Dashboard');
      await fetchData();
      setNotice(data.approval_id ? 'Draft created and added to the HITL approval queue.' : 'Draft created but guardrails require edits.');
    } catch (e) { setError(e instanceof Error ? e.message : 'Draft creation failed'); }
    finally { setIsBusy(false); }
  };

  if (!token) {
    return (
      <main style={{ minHeight: '100vh', display: 'grid', placeItems: 'center', background: '#f4f7fb', padding: 24 }}>
        <div style={{ background: '#fff', border: '1px solid #e4e7ec', borderRadius: 18, padding: 32, width: '100%', maxWidth: 520, boxShadow: '0 20px 60px rgba(16,24,40,.08)' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 8 }}><ShieldCheck size={20} /><strong>LinkedIn Brand OS</strong></div>
          <h1 style={{ margin: '10px 0 8px' }}>Connect your LinkedIn account</h1>
          <p style={{ color: '#667085' }}>Brand OS uses LinkedIn's official OAuth flow. Your LinkedIn password is never entered into Brand OS.</p>
          {error && <div style={{ background: '#fee4e2', color: '#b42318', padding: 12, borderRadius: 8, margin: '14px 0' }}>{error}</div>}
          <button type="button" onClick={connectLinkedIn} style={{ width: '100%', background: '#0a66c2', color: '#fff', border: 0, borderRadius: 10, padding: 14, cursor: 'pointer', fontWeight: 700, display: 'flex', justifyContent: 'center', gap: 8, alignItems: 'center' }}>
            <LinkedInMark size={18} /> Continue with LinkedIn
          </button>
          <p style={{ fontSize: 12, color: '#98a2b3', marginTop: 18 }}>Access is restricted to approved Brand OS users. OAuth permissions requested: profile, email and posting on your behalf.</p>
        </div>
      </main>
    );
  }

  const nav = [
    ['Dashboard', Sparkles], ['Content', FileText], ['Engagement', MessageSquare],
    ['Analytics', BarChart3], ['Settings', Settings],
  ] as const;

  return (
    <main style={{ display: 'grid', gridTemplateColumns: '240px 1fr', minHeight: '100vh', background: '#f4f7fb' }}>
      <aside style={{ background: '#111827', color: '#fff', padding: 24, position: 'sticky', top: 0, height: '100vh', boxSizing: 'border-box' }}>
        <h2 style={{ marginTop: 0 }}>Brand OS</h2>
        <p style={{ color: '#9ca3af', marginBottom: 26 }}>Personal Brand Manager</p>
        {nav.map(([label, Icon]) => (
          <button key={label} type="button" onClick={() => setTab(label)} style={{ width: '100%', textAlign: 'left', padding: '12px 10px', marginBottom: 4, display: 'flex', gap: 10, alignItems: 'center', border: 0, borderRadius: 8, background: tab === label ? '#273244' : 'transparent', color: '#fff', cursor: 'pointer' }}>
            <Icon size={17} />{label}
          </button>
        ))}
        <button type="button" onClick={connectLinkedIn} style={{ width: '100%', marginTop: 24, border: '1px solid #475467', borderRadius: 8, padding: '10px', background: linkedin.connected ? '#153e2c' : '#1d2939', color: '#fff', cursor: 'pointer', display: 'flex', gap: 8, alignItems: 'center' }}>
          <LinkedInMark size={16} /> {linkedin.connected ? 'LinkedIn connected' : 'Connect LinkedIn'}
        </button>
        <div style={{ marginTop: 24, padding: 12, border: '1px solid #374151', borderRadius: 10, fontSize: 13 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}><ShieldCheck size={17} /><strong>HITL gate</strong></div>
          <div style={{ marginTop: 8, color: '#d1d5db' }}>No external LinkedIn action is executed without your approval.</div>
        </div>
        <button type="button" onClick={logout} style={{ marginTop: 24, background: 'transparent', border: 0, color: '#9ca3af', cursor: 'pointer', display: 'flex', gap: 8, alignItems: 'center' }}><LogOut size={15}/> Sign out</button>
      </aside>

      <section style={{ padding: 36, maxWidth: 1250, width: '100%', boxSizing: 'border-box' }}>
        {notice && <div style={{ background: '#ecfdf3', color: '#067647', border: '1px solid #abefc6', padding: 12, borderRadius: 8, marginBottom: 16 }}>{notice}</div>}
        {error && <div style={{ background: '#fee4e2', color: '#b42318', border: '1px solid #fecdca', padding: 12, borderRadius: 8, marginBottom: 16 }}>{error}</div>}

        {tab === 'Dashboard' && <>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 20, flexWrap: 'wrap' }}>
            <div><h1 style={{ margin: '0 0 6px' }}>Good morning, {profile.display_name}</h1><p style={{ color: '#667085', margin: 0 }}>Your AI-prepared work stays behind the human approval gate.</p></div>
            <div style={{ display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '9px 12px', borderRadius: 999, background: linkedin.connected ? '#ecfdf3' : '#fff4e5', color: linkedin.connected ? '#067647' : '#b54708', border: '1px solid #e4e7ec', fontSize: 13, fontWeight: 700 }}>
                <span style={{ width: 8, height: 8, borderRadius: '50%', background: linkedin.connected ? '#12b76a' : '#f79009' }} />
                {linkedin.connected ? 'LinkedIn connected' : 'LinkedIn not connected'}
              </div>
              <button type="button" onClick={connectLinkedIn} style={{ background: linkedin.connected ? '#153e2c' : '#0a66c2', color: '#fff', border: 0, borderRadius: 8, padding: '10px 14px', cursor: 'pointer', display: 'flex', gap: 8, alignItems: 'center', fontWeight: 700 }}>
                <LinkedInMark size={16}/>{linkedin.connected ? 'Reconnect LinkedIn' : 'Connect LinkedIn'}
              </button>
              <button type="button" onClick={logout} style={{ background: '#fff', color: '#344054', border: '1px solid #d0d5dd', borderRadius: 8, padding: '10px 14px', cursor: 'pointer', display: 'flex', gap: 8, alignItems: 'center', fontWeight: 600 }}>
                <LogOut size={16}/> Sign out
              </button>
            </div>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, minmax(0, 1fr))', gap: 14, marginTop: 24 }}>
            {[['Pending approval', summary.pending], ['Reviewed', summary.reviewed], ['Rejected', summary.rejected], ['Executed', summary.executed]].map(([label, value]) => (
              <div key={String(label)} style={{ background: '#fff', padding: 18, borderRadius: 12, border: '1px solid #e4e7ec' }}><div style={{ fontSize: 25, fontWeight: 700 }}>{value}</div><div style={{ color: '#667085' }}>{label}</div></div>
            ))}
          </div>

          <div style={{ marginTop: 28, background: '#fff', border: '1px solid #e4e7ec', borderRadius: 14, padding: 24 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16, gap: 12, flexWrap: 'wrap' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '8px 10px', borderRadius: 999, background: '#eef2ff', color: '#3730a3' }}><Clock3 size={15}/> Queue</div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '8px 10px', borderRadius: 8, border: '1px solid #e4e7ec' }}><Search size={15}/><input value={searchTerm} onChange={(e) => setSearchTerm(e.target.value)} placeholder="Search queue" style={{ border: 0, outline: 'none', minWidth: 160 }} /></div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '8px 10px', borderRadius: 8, border: '1px solid #e4e7ec' }}><SlidersHorizontal size={15}/><select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value as any)} style={{ border: 0, outline: 'none' }}><option value="all">All</option><option value="PENDING">Pending</option><option value="EDITED">Edited</option><option value="REGENERATED">Regenerated</option></select></div>
              </div>
              <button type="button" onClick={() => setTab('Content')} style={{ background: '#111827', color: '#fff', border: 0, borderRadius: 8, padding: '9px 12px', cursor: 'pointer', display: 'flex', gap: 7, alignItems: 'center' }}><Plus size={15}/> New draft</button>
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 12 }}>
              {filteredQueue.length === 0 ? <div style={{ padding: 18, border: '1px dashed #d0d5dd', borderRadius: 10, color: '#667085' }}>No approvals match the current filter. Create a draft to populate the HITL queue.</div> :
                filteredQueue.map((item) => <button key={item.id} type="button" onClick={() => setSelectedId(item.id)} style={{ textAlign: 'left', background: selectedId === item.id ? '#eef2ff' : '#f8fafc', padding: 14, borderRadius: 10, border: '1px solid #e4e7ec', cursor: 'pointer', color: '#111827' }}><div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8 }}><span style={{ fontSize: 12, color: '#667085' }}>POST #{item.id}</span><span style={{ fontSize: 12, padding: '4px 8px', borderRadius: 999, background: statusTone[item.status]?.bg, color: statusTone[item.status]?.color }}>{item.status}</span></div><div style={{ fontWeight: 700, marginBottom: 8 }}>{item.action_type}</div><div style={{ fontSize: 12, color: '#667085' }}>{item.content.slice(0, 100)}{item.content.length > 100 ? '…' : ''}</div></button>)
              }
            </div>
          </div>

          <div style={{ marginTop: 28, background: '#fff', border: '1px solid #e4e7ec', borderRadius: 14, padding: 24 }}>
            {selectedApproval ? <><div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}><div><span style={{ fontSize: 12, color: '#667085' }}>POST #{selectedApproval.id} · {selectedApproval.action_type}</span><h2 style={{ margin: '8px 0 0' }}>Review draft</h2></div><span style={{ background: statusTone[selectedApproval.status]?.bg, color: statusTone[selectedApproval.status]?.color, padding: '6px 10px', borderRadius: 20, fontSize: 12 }}>{selectedApproval.status}</span></div>
              <textarea value={editedBody} onChange={(e) => setEditedBody(e.target.value)} style={{ width: '100%', minHeight: 200, marginTop: 18, padding: 16, borderRadius: 10, border: '1px solid #d0d5dd', boxSizing: 'border-box', fontFamily: 'inherit' }}/>
              <textarea value={reviewNote} onChange={(e) => setReviewNote(e.target.value)} placeholder="Review note..." style={{ width: '100%', minHeight: 80, marginTop: 14, padding: 12, borderRadius: 10, border: '1px solid #d0d5dd', boxSizing: 'border-box', fontFamily: 'inherit' }}/>
              <div style={{ display: 'flex', gap: 10, marginTop: 16, flexWrap: 'wrap' }}>
                {[
                  ['Approve', () => runApprovalAction('approve'), Check, '#067647'],
                  ['Edit', () => runApprovalAction('edit', { edited_body: editedBody, reason: reviewNote || 'Edited during review.' }), Pencil, '#344054'],
                  ['Regenerate', () => runApprovalAction('regenerate', { reason: reviewNote || 'Regenerated after review.' }), RotateCcw, '#344054'],
                  ['Reject', () => runApprovalAction('reject', { reason: reviewNote || 'Rejected by reviewer.' }), X, '#b42318'],
                ].map(([label, action, Icon, color]: any) => <button key={String(label)} type="button" disabled={isBusy} onClick={action} style={{ display: 'flex', gap: 7, alignItems: 'center', padding: '10px 14px', borderRadius: 8, border: '1px solid #d0d5dd', background: label === 'Approve' ? '#067647' : '#fff', color: label === 'Approve' ? '#fff' : color, cursor: 'pointer' }}><Icon size={16}/>{label}</button>)}
              </div>
            </> : <div style={{ color: '#667085' }}>Select a queue item to review it.</div>}
          </div>
        </>}

        {tab === 'Content' && <div style={{ background: '#fff', border: '1px solid #e4e7ec', borderRadius: 14, padding: 28 }}>
          <h2 style={{ marginTop: 0 }}>Content Studio</h2><p style={{ color: '#667085' }}>Create a draft. Guardrails decide whether it enters the approval queue.</p>
          <div style={{ display: 'grid', gap: 14, maxWidth: 850 }}>
            <input value={draftTitle} onChange={(e) => setDraftTitle(e.target.value)} placeholder="Post title" style={{ padding: 12, border: '1px solid #d0d5dd', borderRadius: 8 }}/>
            <input value={draftTopic} onChange={(e) => setDraftTopic(e.target.value)} placeholder="Topic / theme" style={{ padding: 12, border: '1px solid #d0d5dd', borderRadius: 8 }}/>
            <textarea value={draftBody} onChange={(e) => setDraftBody(e.target.value)} placeholder="Write or paste the post draft..." style={{ minHeight: 260, padding: 14, border: '1px solid #d0d5dd', borderRadius: 8, fontFamily: 'inherit' }}/>
            <button type="button" disabled={isBusy} onClick={createDraft} style={{ width: 'fit-content', background: '#111827', color: '#fff', border: 0, borderRadius: 8, padding: '11px 16px', cursor: 'pointer', display: 'flex', gap: 8, alignItems: 'center' }}><Zap size={16}/> Send to HITL queue</button>
          </div>
        </div>}

        {tab === 'Engagement' && <Panel title="Engagement" text="This area is now wired as a real navigation surface. LinkedIn reading, comments and reactions should only be added through officially supported permissions and explicit approval."/>}
        {tab === 'Analytics' && <Panel title="Analytics" text="Performance analytics surface is ready. It will show published-post metrics once LinkedIn read/analytics permissions are provisioned for this application."/>}
        {tab === 'Settings' && <div style={{ background: '#fff', border: '1px solid #e4e7ec', borderRadius: 14, padding: 28 }}><h2 style={{ marginTop: 0 }}>Settings</h2><p style={{ color: '#667085' }}>Signed in as <b>{profile.display_name}</b>.</p><div style={{ display: 'flex', gap: 10, alignItems: 'center', marginTop: 18 }}><LinkedInMark size={20} color="#0a66c2"/><div><b>{linkedin.connected ? 'LinkedIn connected' : 'LinkedIn not connected'}</b><div style={{ color: '#667085', fontSize: 13 }}>{linkedin.email || 'Connect your account to enable official API actions.'}</div></div><button type="button" onClick={connectLinkedIn} style={{ marginLeft: 'auto', padding: '9px 12px', borderRadius: 8, border: '1px solid #d0d5dd', background: '#fff', cursor: 'pointer' }}>{linkedin.connected ? 'Reconnect' : 'Connect'}</button></div><a href="https://www.linkedin.com/" target="_blank" rel="noreferrer" style={{ display: 'inline-flex', gap: 7, alignItems: 'center', marginTop: 24, color: '#0a66c2' }}>Open LinkedIn <ExternalLink size={14}/></a></div>}
      </section>
    </main>
  );
}

function LinkedInMark({ size = 18, color }: { size?: number; color?: string }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill={color || "currentColor"} aria-hidden="true">
      <path d="M6.5 8.2H3.2V20h3.3V8.2ZM4.85 3A1.95 1.95 0 1 0 4.85 6.9 1.95 1.95 0 0 0 4.85 3ZM20.8 13.25c0-3.52-1.88-5.16-4.4-5.16-2.02 0-2.92 1.11-3.43 1.89V8.2H9.67V20h3.3v-5.84c0-1.54.29-3.03 2.2-3.03 1.88 0 1.91 1.76 1.91 3.13V20h3.3l.02-6.75Z"/>
    </svg>
  );
}

function Panel({ title, text }: { title: string; text: string }) {
  return <div style={{ background: '#fff', border: '1px solid #e4e7ec', borderRadius: 14, padding: 28 }}><h2 style={{ marginTop: 0 }}>{title}</h2><p style={{ color: '#667085', lineHeight: 1.6 }}>{text}</p></div>;
}
