'use client';

import { useEffect, useMemo, useState } from 'react';
import {
  ShieldCheck, Sparkles, FileText, MessageSquare, BarChart3, Settings,
  Check, X, Pencil, RotateCcw, Clock3, Search, SlidersHorizontal,
  Plus, LogOut, Zap, ExternalLink
} from 'lucide-react';

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

function getApiError(data: any, fallback: string) {
  if (typeof data?.detail === 'string') return data.detail;
  if (Array.isArray(data?.detail)) return data.detail.map((item: any) => item?.msg || String(item)).join('; ');
  if (typeof data?.message === 'string') return data.message;
  return fallback;
}
const STORAGE_KEY = 'brand-os-token';

type ApprovalStatus = 'PENDING' | 'EDITED' | 'REGENERATED' | 'APPROVED' | 'REJECTED' | 'EXECUTED';
type ApprovalItem = { id: number; status: ApprovalStatus; action_type: string; reason: string | null; content: string };
type Profile = { display_name: string; role?: string };
type LinkedInStatus = { connected: boolean; name?: string | null; email?: string | null; expires_at?: string | null };
type BrandStatus = {
  ready: boolean;
  status: string;
  source_post_count: number;
  current_post_count?: number;
  continuous_learning?: boolean;
  historical_import_optional?: boolean;
  last_updated?: string | null;
  summary?: string | null;
  profile?: { display_name?: string; professional_title?: string | null; industry?: string | null; audience?: string | null; brand_positioning?: string | null; tone?: string | null }
};
type Opportunity = { id: number; title: string; topic: string; angle: string; pillar: string; format?: string; objective?: string; total_score: number; scores: Record<string, number>; rationale?: string; evidence?: { summary?: string; why_now?: string; source_hints?: string[]; grounding_queries?: string[] }; source_ids?: number[]; sources?: { title?: string; url?: string; domain?: string }[] };
type Tab = 'Dashboard' | 'Research' | 'Content' | 'Engagement' | 'Analytics' | 'Settings';

const statusTone: Record<string, { bg: string; color: string }> = {
  PENDING: { bg: '#ecfdf5', color: '#067647' }, EDITED: { bg: '#fff4e5', color: '#b54708' },
  REGENERATED: { bg: '#eef2ff', color: '#3730a3' }, APPROVED: { bg: '#ecfdf5', color: '#067647' },
  REJECTED: { bg: '#fee4e2', color: '#b42318' }, EXECUTED: { bg: '#e0f2fe', color: '#075985' },
};

export default function Home() {
  const [token, setToken] = useState<string | null>(null);
  const [profile, setProfile] = useState<Profile>({ display_name: 'User', role: 'owner' });
  const [linkedin, setLinkedin] = useState<LinkedInStatus>({ connected: false });
  const [brand, setBrand] = useState<BrandStatus>({ ready: false, status: 'NOT_INITIALIZED', source_post_count: 0 });
  const [brandTitle, setBrandTitle] = useState('');
  const [brandIndustry, setBrandIndustry] = useState('');
  const [brandAudience, setBrandAudience] = useState('');
  const [brandPositioning, setBrandPositioning] = useState('');
  const [brandTone, setBrandTone] = useState('');
  const [brandGoals, setBrandGoals] = useState('');
  const [historicalPosts, setHistoricalPosts] = useState('');
  const [isBuildingBrand, setIsBuildingBrand] = useState(false);
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
  const [isGenerating, setIsGenerating] = useState(false);
  const [opportunities, setOpportunities] = useState<Opportunity[]>([]);
  const [isResearching, setIsResearching] = useState(false);

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
        body: JSON.stringify({ code }),
      })
        .then(async (res) => {
          const data = await res.json();
          if (!res.ok) throw new Error(getApiError(data, 'LinkedIn connection failed'));
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
      const [profileRes, approvalsRes, linkedinRes, brandRes, opportunityRes] = await Promise.all([
        fetch(`${API_BASE}/api/auth/me`, { headers: headers(authToken) }),
        fetch(`${API_BASE}/api/dashboard/approvals`, { headers: headers(authToken) }),
        fetch(`${API_BASE}/api/linkedin/status`, { headers: headers(authToken) }),
        fetch(`${API_BASE}/api/brand/status`, { headers: headers(authToken) }),
        fetch(`${API_BASE}/api/research/opportunities`, { headers: headers(authToken) }),
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
      const brandJson = brandRes.ok ? await brandRes.json() : { ready: false, status: 'NOT_INITIALIZED', source_post_count: 0 };
      setBrand(brandJson);
      const brandProfile = brandJson.profile || {};
      setBrandTitle(brandProfile.professional_title || '');
      setBrandIndustry(brandProfile.industry || '');
      setBrandAudience(brandProfile.audience || '');
      setBrandPositioning(brandProfile.brand_positioning || '');
      setBrandTone(brandProfile.tone || '');
      const opportunityJson = opportunityRes.ok ? await opportunityRes.json() : { opportunities: [] };
      setOpportunities(opportunityJson.opportunities || []);
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

  const generateContent = async () => {
    if (!token) return;
    if (!brand.ready) {
      setTab('Settings');
      setError('Complete the lightweight Brand Intelligence setup first. Historical posts are optional.');
      return;
    }
    setIsGenerating(true); setError(null); setNotice(null);
    try {
      const res = await fetch(API_BASE + '/api/agent/events', {
        method: 'POST',
        headers: { ...headers(), 'Content-Type': 'application/json' },
        body: JSON.stringify({
          event_type: 'manual_generate_content',
          payload: { objective: 'Generate a fresh LinkedIn content opportunity for human review.' }
        }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(getApiError(data, 'Content generation failed'));
      await fetchData();
      setTab('Dashboard');
      setNotice(data.created_count ? 'New content suggestion generated and added to the approval queue.' : 'No new suggestion was created. The agent may have detected a duplicate.');
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Content generation failed');
    } finally {
      setIsGenerating(false);
    }
  };

  const discoverResearch = async () => {
    if (!token) return;
    if (!brand.ready) {
      setTab('Settings');
      setError('Complete the lightweight Brand Intelligence setup before running live research.');
      return;
    }
    setIsResearching(true); setError(null); setNotice(null);
    try {
      const res = await fetch(API_BASE + '/api/research/discover', {
        method: 'POST',
        headers: { ...headers(), 'Content-Type': 'application/json' },
        body: JSON.stringify({}),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(getApiError(data, 'Live research failed'));
      setOpportunities(data.opportunities || []);
      setNotice('Fresh research completed. Opportunities were ranked using Brand Fit, relevance, timeliness, evidence, novelty and risk.');
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Live research failed');
    } finally {
      setIsResearching(false);
    }
  };

  const buildBrand = async () => {
    if (!token) return;
    const blocks = historicalPosts.split(/\n---POST---\n|\n---POST---\r?\n/).map((body) => body.trim()).filter(Boolean);
    setIsBuildingBrand(true); setError(null); setNotice(null);
    try {
      const res = await fetch(API_BASE + '/api/brand/onboard', {
        method: 'POST',
        headers: { ...headers(), 'Content-Type': 'application/json' },
        body: JSON.stringify({
          display_name: profile.display_name,
          professional_title: brandTitle || null,
          industry: brandIndustry || null,
          audience: brandAudience || null,
          goals: brandGoals.split(',').map((x) => x.trim()).filter(Boolean),
          brand_positioning: brandPositioning || null,
          tone: brandTone || null,
          posts: blocks.map((body) => ({ body })),
        }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(getApiError(data, 'Brand Intelligence setup failed'));
      setBrand({ ...data.brand_memory, ready: data.brand_memory?.status === 'READY' });
      setHistoricalPosts('');
      setNotice(blocks.length
        ? 'Brand Intelligence initialized using your profile plus ' + blocks.length + ' imported post' + (blocks.length === 1 ? '' : 's') + '. It will continue learning from new Brand OS activity.'
        : 'Brand Intelligence initialized from your professional profile. Historical posts remain optional and can be added later.');
      await fetchData();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Brand Intelligence setup failed');
    } finally {
      setIsBuildingBrand(false);
    }
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
    ['Dashboard', Sparkles], ['Research', Search], ['Content', FileText], ['Engagement', MessageSquare],
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
              <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
                <button type="button" onClick={generateContent} disabled={isGenerating} style={{ background: '#111827', color: '#fff', border: 0, borderRadius: 8, padding: '9px 14px', cursor: isGenerating ? 'wait' : 'pointer', display: 'flex', gap: 7, alignItems: 'center', fontWeight: 700, opacity: isGenerating ? 0.7 : 1 }}>
                  <Sparkles size={15}/> {isGenerating ? 'Generating…' : 'Generate content'}
                </button>
                <button type="button" onClick={() => setTab('Research')} style={{ background: '#fff', color: '#344054', border: '1px solid #d0d5dd', borderRadius: 8, padding: '9px 12px', cursor: 'pointer', display: 'flex', gap: 7, alignItems: 'center' }}><Search size={15}/> Research</button>
              </div>
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

        {tab === 'Research' && <div style={{ display: 'grid', gap: 18 }}>
          <div style={{ background: '#fff', border: '1px solid #e4e7ec', borderRadius: 14, padding: 24 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', gap: 16, alignItems: 'center', flexWrap: 'wrap' }}>
              <div><h2 style={{ margin: 0 }}>Research & Content Opportunities</h2><p style={{ color: '#667085', marginBottom: 0 }}>Current web evidence is combined with your Brand DNA before an idea reaches the drafting engine.</p></div>
              <button type="button" onClick={discoverResearch} disabled={isResearching} style={{ background: '#111827', color: '#fff', border: 0, borderRadius: 8, padding: '10px 14px', fontWeight: 700, cursor: isResearching ? 'wait' : 'pointer' }}><Search size={15}/> {isResearching ? 'Researching…' : 'Research now'}</button>
            </div>
          </div>
          {opportunities.length === 0 ? <div style={{ background: '#fff', border: '1px dashed #d0d5dd', borderRadius: 14, padding: 28, color: '#667085' }}>No researched opportunities yet. Click <b>Research now</b>.</div> :
            opportunities.map((item) => <div key={item.id} style={{ background: '#fff', border: '1px solid #e4e7ec', borderRadius: 14, padding: 22 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', gap: 14, flexWrap: 'wrap' }}>
                <div style={{ flex: 1, minWidth: 260 }}><div style={{ fontSize: 12, color: '#667085', marginBottom: 6 }}>{item.pillar} · {item.format || 'Insight post'}</div><h3 style={{ margin: 0 }}>{item.title}</h3><p style={{ color: '#475467', lineHeight: 1.55 }}>{item.angle}</p></div>
                <div style={{ minWidth: 130, textAlign: 'center', padding: 14, background: '#f8fafc', borderRadius: 12 }}><div style={{ fontSize: 30, fontWeight: 800 }}>{Math.round(item.total_score)}</div><div style={{ color: '#667085', fontSize: 12 }}>Opportunity score</div></div>
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, minmax(0,1fr))', gap: 8, marginTop: 10 }}>
                {Object.entries(item.scores || {}).filter(([k]) => k !== 'risk').slice(0, 7).map(([key, value]) => <div key={key} style={{ padding: 9, background: '#f8fafc', borderRadius: 8 }}><div style={{ fontSize: 11, color: '#667085' }}>{key.replaceAll('_',' ')}</div><b>{Math.round(value)}</b></div>)}
              </div>
              {item.evidence?.summary && <div style={{ marginTop: 16, padding: 14, borderLeft: '3px solid #98a2b3', background: '#f8fafc', lineHeight: 1.55 }}><b>Evidence:</b> {item.evidence.summary}</div>}
              {item.evidence?.why_now && <p style={{ color: '#475467' }}><b>Why now:</b> {item.evidence.why_now}</p>}
              {item.rationale && <p style={{ color: '#667085', fontSize: 13 }}><b>Why it survived:</b> {item.rationale}</p>}
              {item.sources?.length ? <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginTop: 10 }}>{item.sources.slice(0, 5).map((source, idx) => source.url ? <a key={idx} href={source.url} target="_blank" rel="noreferrer" style={{ fontSize: 12, color: '#175cd3', display: 'inline-flex', gap: 5, alignItems: 'center' }}>{source.title || source.domain || 'Source'} <ExternalLink size={12}/></a> : null)}</div> : null}
            </div>)
          }
        </div>}

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
        {tab === 'Settings' && <div style={{ display: 'grid', gap: 18 }}>
          <div style={{ background: '#fff', border: '1px solid #e4e7ec', borderRadius: 14, padding: 28 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', gap: 16, alignItems: 'flex-start', flexWrap: 'wrap' }}>
              <div>
                <h2 style={{ marginTop: 0, marginBottom: 6 }}>Brand Intelligence</h2>
                <p style={{ color: '#667085', marginTop: 0, lineHeight: 1.55 }}>
                  Your Brand DNA is a living memory — not a one-time questionnaire. Brand OS learns from your profile, approved content and posts published through Brand OS.
                </p>
              </div>
              <span style={{ padding: '7px 11px', borderRadius: 999, background: brand.ready ? '#ecfdf3' : '#fff4e5', color: brand.ready ? '#067647' : '#b54708', fontWeight: 700, fontSize: 12 }}>
                {brand.ready ? 'ACTIVE · ' + brand.source_post_count + ' posts learned' : 'SETUP NEEDED'}
              </span>
            </div>

            {brand.ready ? (
              <>
                {brand.summary && <div style={{ marginTop: 14, padding: 14, background: '#f8fafc', borderRadius: 10, color: '#344054', lineHeight: 1.55 }}><b>Current Brand DNA:</b> {brand.summary}</div>}
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, minmax(0, 1fr))', gap: 10, marginTop: 14 }}>
                  <div style={{ padding: 12, border: '1px solid #e4e7ec', borderRadius: 10 }}><div style={{ fontSize: 12, color: '#667085' }}>Content memory</div><b>{brand.current_post_count ?? brand.source_post_count} items</b></div>
                  <div style={{ padding: 12, border: '1px solid #e4e7ec', borderRadius: 10 }}><div style={{ fontSize: 12, color: '#667085' }}>Learning mode</div><b>{brand.continuous_learning ? 'Continuous' : 'Snapshot'}</b></div>
                  <div style={{ padding: 12, border: '1px solid #e4e7ec', borderRadius: 10 }}><div style={{ fontSize: 12, color: '#667085' }}>Last memory update</div><b>{brand.last_updated ? new Date(brand.last_updated).toLocaleString() : 'Just now'}</b></div>
                </div>
              </>
            ) : (
              <div style={{ marginTop: 14, padding: 14, background: '#f8fafc', borderRadius: 10, color: '#475467', lineHeight: 1.55 }}>
                Start with your professional profile. You do <b>not</b> need to paste your old LinkedIn posts.
              </div>
            )}
          </div>

          <div style={{ background: '#fff', border: '1px solid #e4e7ec', borderRadius: 14, padding: 28 }}>
            <h3 style={{ marginTop: 0 }}>1. Your professional profile</h3>
            <p style={{ color: '#667085', fontSize: 13, lineHeight: 1.55 }}>
              These fields establish the factual baseline. Brand OS will not invent missing credentials, experience or achievements.
            </p>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0, 1fr))', gap: 12 }}>
              <input value={brandTitle} onChange={(e) => setBrandTitle(e.target.value)} placeholder="Professional title" style={{ padding: 12, border: '1px solid #d0d5dd', borderRadius: 8 }} />
              <input value={brandIndustry} onChange={(e) => setBrandIndustry(e.target.value)} placeholder="Industry" style={{ padding: 12, border: '1px solid #d0d5dd', borderRadius: 8 }} />
              <input value={brandAudience} onChange={(e) => setBrandAudience(e.target.value)} placeholder="Who you want to reach" style={{ padding: 12, border: '1px solid #d0d5dd', borderRadius: 8 }} />
              <input value={brandGoals} onChange={(e) => setBrandGoals(e.target.value)} placeholder="Goals, comma separated" style={{ padding: 12, border: '1px solid #d0d5dd', borderRadius: 8 }} />
              <input value={brandTone} onChange={(e) => setBrandTone(e.target.value)} placeholder="Desired tone (optional)" style={{ padding: 12, border: '1px solid #d0d5dd', borderRadius: 8 }} />
              <input value={brandPositioning} onChange={(e) => setBrandPositioning(e.target.value)} placeholder="How you want to be known" style={{ padding: 12, border: '1px solid #d0d5dd', borderRadius: 8 }} />
            </div>
            <div style={{ display: 'flex', gap: 10, alignItems: 'center', marginTop: 18, flexWrap: 'wrap' }}>
              <button type="button" onClick={buildBrand} disabled={isBuildingBrand} style={{ background: '#111827', color: '#fff', border: 0, borderRadius: 8, padding: '11px 16px', cursor: isBuildingBrand ? 'wait' : 'pointer', fontWeight: 700 }}>
                {isBuildingBrand ? 'Building Brand Intelligence…' : brand.ready ? 'Refresh Brand Intelligence' : 'Start Brand Intelligence'}
              </button>
              <span style={{ color: '#667085', fontSize: 13 }}>No historical posts required.</span>
            </div>
          </div>

          <div style={{ background: '#fff', border: '1px solid #e4e7ec', borderRadius: 14, padding: 28 }}>
            <details>
              <summary style={{ cursor: 'pointer', fontWeight: 700 }}>Optional: improve initial voice learning with previous posts</summary>
              <p style={{ color: '#667085', fontSize: 13, lineHeight: 1.55, marginBottom: 12 }}>
                This is optional. Paste a few previous posts if you want a stronger initial writing signal. They are stored as private brand evidence. Brand OS does not scrape LinkedIn.
              </p>
              <textarea value={historicalPosts} onChange={(e) => setHistoricalPosts(e.target.value)} placeholder={'Post 1...\n\n---POST---\n\nPost 2...'} style={{ width: '100%', minHeight: 240, padding: 14, border: '1px solid #d0d5dd', borderRadius: 10, boxSizing: 'border-box', fontFamily: 'inherit', lineHeight: 1.5 }} />
              <div style={{ marginTop: 10, color: '#667085', fontSize: 13 }}>
                {historicalPosts.split(/\n---POST---\n|\n---POST---\r?\n/).filter((x) => x.trim()).length} posts ready to import
              </div>
            </details>
          </div>

          <div style={{ background: '#fff', border: '1px solid #e4e7ec', borderRadius: 14, padding: 28 }}>
            <h3 style={{ marginTop: 0 }}>How the memory evolves</h3>
            <div style={{ color: '#475467', lineHeight: 1.65, fontSize: 14 }}>
              <b>Profile</b> → identity and positioning · <b>Approved/edited content</b> → voice signals · <b>Brand OS published posts</b> → durable content memory · <b>Research</b> → current opportunities.
            </div>
            <p style={{ color: '#667085', fontSize: 13, marginBottom: 0 }}>
              When new Brand OS posts are published, they are added to the memory store automatically. The next generation refreshes the derived Brand DNA when new content is detected. Historical LinkedIn posts remain optional because LinkedIn restricts broad personal-post retrieval to approved permissions.
            </p>
          </div>

          <div style={{ background: '#fff', border: '1px solid #e4e7ec', borderRadius: 14, padding: 28 }}>
            <h3 style={{ marginTop: 0 }}>LinkedIn connection</h3>
            <p style={{ color: '#667085' }}>Signed in as <b>{profile.display_name}</b>. {linkedin.connected ? 'Official LinkedIn posting is connected.' : 'Connect LinkedIn to enable official API actions.'}</p>
            <button type="button" onClick={connectLinkedIn} style={{ padding: '9px 12px', borderRadius: 8, border: '1px solid #d0d5dd', background: '#fff', cursor: 'pointer' }}>{linkedin.connected ? 'Reconnect LinkedIn' : 'Connect LinkedIn'}</button>
          </div>
        </div>}
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
