'use client';

import { useEffect, useMemo, useState } from 'react';
import {
  Activity, ArrowUpRight, BarChart3, BrainCircuit, Check, ChevronRight, CircleCheck,
  Clock3, Command, ExternalLink, FileText, Gauge, Globe2, LayoutDashboard, Link2,
  LogOut, Menu, MessageSquare, Pencil, Plus, RefreshCw, RotateCcw, Search, Settings,
  ShieldCheck, Sparkles, Target, TrendingUp, UserRound, WandSparkles, X, Zap
} from 'lucide-react';

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
const STORAGE_KEY = 'brand-os-token';

function getApiError(data: any, fallback: string) {
  if (typeof data?.detail === 'string') return data.detail;
  if (Array.isArray(data?.detail)) return data.detail.map((item: any) => item?.msg || String(item)).join('; ');
  if (typeof data?.message === 'string') return data.message;
  return fallback;
}

type ApprovalStatus = 'PENDING' | 'EDITED' | 'REGENERATED' | 'APPROVED' | 'REJECTED' | 'EXECUTED';
type ApprovalItem = { id: number; status: ApprovalStatus; action_type: string; reason: string | null; content: string };
type Profile = { display_name: string; role?: string };
type LinkedInStatus = { connected: boolean; name?: string | null; email?: string | null; expires_at?: string | null };
type BrandStatus = {
  ready: boolean; status: string; source_post_count: number; current_post_count?: number;
  continuous_learning?: boolean; historical_import_optional?: boolean; last_updated?: string | null;
  summary?: string | null;
  profile?: { display_name?: string; professional_title?: string | null; industry?: string | null; audience?: string | null; brand_positioning?: string | null; tone?: string | null };
};
type Opportunity = {
  id: number; title: string; topic: string; angle: string; pillar: string; format?: string; objective?: string;
  total_score: number; scores: Record<string, number>; rationale?: string;
  evidence?: { summary?: string; why_now?: string; source_hints?: string[]; grounding_queries?: string[] };
  source_ids?: number[]; sources?: { title?: string; url?: string; domain?: string }[];
};
type Tab = 'Dashboard' | 'Research' | 'Content' | 'Analytics' | 'Settings';

const nav = [
  ['Dashboard', LayoutDashboard, 'Command center'],
  ['Research', Search, 'Find opportunities'],
  ['Content', FileText, 'Draft & refine'],
  ['Analytics', BarChart3, 'Performance'],
  ['Settings', Settings, 'Brand DNA'],
] as const;

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
  const [historicalPostEntries, setHistoricalPostEntries] = useState<string[]>(['']);
  const [brandEditing, setBrandEditing] = useState(false);
  const [analytics, setAnalytics] = useState<any>(null);
  const [draftLanguage, setDraftLanguage] = useState('');
  const [isImproving, setIsImproving] = useState(false);
  const [improvementNotes, setImprovementNotes] = useState<string[]>([]);
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
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [loading, setLoading] = useState(false);

  const headers = (authToken = token) => authToken ? { Authorization: `Bearer ${authToken}` } : {};

  useEffect(() => {
    if (!notice) return;
    const timer = window.setTimeout(() => setNotice(null), 4500);
    return () => window.clearTimeout(timer);
  }, [notice]);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const code = params.get('linkedin_code');
    const savedToken = window.localStorage.getItem(STORAGE_KEY);
    if (code) {
      window.history.replaceState({}, document.title, window.location.pathname);
      fetch(`${API_BASE}/api/auth/linkedin/exchange`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ code }),
      }).then(async (res) => {
        const data = await res.json();
        if (!res.ok) throw new Error(getApiError(data, 'LinkedIn connection failed'));
        window.localStorage.setItem(STORAGE_KEY, data.token);
        setToken(data.token);
        setNotice('LinkedIn account connected successfully.');
      }).catch((e) => setError(e instanceof Error ? e.message : 'LinkedIn connection failed'));
      return;
    }
    if (savedToken) setToken(savedToken);
  }, []);

  const fetchData = async (authToken: string | null = token) => {
    if (!authToken) return;
    setLoading(true);
    try {
      const [profileRes, approvalsRes, linkedinRes, brandRes, opportunityRes, sourceRes, analyticsRes] = await Promise.all([
        fetch(`${API_BASE}/api/auth/me`, { headers: headers(authToken) }),
        fetch(`${API_BASE}/api/dashboard/approvals`, { headers: headers(authToken) }),
        fetch(`${API_BASE}/api/linkedin/status`, { headers: headers(authToken) }),
        fetch(`${API_BASE}/api/brand/status`, { headers: headers(authToken) }),
        fetch(`${API_BASE}/api/research/opportunities`, { headers: headers(authToken) }),
        fetch(`${API_BASE}/api/brand/source-posts`, { headers: headers(authToken) }),
        fetch(`${API_BASE}/api/analytics/overview`, { headers: headers(authToken) }),
      ]);
      if (profileRes.status === 401 || approvalsRes.status === 401) {
        window.localStorage.removeItem(STORAGE_KEY);
        setToken(null); setQueue([]); setLinkedin({ connected: false });
        throw new Error('Your session expired. Please sign in with LinkedIn again.');
      }
      if (!profileRes.ok || !approvalsRes.ok) throw new Error('Unable to load dashboard data.');
      const profileJson = await profileRes.json();
      const approvalsJson = await approvalsRes.json();
      setProfile({ display_name: profileJson.display_name || 'User', role: profileJson.role || 'owner' });
      setLinkedin(linkedinRes.ok ? await linkedinRes.json() : { connected: false });
      const brandJson = brandRes.ok ? await brandRes.json() : { ready: false, status: 'NOT_INITIALIZED', source_post_count: 0 };
      setBrand(brandJson);
      const p = brandJson.profile || {};
      setBrandTitle(p.professional_title || ''); setBrandIndustry(p.industry || '');
      setBrandAudience(p.audience || ''); setBrandPositioning(p.brand_positioning || ''); setBrandTone(p.tone || '');
      setBrandGoals(Array.isArray(p.goals) ? p.goals.join(', ') : (p.goals || ''));
      const sourceJson = sourceRes.ok ? await sourceRes.json() : { posts: [] };
      const sourcePosts = (sourceJson.posts || []).map((item: any) => item.body).filter((body: any) => typeof body === 'string' && body.trim());
      if (sourcePosts.length) setHistoricalPostEntries(sourcePosts.slice(0, 5));
      const analyticsJson = analyticsRes.ok ? await analyticsRes.json() : null;
      setAnalytics(analyticsJson);
      const opportunityJson = opportunityRes.ok ? await opportunityRes.json() : { opportunities: [] };
      setOpportunities(opportunityJson.opportunities || []);
      const nextQueue: ApprovalItem[] = (approvalsJson.pending_approvals || []).map((item: any) => ({
        id: item.id, status: item.status, action_type: item.action_type, reason: item.reason, content: item.content || '',
      }));
      setQueue(nextQueue);
      if (nextQueue.length && !nextQueue.some((i) => i.id === selectedId)) setSelectedId(nextQueue[0].id);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Unable to load dashboard data');
    } finally { setLoading(false); }
  };

  useEffect(() => { fetchData(token); }, [token]);
  useEffect(() => {
    const selected = queue.find((item) => item.id === selectedId);
    if (selected) { setEditedBody(selected.content || ''); setReviewNote(selected.reason || ''); }
  }, [selectedId, queue]);

  const filteredQueue = useMemo(() => {
    const query = searchTerm.trim().toLowerCase();
    return queue.filter((item) => {
      const statusMatch = statusFilter === 'all' || item.status === statusFilter;
      const haystack = `${item.action_type} ${item.content} ${item.reason || ''}`.toLowerCase();
      return statusMatch && (!query || haystack.includes(query));
    });
  }, [queue, searchTerm, statusFilter]);

  const selectedApproval = queue.find((item) => item.id === selectedId) ?? null;
  const summary = useMemo(() => ({
    pending: queue.filter((i) => ['PENDING', 'EDITED', 'REGENERATED'].includes(i.status)).length,
    reviewed: queue.filter((i) => i.status === 'APPROVED').length,
    rejected: queue.filter((i) => i.status === 'REJECTED').length,
    executed: queue.filter((i) => i.status === 'EXECUTED').length,
  }), [queue]);

  const initials = (profile.display_name || 'User').split(' ').map((x) => x[0]).slice(0, 2).join('').toUpperCase();
  const closeSidebar = () => setSidebarOpen(false);
  const connectLinkedIn = () => { window.location.href = '/api/auth/linkedin/start'; };
  const cancelBrandEdit = async () => { await fetchData(); setBrandEditing(false); };
  const cancelBrandEdit = async () => { await fetchData(); setBrandEditing(false); };
  const logout = () => {
    window.localStorage.removeItem(STORAGE_KEY);
    setToken(null); setQueue([]); setLinkedin({ connected: false }); closeSidebar();
  };
  const go = (next: Tab) => { setTab(next); closeSidebar(); window.scrollTo({ top: 0, behavior: 'smooth' }); };

  const runApprovalAction = async (action: 'approve' | 'edit' | 'reject' | 'regenerate', payload?: Record<string, string>) => {
    if (!selectedApproval || !token) return;
    setIsBusy(true); setError(null); setNotice(null);
    try {
      const res = await fetch(`${API_BASE}/api/approvals/${selectedApproval.id}/${action}`, {
        method: 'POST', headers: { ...headers(), 'Content-Type': 'application/json' }, body: JSON.stringify(payload || {}),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(getApiError(data, `Action failed: ${action}`));
      await fetchData(); setReviewNote('');
      setNotice(`${action.charAt(0).toUpperCase() + action.slice(1)} completed.`);
    } catch (e) { setError(e instanceof Error ? e.message : 'Approval action failed'); }
    finally { setIsBusy(false); }
  };

  const generateContent = async () => {
    if (!token) return;
    if (!brand.ready) { go('Settings'); setError('Complete Brand Intelligence setup first.'); return; }
    setIsGenerating(true); setError(null); setNotice(null);
    try {
      const res = await fetch(API_BASE + '/api/agent/events', {
        method: 'POST', headers: { ...headers(), 'Content-Type': 'application/json' },
        body: JSON.stringify({ event_type: 'manual_generate_content', payload: { objective: 'Generate a fresh LinkedIn content opportunity for human review.' } }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(getApiError(data, 'Content generation failed'));
      await fetchData(); go('Dashboard');
      setNotice(data.created_count ? 'New content suggestion generated and added to the approval queue.' : 'No new suggestion was created. The agent may have detected a duplicate.');
    } catch (e) { setError(e instanceof Error ? e.message : 'Content generation failed'); }
    finally { setIsGenerating(false); }
  };

  const discoverResearch = async () => {
    if (!token) return;
    if (!brand.ready) { go('Settings'); setError('Complete Brand Intelligence setup before running live research.'); return; }
    setIsResearching(true); setError(null); setNotice(null);
    try {
      const res = await fetch(API_BASE + '/api/research/discover', {
        method: 'POST', headers: { ...headers(), 'Content-Type': 'application/json' }, body: JSON.stringify({}),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(getApiError(data, 'Live research failed'));
      setOpportunities(data.opportunities || []);
      setNotice('Fresh research completed. Opportunities were ranked against your Brand DNA.');
    } catch (e) { setError(e instanceof Error ? e.message : 'Live research failed'); }
    finally { setIsResearching(false); }
  };

  const updateHistoricalPost = (index: number, value: string) =>
    setHistoricalPostEntries((current) => current.map((post, i) => i === index ? value : post));
  const addHistoricalPost = () =>
    setHistoricalPostEntries((current) => current.length >= 5 ? current : [...current, '']);
  const removeHistoricalPost = (index: number) =>
    setHistoricalPostEntries((current) => current.length <= 1 ? current : current.filter((_, i) => i !== index));

  const buildBrand = async () => {
    if (!token) return;
    const blocks = historicalPostEntries.map((body) => body.trim()).filter(Boolean);
    if (blocks.length < 3) { setError('Please add at least 3 previous LinkedIn posts before building Brand Intelligence.'); return; }
    setIsBuildingBrand(true); setError(null); setNotice(null);
    try {
      const res = await fetch(API_BASE + '/api/brand/onboard', {
        method: 'POST', headers: { ...headers(), 'Content-Type': 'application/json' },
        body: JSON.stringify({
          display_name: profile.display_name, professional_title: brandTitle || null, industry: brandIndustry || null,
          audience: brandAudience || null, goals: brandGoals.split(',').map((x) => x.trim()).filter(Boolean),
          brand_positioning: brandPositioning || null, tone: brandTone || null, posts: blocks.map((body) => ({ body })),
        }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(getApiError(data, 'Brand Intelligence setup failed'));
      setBrand({ ...data.brand_memory, ready: data.brand_memory?.status === 'READY' });
      setNotice(`Brand Intelligence updated using your profile plus ${blocks.length} imported posts.`);
      await fetchData();
    } catch (e) { setError(e instanceof Error ? e.message : 'Brand Intelligence setup failed'); }
    finally { setIsBuildingBrand(false); }
  };

  const improveDraft = async () => {
    if (!token || !draftBody.trim()) { setError('Write a draft first, then ask Brand OS to polish it.'); return; }
    setIsImproving(true); setError(null); setNotice(null);
    try {
      const res = await fetch(API_BASE + '/api/content/improve', {
        method: 'POST',
        headers: { ...headers(), 'Content-Type': 'application/json' },
        body: JSON.stringify({ title: draftTitle, topic: draftTopic, body: draftBody, language: draftLanguage || null }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(getApiError(data, 'Content improvement failed'));
      setDraftTitle(data.title || draftTitle);
      setDraftTopic(data.topic || draftTopic);
      setDraftBody(data.body || draftBody);
      setImprovementNotes(data.changes || []);
      setNotice('Polished version ready for your preview. Nothing has been sent for approval yet.');
    } catch (e) { setError(e instanceof Error ? e.message : 'Content improvement failed'); }
    finally { setIsImproving(false); }
  };

  const createDraft = async () => {
    if (!token || !draftTitle.trim() || !draftTopic.trim() || !draftBody.trim()) {
      setError('Title, topic and draft body are required.'); return;
    }
    setIsBusy(true); setError(null); setNotice(null);
    try {
      const res = await fetch(`${API_BASE}/api/content/drafts`, {
        method: 'POST', headers: { ...headers(), 'Content-Type': 'application/json' },
        body: JSON.stringify({ title: draftTitle, topic: draftTopic, pillar: 'Expertise', body: draftBody }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(getApiError(data, 'Draft creation failed'));
      setDraftTitle(''); setDraftTopic(''); setDraftBody('');
      await fetchData(); go('Dashboard');
      setNotice(data.approval_id ? 'Draft created and added to the HITL approval queue.' : 'Draft created but guardrails require edits.');
    } catch (e) { setError(e instanceof Error ? e.message : 'Draft creation failed'); }
    finally { setIsBusy(false); }
  };

  if (!token) return <LoginScreen error={error} onConnect={connectLinkedIn} />;

  return (
    <div className="app-shell">
      {sidebarOpen && <div className="mobile-overlay" onClick={closeSidebar} />}
      <aside className={`sidebar ${sidebarOpen ? 'open' : ''}`}>
        <div className="brand-lockup">
          <div className="brand-mark"><Sparkles size={18} /></div>
          <div><div className="brand-name">Brand OS</div><div className="brand-sub">Personal Brand Manager</div></div>
        </div>
        <div className="nav-label">Workspace</div>
        {nav.map(([label, Icon, sub]) => (
          <button key={label} className={`nav-item ${tab === label ? 'active' : ''}`} onClick={() => go(label as Tab)}>
            <Icon size={16} /><span>{label}</span>{label === 'Dashboard' && summary.pending > 0 ? <em>{summary.pending}</em> : <ChevronRight size={13} opacity={.35} />}
          </button>
        ))}
        <div className="sidebar-spacer" />
        <div className="connection-card">
          <div className="connection-row">
            <span className={`connection-dot ${linkedin.connected ? 'live' : ''}`} />
            <span className="connection-title">{linkedin.connected ? 'LinkedIn connected' : 'LinkedIn not connected'}</span>
          </div>
          <div className="connection-meta">{linkedin.connected ? 'Official API connection is ready.' : 'Connect through official OAuth to enable publishing.'}</div>
          <button className="button ghost-dark" style={{ width: '100%', marginTop: 9 }} onClick={connectLinkedIn}>
            <Link2 size={13} /> {linkedin.connected ? 'Reconnect' : 'Connect'}
          </button>
        </div>
        <div className="connection-card">
          <div className="connection-row"><ShieldCheck size={15} color="#8b7cff" /><span className="connection-title">Human approval gate</span></div>
          <div className="connection-meta">No external LinkedIn action is executed without your explicit approval.</div>
        </div>
        <button className="side-button" onClick={logout}><LogOut size={14} /> Sign out <span style={{ marginLeft: 'auto' }}>⌘Q</span></button>
      </aside>

      <div className="main-shell">
        <header className="topbar">
          <div className="topbar-left">
            <button className="icon-button mobile-menu" onClick={() => setSidebarOpen(true)}><Menu size={18} /></button>
            <div><div className="eyebrow">Workspace / {tab}</div><div className="topbar-title">{tab === 'Dashboard' ? 'Command center' : nav.find((x) => x[0] === tab)?.[2]}</div></div>
          </div>
          <div className="topbar-actions">
            <button className="icon-button" title="Refresh workspace" onClick={() => fetchData()}><RefreshCw size={15} className={loading ? 'spin' : ''} /></button>
            <div className="avatar">{initials}</div>
          </div>
        </header>

        <main className="page">
          {notice && <div className="notice success"><CircleCheck size={15} /><span>{notice}</span></div>}
          {error && <div className="notice error"><X size={15} /><span>{error}</span></div>}

          {tab === 'Dashboard' && (
            <>
              <section className="hero">
                <div className="hero-grid">
                  <div>
                    <div className="page-kicker" style={{ color: '#bdb6ff' }}><Sparkles size={13} /> Brand intelligence active</div>
                    <h1>Turn your expertise into a recognizable point of view.</h1>
                    <p>Research, content strategy, drafting and review — orchestrated around your brand voice, with you always in control of what reaches LinkedIn.</p>
                    <div className="hero-actions">
                      <button className="button primary" onClick={generateContent} disabled={isGenerating}><WandSparkles size={15} /> {isGenerating ? 'Generating…' : 'Generate content'}</button>
                      <button className="button ghost-dark" onClick={() => go('Research')}><Search size={15} /> Discover opportunities</button>
                    </div>
                  </div>
                  <div className="hero-status">
                    <div className="status-orb"><div className="orb-inner"><BrainCircuit size={30} /></div></div>
                    <div style={{ color: '#8f9ab1', fontSize: 10, textAlign: 'right' }}>AI prepared · human approved<br />No autonomous publishing</div>
                  </div>
                </div>
              </section>

              <div className="metrics">
                <Metric icon={Clock3} label="Awaiting approval" value={summary.pending} meta="Needs your decision" />
                <Metric icon={CircleCheck} label="Approved" value={summary.reviewed} meta="Ready for execution" />
                <Metric icon={TrendingUp} label="Published" value={summary.executed} meta="Tracked by Brand OS" />
                <Metric icon={ShieldCheck} label="Guardrail status" value="ON" meta="Claims · voice · duplicate · action" />
              </div>

              <div className="section-grid">
                <section className="panel">
                  <div className="panel-head">
                    <div><div className="panel-title">Approval queue</div><div className="panel-subtitle">Your editorial desk — review the exact content before anything external happens.</div></div>
                    <button className="button" onClick={() => go('Content')}><Plus size={14} /> New draft</button>
                  </div>
                  <ApprovalWorkspace
                    queue={filteredQueue} selected={selectedApproval} selectedId={selectedId}
                    setSelectedId={setSelectedId} searchTerm={searchTerm} setSearchTerm={setSearchTerm}
                    statusFilter={statusFilter} setStatusFilter={setStatusFilter}
                    editedBody={editedBody} setEditedBody={setEditedBody}
                    reviewNote={reviewNote} setReviewNote={setReviewNote}
                    isBusy={isBusy} onAction={runApprovalAction}
                  />
                </section>

                <section className="panel">
                  <div className="panel-head">
                    <div><div className="panel-title">Brand pulse</div><div className="panel-subtitle">What the system currently knows about your positioning.</div></div>
                    <button className="icon-button" onClick={() => go('Settings')}><ArrowUpRight size={14} /></button>
                  </div>
                  <div className="panel-body">
                    {brand.ready ? (
                      <>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 12, padding: 13, borderRadius: 13, background: '#f8f7ff', border: '1px solid #ebe8ff' }}>
                          <div className="metric-icon"><BrainCircuit size={16} /></div>
                          <div><div style={{ fontSize: 12, fontWeight: 800 }}>Brand DNA active</div><div style={{ color: '#667085', fontSize: 10, marginTop: 2 }}>{brand.current_post_count ?? brand.source_post_count} content signals in memory</div></div>
                        </div>
                        <div style={{ marginTop: 14, color: '#475467', fontSize: 12, lineHeight: 1.6 }}>{brand.summary || 'Your brand memory is ready to shape new content.'}</div>
                        <div className="score-grid" style={{ marginTop: 14 }}>
                          <MiniStat icon={Target} label="Audience" value={brand.profile?.audience || 'Defined in profile'} />
                          <MiniStat icon={Gauge} label="Tone" value={brand.profile?.tone || 'Learned from content'} />
                          <MiniStat icon={Globe2} label="Industry" value={brand.profile?.industry || 'Defined in profile'} />
                          <MiniStat icon={Activity} label="Learning" value={brand.continuous_learning ? 'Continuous' : 'Snapshot'} />
                        </div>
                      </>
                    ) : (
                      <EmptyState icon={BrainCircuit} title="Brand DNA needs a starting signal" text="Add your professional profile and at least three previous posts in Settings." action="Set up Brand Intelligence" onAction={() => go('Settings')} />
                    )}
                  </div>
                </section>
              </div>
            </>
          )}

          {tab === 'Research' && <ResearchView opportunities={opportunities} isResearching={isResearching} onResearch={discoverResearch} />}
          {tab === 'Content' && <ContentStudio profile={profile} title={draftTitle} setTitle={setDraftTitle} topic={draftTopic} setTopic={setDraftTopic} body={draftBody} setBody={setDraftBody} language={draftLanguage} setLanguage={setDraftLanguage} busy={isBusy} improving={isImproving} improvementNotes={improvementNotes} onImprove={improveDraft} onSubmit={createDraft} />}
          {tab === 'Analytics' && <AnalyticsView analytics={analytics} />}
          {tab === 'Settings' && (
            <SettingsView
              brand={brand} profile={profile} brandTitle={brandTitle} setBrandTitle={setBrandTitle}
              brandIndustry={brandIndustry} setBrandIndustry={setBrandIndustry} brandAudience={brandAudience} setBrandAudience={setBrandAudience}
              brandPositioning={brandPositioning} setBrandPositioning={setBrandPositioning} brandTone={brandTone} setBrandTone={setBrandTone}
              brandGoals={brandGoals} setBrandGoals={setBrandGoals} posts={historicalPostEntries}
              updatePost={updateHistoricalPost} addPost={addHistoricalPost} removePost={removeHistoricalPost}
              building={isBuildingBrand} onBuild={buildBrand} linkedin={linkedin} onConnect={connectLinkedIn} editing={brandEditing} setEditing={setBrandEditing} onCancel={cancelBrandEdit}
            />
          )}
        </main>
      </div>
    </div>
  );
}

function LoginScreen({ error, onConnect }: { error: string | null; onConnect: () => void }) {
  return (
    <main style={{ minHeight: '100vh', display: 'grid', placeItems: 'center', padding: 22, background: 'radial-gradient(circle at 20% 10%, #e9e5ff, transparent 28%), radial-gradient(circle at 90% 80%, #dff9fb, transparent 30%), #f6f7fb' }}>
      <div className="login-shell">
        <div className="login-visual">
          <div className="brand-lockup" style={{ padding: 0 }}><div className="brand-mark"><Sparkles size={18}/></div><div><div className="brand-name">Brand OS</div><div className="brand-sub" style={{ color: '#7f8aa3' }}>Personal Brand Manager</div></div></div>
          <div style={{ position: 'relative', zIndex: 1, marginTop: 74 }}>
            <div className="page-kicker" style={{ color: '#bdb6ff' }}><Sparkles size={13}/> AI + human editorial control</div>
            <h1 style={{ fontFamily: 'Space Grotesk', fontSize: 47, lineHeight: 1.02, letterSpacing: '-.055em', margin: '12px 0 16px' }}>Your brand,<br/>with a brain.</h1>
            <p style={{ color: '#aeb7ca', maxWidth: 430, lineHeight: 1.65, fontSize: 13 }}>A professional operating system for discovering ideas, shaping your voice and preparing content — without giving an AI free rein over your identity.</p>
            <div style={{ display: 'grid', gap: 9, marginTop: 28 }}>
              {['Learns from approved content', 'Researches before drafting', 'Human approval before external actions'].map((x) => <div key={x} style={{ display: 'flex', gap: 9, alignItems: 'center', color: '#dce1ec', fontSize: 11 }}><CircleCheck size={15} color="#8b7cff"/>{x}</div>)}
            </div>
          </div>
        </div>
        <div className="login-form">
          <div className="page-kicker"><ShieldCheck size={13}/> Secure official connection</div>
          <h2 style={{ fontFamily: 'Space Grotesk', fontSize: 29, letterSpacing: '-.04em', margin: '10px 0 8px' }}>Connect LinkedIn</h2>
          <p style={{ color: '#667085', fontSize: 13, lineHeight: 1.6, margin: 0 }}>Brand OS uses LinkedIn's official OAuth flow. Your LinkedIn password is never entered into Brand OS.</p>
          {error && <div className="notice error" style={{ marginTop: 16 }}><X size={15}/><span>{error}</span></div>}
          <button className="button primary" style={{ width: '100%', minHeight: 46, marginTop: 24 }} onClick={onConnect}><LinkedInMark size={18}/> Continue with LinkedIn</button>
          <div style={{ marginTop: 17, padding: 12, borderRadius: 12, background: '#f8f9fb', color: '#667085', fontSize: 10, lineHeight: 1.55 }}>OAuth permissions requested are limited to supported identity and posting capabilities. External actions remain behind the approval gate.</div>
        </div>
      </div>
    </main>
  );
}

function Metric({ icon: Icon, label, value, meta }: any) {
  return <div className="metric-card"><div className="metric-top"><span>{label}</span><span className="metric-icon"><Icon size={15}/></span></div><div className="metric-value">{value}</div><div className="metric-meta">{meta}</div></div>;
}

function MiniStat({ icon: Icon, label, value }: any) {
  return <div className="score-item"><div className="score-name" style={{ display: 'flex', gap: 5, alignItems: 'center' }}><Icon size={11}/>{label}</div><div className="score-value" style={{ fontSize: 11, lineHeight: 1.35 }}>{value}</div></div>;
}

function ApprovalWorkspace(props: any) {
  const { queue, selected, selectedId, setSelectedId, searchTerm, setSearchTerm, statusFilter, setStatusFilter, editedBody, setEditedBody, reviewNote, setReviewNote, isBusy, onAction } = props;
  return (
    <div className="queue-layout">
      <div className="queue-list">
        <div className="queue-tools">
          <div className="searchbox"><Search size={13}/><input className="input" placeholder="Search drafts…" value={searchTerm} onChange={(e) => setSearchTerm(e.target.value)} /></div>
          <div className="filter-row">
            {(['all','PENDING','EDITED','REGENERATED'] as const).map((x) => <button key={x} className={`filter-chip ${statusFilter === x ? 'active' : ''}`} onClick={() => setStatusFilter(x)}>{x === 'all' ? 'All' : x[0] + x.slice(1).toLowerCase()}</button>)}
          </div>
        </div>
        <div className="queue-items">
          {queue.length ? queue.map((item: ApprovalItem) => (
            <button key={item.id} className={`queue-item ${selectedId === item.id ? 'selected' : ''}`} onClick={() => setSelectedId(item.id)}>
              <div className="queue-item-top"><span className="queue-id">POST #{item.id}</span><StatusPill status={item.status}/></div>
              <div className="queue-action">{item.action_type}</div>
              <div className="queue-preview">{item.content.slice(0, 88)}{item.content.length > 88 ? '…' : ''}</div>
            </button>
          )) : <div className="empty-state"><div className="empty-icon"><FileText size={18}/></div><strong>Queue is clear</strong><span>Create a draft or generate content to start the review flow.</span></div>}
        </div>
      </div>
      <div className="review-pane">
        {selected ? (
          <>
            <div className="review-head"><div><div className="review-label">Editorial review · post #{selected.id}</div><div className="review-title">{selected.action_type}</div></div><StatusPill status={selected.status}/></div>
            <div className="review-editor">
              <div className="editor-toolbar"><span>Exact content bound to approval</span><span>{editedBody.length} chars</span></div>
              <textarea className="textarea" value={editedBody} onChange={(e) => setEditedBody(e.target.value)} />
              <textarea className="textarea" style={{ minHeight: 65, marginTop: 8 }} value={reviewNote} onChange={(e) => setReviewNote(e.target.value)} placeholder="Add an editorial note (optional)…" />
              <div className="review-actions">
                <button className="button success" disabled={isBusy} onClick={() => onAction('approve')}><Check size={14}/> Approve</button>
                <button className="button" disabled={isBusy} onClick={() => onAction('edit', { edited_body: editedBody, reason: reviewNote || 'Edited during review.' })}><Pencil size={14}/> Save edit</button>
                <button className="button" disabled={isBusy} onClick={() => onAction('regenerate', { reason: reviewNote || 'Regenerated after review.' })}><RotateCcw size={14}/> Regenerate</button>
                <button className="button danger" disabled={isBusy} onClick={() => onAction('reject', { reason: reviewNote || 'Rejected by reviewer.' })}><X size={14}/> Reject</button>
              </div>
            </div>
            <div style={{ marginTop: 17 }}>
              <div className="review-label" style={{ marginBottom: 9 }}>Safety rail</div>
              <div style={{ display: 'flex', gap: 7, flexWrap: 'wrap' }}>
                {['Claim guard','Voice guard','Duplicate guard','Action guard'].map((x) => <span key={x} className="tag"><ShieldCheck size={10}/>{x}</span>)}
              </div>
            </div>
          </>
        ) : <EmptyState icon={FileText} title="Select a draft" text="Your editorial workspace will appear here." />}
      </div>
    </div>
  );
}

function StatusPill({ status }: { status: string }) {
  const cls = status.toLowerCase();
  return <span className={`status-pill ${cls}`}><span>●</span>{status}</span>;
}

function ResearchView({ opportunities, isResearching, onResearch }: { opportunities: Opportunity[]; isResearching: boolean; onResearch: () => void }) {
  return (
    <>
      <div className="page-header">
        <div><div className="page-kicker"><Search size={13}/> Intelligence layer</div><h1 className="page-title">Research & opportunities</h1><p className="page-description">Live evidence is combined with your Brand DNA before an idea reaches the drafting engine.</p></div>
        <button className="button primary" onClick={onResearch} disabled={isResearching}><Search size={14}/>{isResearching ? 'Researching…' : 'Research now'}</button>
      </div>
      <div className="research-grid">
        {opportunities.length ? opportunities.map((item) => <ResearchCard key={item.id} item={item}/>) :
          <section className="panel"><EmptyState icon={Search} title="No opportunities yet" text="Run live research to surface current topics, evidence and brand-fit angles." action="Run research" onAction={onResearch}/></section>}
      </div>
    </>
  );
}

function ResearchCard({ item }: { item: Opportunity }) {
  const scores = Object.entries(item.scores || {}).filter(([key]) => key !== 'risk').slice(0, 7);
  return (
    <article className="research-card">
      <div className="research-top">
        <div style={{ minWidth: 0 }}>
          <div className="tag-row"><span className="tag">{item.pillar}</span><span className="tag">{item.format || 'Insight post'}</span><span className="tag"><Target size={10}/>{item.objective || 'Brand growth'}</span></div>
          <div className="research-title">{item.title}</div>
          <p className="research-angle">{item.angle}</p>
        </div>
        <div className="opportunity-score"><strong>{Math.round(item.total_score)}</strong><span>opportunity</span></div>
      </div>
      <div className="score-grid" style={{ marginTop: 14 }}>
        {scores.map(([key, value]) => <div className="score-item" key={key}><div className="score-name">{key.replaceAll('_',' ')}</div><div className="score-value">{Math.round(value)}</div><div className="score-bar"><span style={{ width: `${Math.min(100, Math.max(0, Number(value)))}%` }}/></div></div>)}
      </div>
      {item.evidence?.summary && <div className="evidence-box"><b>Evidence:</b> {item.evidence.summary}</div>}
      {item.evidence?.why_now && <p style={{ color: '#475467', fontSize: 11, lineHeight: 1.55, margin: '12px 0 0' }}><b>Why now:</b> {item.evidence.why_now}</p>}
      {item.rationale && <p style={{ color: '#667085', fontSize: 10, lineHeight: 1.5, margin: '8px 0 0' }}><b>Selection logic:</b> {item.rationale}</p>}
      {item.sources?.length ? <div className="source-row">{item.sources.slice(0,5).map((source, i) => source.url ? <a className="source-link" key={i} href={source.url} target="_blank" rel="noreferrer">{source.title || source.domain || 'Source'} <ExternalLink size={10}/></a> : null)}</div> : null}
    </article>
  );
}

function ContentStudio({ profile, title, setTitle, topic, setTopic, body, setBody, language, setLanguage, busy, improving, improvementNotes, onImprove, onSubmit }: any) {
  return (
    <>
      <div className="page-header">
        <div>
          <div className="page-kicker"><WandSparkles size={13}/> Editorial studio</div>
          <h1 className="page-title">Write it your way. Let Brand OS polish it.</h1>
          <p className="page-description">Start with your own idea and wording in any language. Brand OS can improve structure and clarity using your Brand DNA, then you preview the exact version before it enters the approval queue.</p>
        </div>
      </div>
      <section className="panel studio-grid">
        <div className="studio-form">
          <div className="form-group"><label className="form-label">Post heading / working title</label><input className="input" value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Write the idea or heading you have in mind" /></div>
          <div className="form-group"><label className="form-label">Topic / theme <span className="form-help">(optional)</span></label><input className="input" value={topic} onChange={(e) => setTopic(e.target.value)} placeholder="What is this post about?" /></div>
          <div className="form-group"><label className="form-label">Your language</label><input className="input" value={language} onChange={(e) => setLanguage(e.target.value)} placeholder="e.g. English, Hindi, Hinglish" /></div>
          <div className="form-group">
            <label className="form-label">Your draft</label>
            <textarea className="textarea" style={{ minHeight: 270 }} value={body} onChange={(e) => setBody(e.target.value)} placeholder="Write naturally. Do not worry about formatting — Brand OS will preserve your meaning and improve the presentation." />
          </div>
          <div style={{ display: 'flex', gap: 9, alignItems: 'center', flexWrap: 'wrap' }}>
            <button className="button primary" disabled={improving || !body.trim()} onClick={onImprove}><WandSparkles size={14}/>{improving ? 'Polishing…' : 'Improvise / polish with Brand OS'}</button>
            <button className="button dark" disabled={busy || !body.trim()} onClick={onSubmit}><ShieldCheck size={14}/>{busy ? 'Sending…' : 'Send this version to approval'}</button>
          </div>
          {improvementNotes?.length ? <div style={{ marginTop: 12, padding: 11, borderRadius: 11, background: '#f8f7ff', color: '#667085', fontSize: 10, lineHeight: 1.5 }}><b style={{ color: '#5145cd' }}>What changed:</b> {improvementNotes.join(' · ')}</div> : null}
        </div>
        <div className="live-preview">
          <div className="panel-title" style={{ marginBottom: 4 }}>Preview before approval</div>
          <div className="panel-subtitle" style={{ marginBottom: 14 }}>This is the exact text you can send to the HITL queue. Nothing is published from this screen.</div>
          <div className="linkedin-card">
            <div className="li-head"><div className="li-avatar">{(profile.display_name || 'U').slice(0,1).toUpperCase()}</div><div><div className="li-name">{profile.display_name}</div><div className="li-meta">Professional profile · Draft</div></div></div>
            <div className="li-body">{body || 'Your polished post preview will appear here.'}</div>
            <div className="li-actions"><span>Like</span><span>Comment</span><span>Share</span></div>
          </div>
          <div style={{ marginTop: 12, padding: 11, borderRadius: 11, background: '#f8f7ff', color: '#667085', fontSize: 10, lineHeight: 1.5 }}><b style={{ color: '#5145cd' }}>HITL:</b> Polish → preview → send to approval → approve → publish. The AI never bypasses the approval gate.</div>
        </div>
      </section>
    </>
  );
}

function AnalyticsView({ analytics }: { analytics: any }) {
  const p = analytics?.pipeline || {};
  const live = analytics?.linkedin_performance || {};
  const cards = [
    ['Historical posts', p.historical_posts ?? 0, 'User-provided brand evidence'],
    ['Content created', p.content_items ?? 0, 'Drafts generated in Brand OS'],
    ['Awaiting approval', p.pending_approval ?? 0, 'Needs your decision'],
    ['Published', p.published_via_brand_os ?? 0, 'Published through approved workflow'],
  ];
  return (
    <>
      <div className="page-header">
        <div><div className="page-kicker"><BarChart3 size={13}/> Performance intelligence</div><h1 className="page-title">Know what the system is doing.</h1><p className="page-description">Operational analytics are available now. LinkedIn performance metrics are shown only when the official analytics capability is connected.</p></div>
      </div>
      <div className="metrics">{cards.map(([label, value, meta]) => <Metric key={label as string} icon={BarChart3} label={label} value={value} meta={meta} />)}</div>
      <section className="panel" style={{ marginTop: 16 }}>
        <div className="panel-head"><div><div className="panel-title">LinkedIn performance</div><div className="panel-subtitle">{live.available ? 'Official LinkedIn metrics are connected.' : 'No fabricated reach, impressions or engagement numbers.'}</div></div><span className="status-pill edited">● {live.available ? 'CONNECTED' : 'NOT CONNECTED'}</span></div>
        <div className="panel-body">
          <div className="empty-state" style={{ minHeight: 180 }}>
            <div className="empty-icon"><TrendingUp size={19}/></div>
            <strong>{live.available ? 'Metrics available' : 'Official performance data is not connected yet'}</strong>
            <span>{live.message || 'Connect the official LinkedIn analytics capability to populate post-level reach, reactions, comments and other supported metrics.'}</span>
          </div>
        </div>
      </section>
      <section className="panel" style={{ marginTop: 16 }}>
        <div className="panel-head"><div><div className="panel-title">How to use this section</div><div className="panel-subtitle">Analytics is for learning, not inventing conclusions.</div></div></div>
        <div className="panel-body" style={{ color: '#667085', fontSize: 11, lineHeight: 1.7 }}>
          Brand OS currently measures the content pipeline: what you imported, what was created, what is waiting for approval and what was actually published through the product. When official LinkedIn post analytics are available, those observed metrics can be added without using scraping or unsupported APIs.
        </div>
      </section>
    </>
  );
}

