'use client';

import { useEffect, useMemo, useState } from 'react';
import {
  Activity, ArrowUpRight, BarChart3, BrainCircuit, Check, ChevronRight, CircleCheck,
  Clock3, Command, ExternalLink, FileText, Gauge, Globe2, LayoutDashboard, Link2,
  LogOut, Menu, Pencil, Plus, RefreshCw, RotateCcw, Search, Settings,
  ShieldCheck, Sparkles, Target, TrendingUp, UserRound, WandSparkles, X, Zap
} from 'lucide-react';

const API_BASE = typeof window !== 'undefined' && window.location.hostname === 'localhost' ? (process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000') : '/api/backend';
const STORAGE_KEY = 'brand-os-token';

function getApiError(data: any, fallback: string) {
  if (typeof data?.detail === 'string') return data.detail;
  if (Array.isArray(data?.detail)) return data.detail.map((item: any) => item?.msg || String(item)).join('; ');
  if (typeof data?.message === 'string') return data.message;
  return fallback;
}

type ApprovalStatus = 'PENDING' | 'EDITED' | 'REGENERATED' | 'APPROVED' | 'REJECTED' | 'EXECUTED';
type ApprovalItem = { id: number; status: ApprovalStatus; action_type: string; reason: string | null; content: string; title?: string; topic?: string; approved_at?: string | null; created_at?: string };
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
type Tab = 'Dashboard' | 'Research' | 'Content' | 'LinkedIn Posts' | 'Analytics' | 'Settings';

const nav = [
  ['Dashboard', LayoutDashboard, 'Command center'],
  ['Research', Search, 'Find opportunities'],
  ['Content', FileText, 'Draft & refine'],
  ['LinkedIn Posts', ExternalLink, 'Approved & published'],
  ['Analytics', BarChart3, 'Performance'],
  ['Settings', Settings, 'Brand DNA'],
] as const;

export default function Home() {
  const [token, setToken] = useState<string | null>(null);
  const [profile, setProfile] = useState<Profile>({ display_name: 'User', role: 'owner' });
  const [linkedin, setLinkedin] = useState<LinkedInStatus>({ connected: false });
  const [linkedinProfileSynced, setLinkedinProfileSynced] = useState(false);
  const [brand, setBrand] = useState<BrandStatus>({ ready: false, status: 'NOT_INITIALIZED', source_post_count: 0 });
  const [brandTitle, setBrandTitle] = useState('');
  const [brandIndustry, setBrandIndustry] = useState('');
  const [brandAudience, setBrandAudience] = useState('');
  const [brandPositioning, setBrandPositioning] = useState('');
  const [brandTone, setBrandTone] = useState('');
  const [brandGoals, setBrandGoals] = useState('');
  const [historicalPostEntries, setHistoricalPostEntries] = useState<string[]>([]);
  const [brandEditing, setBrandEditing] = useState(false);
  const [analytics, setAnalytics] = useState<any>(null);
  const [draftLanguage, setDraftLanguage] = useState('');
  const [isImproving, setIsImproving] = useState(false);
  const [improvementProgress, setImprovementProgress] = useState(0);
  const [improvementNotes, setImprovementNotes] = useState<string[]>([]);
  const [isBuildingBrand, setIsBuildingBrand] = useState(false);
  const [queue, setQueue] = useState<ApprovalItem[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [statusFilter, setStatusFilter] = useState<'all' | 'PENDING' | 'EDITED' | 'REGENERATED' | 'APPROVED' | 'EXECUTED' | 'REJECTED'>('PENDING');
  const [searchTerm, setSearchTerm] = useState('');
  const [editedBody, setEditedBody] = useState('');
  const [reviewNote, setReviewNote] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [noticeTtl, setNoticeTtl] = useState(4500);
  const [isBusy, setIsBusy] = useState(false);
  const [busyAction, setBusyAction] = useState<'approve' | 'edit' | 'reject' | 'regenerate' | null>(null);
  const [operationProgress, setOperationProgress] = useState(0);
  const [operationStage, setOperationStage] = useState('');
  const [tab, setTab] = useState<Tab>('Dashboard');
  const [draftTitle, setDraftTitle] = useState('');
  const [draftTopic, setDraftTopic] = useState('');
  const [draftBody, setDraftBody] = useState('');
  const [isGenerating, setIsGenerating] = useState(false);
  const [generationProgress, setGenerationProgress] = useState(0);
  const [generationStage, setGenerationStage] = useState('');
  const [opportunities, setOpportunities] = useState<Opportunity[]>([]);
  const [isResearching, setIsResearching] = useState(false);
  const [researchProgress, setResearchProgress] = useState(0);
  const [researchStage, setResearchStage] = useState('');
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [loading, setLoading] = useState(false);

  const headers = (authToken = token) => authToken ? { Authorization: `Bearer ${authToken}` } : {};

  useEffect(() => {
    if (!notice) return;
    const timer = window.setTimeout(() => setNotice(null), noticeTtl);
    return () => window.clearTimeout(timer);
  }, [notice, noticeTtl]);

  useEffect(() => {
    if (!isGenerating) {
      setGenerationProgress(0);
      setGenerationStage('');
      return;
    }
    setGenerationProgress(10);
    setGenerationStage('Preparing your Brand DNA…');
    const timers = [
      window.setTimeout(() => { setGenerationProgress(28); setGenerationStage('Generating with AI…'); }, 450),
      window.setTimeout(() => { setGenerationProgress(62); setGenerationStage('Shaping the draft around your voice…'); }, 1800),
    ];
    return () => timers.forEach(window.clearTimeout);
  }, [isGenerating]);

  useEffect(() => {
    if (!isImproving) {
      setImprovementProgress(0);
      return;
    }
    setImprovementProgress(12);
    const timer = window.setTimeout(() => setImprovementProgress(58), 700);
    return () => window.clearTimeout(timer);
  }, [isImproving]);

  useEffect(() => {
    if (!isResearching) {
      setResearchProgress(0);
      setResearchStage('');
      return;
    }
    setResearchProgress(8);
    setResearchStage('Connecting to live sources…');
    const timers = [
      window.setTimeout(() => { setResearchProgress(24); setResearchStage('Collecting current public sources…'); }, 700),
      window.setTimeout(() => { setResearchProgress(46); setResearchStage('Cross-checking and deduplicating evidence…'); }, 1800),
      window.setTimeout(() => { setResearchProgress(68); setResearchStage('Matching evidence to your Brand DNA…'); }, 3000),
      window.setTimeout(() => { setResearchProgress(82); setResearchStage('Ranking opportunities…'); }, 4800),
    ];
    return () => timers.forEach(window.clearTimeout);
  }, [isResearching]);

useEffect(() => {
    if (!busyAction) {
      setOperationProgress(0);
      setOperationStage('');
      return;
    }
    setOperationProgress(12);
    setOperationStage(busyAction === 'regenerate' ? 'Regenerating with your feedback…' : 'Processing your request…');
    const timer = window.setTimeout(() => {
      setOperationProgress(62);
      setOperationStage(busyAction === 'regenerate' ? 'Running guardrails and creating the new version…' : 'Applying the change…');
    }, 900);
    return () => window.clearTimeout(timer);
  }, [busyAction]);

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
      // Load the core workspace first. Optional panels must never block the
      // dashboard/Brand DNA from appearing.
      const [profileRes, approvalsRes, linkedinRes, brandRes] = await Promise.all([
        fetch(`${API_BASE}/api/auth/me`, { headers: headers(authToken) }),
        fetch(`${API_BASE}/api/dashboard/approvals`, { headers: headers(authToken) }),
        fetch(`${API_BASE}/api/linkedin/status`, { headers: headers(authToken) }),
        fetch(`${API_BASE}/api/brand/status`, { headers: headers(authToken) }),
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

      let brandJson = brandRes.ok ? await brandRes.json() : { ready: false, status: 'NOT_INITIALIZED', source_post_count: 0 };

      // Keep Brand DNA profile facts synchronized from the connected LinkedIn
      // account once per browser session. This replaces the old manual profile form.
      if (linkedinRes.ok && !linkedinProfileSynced) {
        setLinkedinProfileSynced(true);
        try {
          const syncRes = await fetch(API_BASE + '/api/linkedin/sync-profile', {
            method: 'POST',
            headers: headers(authToken),
          });
          if (syncRes.ok) {
            const refreshedBrandRes = await fetch(API_BASE + '/api/brand/status', { headers: headers(authToken) });
            if (refreshedBrandRes.ok) brandJson = await refreshedBrandRes.json();
          }
        } catch {
          // Profile sync is best-effort. Existing Brand DNA remains usable.
        }
      }

      setBrand(brandJson);
      const p = brandJson.profile || {};
      setBrandTitle(p.professional_title || '');
      setBrandIndustry(p.industry || '');
      setBrandAudience(p.audience || '');
      setBrandPositioning(p.brand_positioning || '');
      setBrandTone(p.tone || '');
      setBrandGoals(Array.isArray(p.goals) ? p.goals.join(', ') : (p.goals || ''));

      // Brand status now carries the frozen source-post snapshot, so Brand DNA
      // does not depend on a second request just to display the user's posts.
      const sourcePosts = (brandJson.source_posts || [])
        .map((item: any) => item.body)
        .filter((body: any) => typeof body === 'string' && body.trim());
      if (sourcePosts.length) setHistoricalPostEntries(sourcePosts.slice(0, 10));

      const nextQueue: ApprovalItem[] = (approvalsJson.pending_approvals || []).map((item: any) => ({
        id: item.id, status: item.status, action_type: item.action_type, reason: item.reason, content: item.content || '',
        title: item.title || '', topic: item.topic || '', approved_at: item.approved_at || null, created_at: item.created_at,
      }));
      setQueue(nextQueue);
      if (nextQueue.length && !nextQueue.some((i) => i.id === selectedId)) setSelectedId(nextQueue[0].id);

      setLoading(false);

      // Optional workspace panels load independently. A slow research feed or
      // analytics query must not blank/freeze the main workspace.
      void Promise.all([
        fetch(`${API_BASE}/api/research/opportunities`, { headers: headers(authToken) }),
        fetch(`${API_BASE}/api/analytics/overview`, { headers: headers(authToken) }),
      ]).then(async ([opportunityRes, analyticsRes]) => {
        const opportunityJson = opportunityRes.ok ? await opportunityRes.json() : { opportunities: [] };
        setOpportunities(opportunityJson.opportunities || []);
        const analyticsJson = analyticsRes.ok ? await analyticsRes.json() : null;
        setAnalytics(analyticsJson);
      }).catch(() => {
        // Optional panels are allowed to fail without affecting the core workspace.
      });
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Unable to load dashboard data');
      setLoading(false);
    }
  };
  useEffect(() => { fetchData(token); }, [token]);
  useEffect(() => {
    const selected = queue.find((item) => item.id === selectedId);
    if (!selected) return;
    setEditedBody(selected.content || '');
    const savedFeedback = window.localStorage.getItem(`brand-os-regeneration-feedback:${selected.id}`);
    setReviewNote(savedFeedback || '');
  }, [selectedId, queue]);

  const filteredQueue = useMemo(() => {
    const query = searchTerm.trim().toLowerCase();
    const pendingStatuses = new Set(['PENDING', 'REGENERATED', 'EDITED']);
    return queue.filter((item) => {
      const normalizedStatus = String(item.status || '').trim().toUpperCase();
      const statusMatch = statusFilter === 'all'
        ? true
        : statusFilter === 'PENDING'
          ? pendingStatuses.has(normalizedStatus)
          : normalizedStatus === statusFilter;
      const haystack = `${item.action_type} ${item.content} ${item.reason || ''}`.toLowerCase();
      return statusMatch && (!query || haystack.includes(query));
    });
  }, [queue, searchTerm, statusFilter]);

  useEffect(() => {
    if (!filteredQueue.length) {
      setSelectedId(null);
      return;
    }
    if (!filteredQueue.some((item) => item.id === selectedId)) {
      setSelectedId(filteredQueue[0].id);
    }
  }, [filteredQueue, selectedId]);

  const selectedApproval = queue.find((item) => item.id === selectedId) ?? null;
  const summary = useMemo(() => ({
    pending: queue.filter((i) => ['PENDING', 'EDITED', 'REGENERATED'].includes(i.status)).length,
    reviewed: queue.filter((i) => ['APPROVED', 'EXECUTED'].includes(i.status)).length,
    rejected: queue.filter((i) => i.status === 'REJECTED').length,
    executed: queue.filter((i) => i.status === 'EXECUTED').length,
  }), [queue]);

  const initials = (profile.display_name || 'User').split(' ').map((x) => x[0]).slice(0, 2).join('').toUpperCase();
  const closeSidebar = () => setSidebarOpen(false);
  const connectLinkedIn = () => { window.location.href = '/api/auth/linkedin/start'; };
  const cancelBrandEdit = async () => { await fetchData(); setBrandEditing(false); };
  const logout = async () => {
    try {
      if (token) {
        await fetch(API_BASE + '/api/auth/logout', { method: 'POST', headers: headers(token) });
      }
    } finally {
      window.localStorage.removeItem(STORAGE_KEY);
      setToken(null); setQueue([]); setLinkedin({ connected: false }); setLinkedinProfileSynced(false); closeSidebar();
    }
  };
  const go = (next: Tab) => { setTab(next); closeSidebar(); window.scrollTo({ top: 0, behavior: 'smooth' }); };

  const requireBrand = (actionLabel: string) => {
    if (brand.ready) return true;
    go('Settings');
    setError('Brand DNA is not set up yet. Before ' + actionLabel + ', connect LinkedIn and build Brand DNA. Previous posts are optional; you can add 3–10 for stronger voice calibration.');
    return false;
  };

  const runApprovalAction = async (action: 'approve' | 'edit' | 'reject' | 'regenerate', payload?: Record<string, string>) => {
    if (!selectedApproval || !token) return;
    if (action === 'regenerate' && !requireBrand('regenerating content')) return;
    if (action === 'regenerate' && !reviewNote.trim()) {
      setError('Add feedback for the regeneration first. The Regenerate button will stay disabled until you do.');
      return;
    }
    setIsBusy(true); setBusyAction(action); setError(null); setNotice(null);
    if (action === 'approve') {
      setOperationProgress(20);
      setOperationStage('Authorizing publication…');
    }
    try {
      const res = await fetch(`${API_BASE}/api/approvals/${selectedApproval.id}/${action}`, {
        method: 'POST', headers: { ...headers(), 'Content-Type': 'application/json' }, body: JSON.stringify(payload || {}),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(getApiError(data, `Action failed: ${action}`));
      if (action === 'approve' && data.published === false) {
        throw new Error(data.message || 'Approval was recorded, but LinkedIn publication failed.');
      }
      if (action === 'regenerate') {
        window.localStorage.removeItem(`brand-os-regeneration-feedback:${selectedApproval.id}`);
        setReviewNote('');
      }
      setOperationProgress(action === 'approve' ? 82 : 88);
      setOperationStage(action === 'regenerate' ? 'Refreshing the approval queue…' : 'Refreshing the workspace…');
      await fetchData();
      setOperationProgress(100);
      setOperationStage('Done');
      setNoticeTtl(action === 'regenerate' ? 1800 : 4500);
      setNotice(
        action === 'regenerate'
          ? 'Regenerated successfully.'
          : action === 'approve'
            ? 'Approved and published to LinkedIn.'
            : 'Action completed successfully.'
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Approval action failed');
    } finally {
      setIsBusy(false);
      setBusyAction(null);
    }
  };

  const generateContent = async () => {
    if (!token) return;
    if (!requireBrand('generating content')) return;
    setIsGenerating(true); setError(null); setNoticeTtl(4500); setNotice(null);
    try {
      setGenerationProgress(34);
      setGenerationStage('Generating with AI…');
      const res = await fetch(API_BASE + '/api/agent/events', {
        method: 'POST', headers: { ...headers(), 'Content-Type': 'application/json' },
        body: JSON.stringify({ event_type: 'manual_generate_content', payload: { objective: 'Generate a fresh LinkedIn content opportunity for human review.' } }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(getApiError(data, 'Content generation failed'));
      setGenerationProgress(84);
      setGenerationStage('Refreshing the approval queue…');
      await fetchData();
      setGenerationProgress(100);
      setGenerationStage('Done');
      go('Dashboard');
      setNotice(
        data.approval_queued
          ? 'New content suggestion generated and added to the approval queue.'
          : data.blocked_by_guardrails
            ? 'Content was generated but held back by guardrails and was not added to the approval queue.'
            : 'No new suggestion was created. Try again with a different feedback or research angle.'
      );
    } catch (e) { setError(e instanceof Error ? e.message : 'Content generation failed'); }
    finally { setIsGenerating(false); }
  };

  const discoverResearch = async () => {
    if (!token) return;
    if (!requireBrand('running live research')) return;
    setIsResearching(true); setResearchProgress(8); setResearchStage('Starting live research…');
    setError(null); setNoticeTtl(4500); setNotice(null);
    try {
      const res = await fetch(API_BASE + '/api/research/discover', {
        method: 'POST', headers: { ...headers(), 'Content-Type': 'application/json' }, body: JSON.stringify({}),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(getApiError(data, 'Live research failed'));
      setResearchProgress(96);
      setResearchStage(data.fallback ? 'Using the latest available research evidence…' : 'Finalizing ranked opportunities…');
      setOpportunities(data.opportunities || []);
      setResearchProgress(100);
      setResearchStage('Research complete');
      setNotice(data.fallback
        ? 'Live sources were temporarily unavailable. Showing the latest available research evidence.'
        : 'Fresh research completed. Opportunities were ranked against your Brand DNA.');
    } catch (e) {
      setResearchProgress(0);
      setResearchStage('');
      setError(e instanceof Error ? e.message : 'Live research failed');
    } finally {
      setIsResearching(false);
    }
  };

  const updateHistoricalPost = (index: number, value: string) =>
    setHistoricalPostEntries((current) => current.map((post, i) => i === index ? value : post));
  const addHistoricalPost = () =>
    setHistoricalPostEntries((current) => current.length >= 10 ? current : [...current, '']);
  const removeHistoricalPost = (index: number) =>
    setHistoricalPostEntries((current) => current.filter((_, i) => i !== index));

  const buildBrand = async () => {
    if (!token) return;
    const blocks = historicalPostEntries.map((body) => body.trim()).filter(Boolean);

    // Historical posts are optional. If a user chooses to provide them, require
    // the full 3–10 range so we never silently analyze an incomplete sample.
    if (blocks.length > 0 && blocks.length < 3) {
      setError('Previous posts are optional. Leave them empty, or add at least 3 and up to 10 posts.');
      return;
    }

    setIsBuildingBrand(true); setError(null); setNoticeTtl(4500); setNotice(null);
    try {
      const endpoint = blocks.length ? '/api/brand/onboard' : '/api/brand/initialize';
      const body = blocks.length
        ? {
            display_name: profile.display_name,
            posts: blocks.map((body) => ({ body })),
          }
        : {
            display_name: profile.display_name,
            professional_title: brandTitle || null,
            industry: brandIndustry || null,
          };

      const res = await fetch(API_BASE + endpoint, {
        method: 'POST',
        headers: { ...headers(), 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(getApiError(data, 'Brand Intelligence setup failed'));

      const memory = data.brand_memory || {};
      setBrand({ ...memory, ready: memory.status === 'READY' });
      setNotice(
        blocks.length
          ? 'Brand Intelligence updated using your LinkedIn profile plus ' + blocks.length + ' imported posts.'
          : 'Brand Intelligence is ready using your LinkedIn profile. You can add previous posts later to strengthen voice calibration.'
      );
      await fetchData();
      setBrandEditing(false);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Brand Intelligence setup failed');
    } finally {
      setIsBuildingBrand(false);
    }
  };

  const improveDraft = async () => {
    if (!token || !draftBody.trim()) { setError('Write a draft first, then ask Brand OS to polish it.'); return; }
    if (!requireBrand('polishing content')) return;
    setIsImproving(true); setError(null); setNoticeTtl(4500); setNotice(null);
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
    if (!requireBrand('sending content to approval')) return;
    setIsBusy(true); setError(null); setNoticeTtl(4500); setNotice(null);
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
                    <div className="page-kicker" style={{ color: '#bdb6ff' }}>
                      {brand.ready ? <><Sparkles size={13} /> Brand intelligence active</> : <><BrainCircuit size={13} /> Brand DNA setup required</>}
                    </div>
                    <h1>{brand.ready ? 'Turn your expertise into a recognizable point of view.' : 'Start by teaching Brand OS your voice.'}</h1>
                    <p>{brand.ready
                      ? 'Research, content strategy, drafting and review — orchestrated around your brand voice, with you always in control of what reaches LinkedIn.'
                      : 'Your LinkedIn profile is the factual starting point. Brand OS can build your Brand DNA automatically, and previous posts are optional evidence for stronger voice calibration.'}</p>
                    <div className="hero-actions">
                      <button className="button primary progress-button" onClick={generateContent} disabled={isGenerating}>
                        <span className="button-content"><WandSparkles size={15} /> {isGenerating ? generationStage || 'Generating…' : 'Generate content'}</span>
                        {isGenerating && <span className="button-progress-track"><span style={{ width: generationProgress + '%' }} /></span>}
                      </button>
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
                <Metric icon={CircleCheck} label="Approved" value={summary.reviewed} meta="Approved for publication" />
                <Metric icon={TrendingUp} label="Published" value={summary.executed} meta="Tracked by Brand OS" />
                <Metric icon={ShieldCheck} label="Guardrail status" value="ON" meta="Claims · voice · duplicate · action" />
                <Metric icon={BrainCircuit} label="Brand Pulse" value={brand.ready ? 'ACTIVE' : 'INACTIVE'} meta={brand.ready ? ((brand.current_post_count ?? brand.source_post_count) + ' signals in memory') : 'Set up before AI actions'} />
              </div>

              <section className="panel approval-panel">
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
                  isBusy={isBusy} busyAction={busyAction} operationProgress={operationProgress} operationStage={operationStage}
                  onAction={runApprovalAction}
                />
              </section>
            </>
          )}

          {tab === 'Research' && <ResearchView opportunities={opportunities} isResearching={isResearching} researchProgress={researchProgress} researchStage={researchStage} onResearch={discoverResearch} />}
          {tab === 'Content' && <ContentStudio profile={profile} title={draftTitle} setTitle={setDraftTitle} topic={draftTopic} setTopic={setDraftTopic} body={draftBody} setBody={setDraftBody} language={draftLanguage} setLanguage={setDraftLanguage} busy={isBusy} improving={isImproving} improvementProgress={improvementProgress} improvementNotes={improvementNotes} onImprove={improveDraft} onSubmit={createDraft} />}
          {tab === 'LinkedIn Posts' && <LinkedInPostsView posts={queue.filter((item) => item.status === 'APPROVED' || item.status === 'EXECUTED')} />}
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

// Production copy sync marker: ensure latest UI copy is included in deployment.
function ApprovalWorkspace(props: any) {
  const { queue, selected, selectedId, setSelectedId, searchTerm, setSearchTerm, statusFilter, setStatusFilter, editedBody, setEditedBody, reviewNote, setReviewNote, isBusy, busyAction, operationProgress, operationStage, onAction } = props;
  return (
    <div className="queue-layout">
      <div className="queue-list">
        <div className="queue-tools">
          <div className="searchbox"><Search size={13}/><input className="input" placeholder="Search drafts…" value={searchTerm} onChange={(e) => setSearchTerm(e.target.value)} /></div>
          <div className="filter-row">
            {(['PENDING','REGENERATED','EDITED','APPROVED','EXECUTED','REJECTED','all'] as const).map((x) => <button key={x} className={`filter-chip ${statusFilter === x ? 'active' : ''}`} onClick={() => setStatusFilter(x)}>{x === 'all' ? 'All' : x[0] + x.slice(1).toLowerCase()}</button>)}
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
              <div className="review-label" style={{ marginTop: 10, marginBottom: 7 }}>Feedback for regeneration <span className="form-help">(optional)</span></div>
              <textarea
                className="textarea"
                style={{ minHeight: 82, marginTop: 0 }}
                value={reviewNote}
                onChange={(e) => {
                  const value = e.target.value;
                  setReviewNote(value);
                  if (selected?.id) {
                    const key = `brand-os-regeneration-feedback:${selected.id}`;
                    if (value.trim()) window.localStorage.setItem(key, value);
                    else window.localStorage.removeItem(key);
                  }
                }}
                placeholder="Tell us what to change, add, or remove. Example: Make the opening less polished and add the point about stakeholder alignment."
              />
              {['PENDING','EDITED','REGENERATED'].includes(selected.status) ? (
                <>
                  <div className="review-actions">
                    <button className="button success progress-button" disabled={isBusy} onClick={() => onAction('approve')}>
                      <span className="button-content"><Check size={14}/> {busyAction === 'approve' ? operationStage || 'Publishing…' : 'Approve & publish'}</span>
                      {busyAction === 'approve' && <span className="button-progress-track"><span style={{ width: operationProgress + '%' }} /></span>}
                    </button>
                    <button className="button" disabled={isBusy} onClick={() => onAction('edit', { edited_body: editedBody, reason: reviewNote || 'Edited during review.' })}><Pencil size={14}/> Save edit</button>
                    <button
                      className="button progress-button"
                      disabled={isBusy || !reviewNote.trim()}
                      title={!reviewNote.trim() ? 'Add feedback before regenerating.' : 'Regenerate using your feedback'}
                      onClick={() => onAction('regenerate', { reason: reviewNote.trim() })}
                    >
                      <span className="button-content"><RotateCcw size={14}/> {busyAction === 'regenerate' ? operationStage || 'Regenerating…' : 'Regenerate'}</span>
                      {busyAction === 'regenerate' && <span className="button-progress-track"><span style={{ width: operationProgress + '%' }} /></span>}
                    </button>
                    <button className="button danger" disabled={isBusy} onClick={() => onAction('reject', { reason: reviewNote || 'Rejected by reviewer.' })}><X size={14}/> Reject</button>
                  </div>
                  <div className="form-help" style={{ marginTop: 8 }}>
                    {reviewNote.trim() ? 'Regenerate will use this feedback and keep the new version behind the approval gate.' : 'Add feedback above to enable Regenerate.'}
                  </div>
                </>
              ) : (
                <>
                  <div className={selected.status === 'EXECUTED' ? 'notice success' : 'notice error'} style={{ marginTop: 10 }}>
                    <CircleCheck size={15}/>
                    <span>{selected.status === 'EXECUTED' ? 'approved and published to linkedin' : selected.status === 'APPROVED' ? 'Approved, but publication did not complete. Use Publish to LinkedIn to retry.' : 'This post is no longer awaiting a decision.'}</span>
                  </div>
                  {selected.status === 'APPROVED' && (
                    <div className="review-actions review-actions-publish">
                      <button className="button success progress-button publish-retry-button" disabled={isBusy} onClick={() => onAction('approve')}>
                        <span className="button-content"><ExternalLink size={14}/>{busyAction === 'approve' ? operationStage || 'Publishing…' : 'Publish to LinkedIn'}</span>
                        {busyAction === 'approve' && <span className="button-progress-track"><span style={{ width: operationProgress + '%' }} /></span>}
                      </button>
                    </div>
                  )}
                </>
              )}
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

function LinkedInPostsView({ posts }: { posts: ApprovalItem[] }) {
  return (
    <>
      <div className="page-header">
        <div>
          <div className="page-kicker"><ExternalLink size={13}/> LinkedIn content</div>
          <h1 className="page-title">Your approved LinkedIn posts.</h1>
          <p className="page-description">Approved content stays visible here even after it leaves the review queue. Published posts are marked separately.</p>
        </div>
      </div>
      <section className="panel">
        <div className="panel-head">
          <div><div className="panel-title">Approved posts</div><div className="panel-subtitle">{posts.length} post{posts.length === 1 ? '' : 's'} in the workflow</div></div>
        </div>
        <div className="post-stack">
          {posts.length ? posts.map((post) => (
            <article className="post-entry" key={post.id}>
              <div className="post-entry-head">
                <span className="post-index">POST #{post.id}</span>
                <StatusPill status={post.status}/>
              </div>
              {post.title ? <div style={{ fontWeight: 700, fontSize: 13, marginBottom: 7 }}>{post.title}</div> : null}
              {post.topic ? <div className="form-help" style={{ marginBottom: 9 }}>{post.topic}</div> : null}
              <div style={{ whiteSpace: 'pre-wrap', fontSize: 12, lineHeight: 1.7, color: '#344054' }}>{post.content}</div>
              {post.approved_at ? <div className="form-help" style={{ marginTop: 10 }}>Approved {new Date(post.approved_at).toLocaleString()}</div> : null}
            </article>
          )) : <EmptyState icon={ExternalLink} title="No approved posts yet" text="Approve a post from the editorial queue and it will appear here automatically." />}
        </div>
      </section>
    </>
  );
}

function ResearchView({ opportunities, isResearching, researchProgress, researchStage, onResearch }: { opportunities: Opportunity[]; isResearching: boolean; researchProgress: number; researchStage: string; onResearch: () => void }) {
  return (
    <>
      <div className="page-header">
        <div><div className="page-kicker"><Search size={13}/> Intelligence layer</div><h1 className="page-title">Research & opportunities</h1><p className="page-description">Live evidence is combined with your Brand DNA before an idea reaches the drafting engine.</p></div>
        <button className="button primary progress-button" onClick={onResearch} disabled={isResearching}>
          <span className="button-content"><Search size={14}/>{isResearching ? researchStage || 'Researching…' : 'Research now'}</span>
          {isResearching && <span className="button-progress-track"><span style={{ width: researchProgress + '%' }} /></span>}
        </button>
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

function ContentStudio({ profile, title, setTitle, topic, setTopic, body, setBody, language, setLanguage, busy, improving, improvementProgress, improvementNotes, onImprove, onSubmit }: any) {
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
            <button className="button primary progress-button" disabled={improving || !body.trim()} onClick={onImprove}>
              <span className="button-content"><WandSparkles size={14}/>{improving ? 'Polishing…' : 'Improvise / polish with Brand OS'}</span>
              {improving && <span className="button-progress-track"><span style={{ width: improvementProgress + '%' }} /></span>}
            </button>
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
  const totals = live.totals || {};
  const trend = Array.isArray(live.trend) ? live.trend : [];
  const cards = [
    ['Historical posts', p.historical_posts ?? 0, 'User-provided brand evidence'],
    ['Content created', p.content_items ?? 0, 'Drafts generated in Brand OS'],
    ['Awaiting approval', p.pending_approval ?? 0, 'Needs your decision'],
    ['Published', p.published_via_brand_os ?? 0, 'Published through approved workflow'],
  ];
  const maxImpressions = Math.max(1, ...trend.map((row: any) => Number(row.IMPRESSION || 0)));

  return (
    <>
      <div className="page-header">
        <div>
          <div className="page-kicker"><BarChart3 size={13}/> Performance intelligence</div>
          <h1 className="page-title">Know what the system is doing.</h1>
          <p className="page-description">Operational analytics are available now. LinkedIn performance uses official LinkedIn member analytics only when the required permissions are granted.</p>
        </div>
      </div>

      <div className="metrics">
        {cards.map(([label, value, meta]) => <Metric key={label as string} icon={BarChart3} label={label} value={value} meta={meta} />)}
      </div>

{/* Temporarily hidden until LinkedIn Community Management analytics access is available. Code intentionally retained. */}
      {false && (
      <section className="panel" style={{ marginTop: 16 }}>
        <div className="panel-head">
          <div>
            <div className="panel-title">LinkedIn performance</div>
            <div className="panel-subtitle">
              {live.available ? `Official LinkedIn data · last ${live.window_days || 30} days` : 'Waiting for official LinkedIn analytics access'}
            </div>
          </div>
          <span className={`status-pill ${live.available ? 'approved' : 'edited'}`}>● {live.available ? 'CONNECTED' : 'NOT CONNECTED'}</span>
        </div>

        <div className="panel-body">
          {live.available ? (
            <>
              <div className="metrics" style={{ gridTemplateColumns: 'repeat(5, minmax(0, 1fr))', marginBottom: 18 }}>
                <Metric icon={TrendingUp} label="Impressions" value={totals.IMPRESSION ?? 0} meta="Lifetime within selected window" />
                <Metric icon={Target} label="Reach" value={totals.MEMBERS_REACHED ?? 0} meta="Members reached" />
                <Metric icon={CircleCheck} label="Reactions" value={totals.REACTION ?? 0} meta="Total reactions" />
                <Metric icon={Activity} label="Comments" value={totals.COMMENT ?? 0} meta="Total comments" />
                <Metric icon={Zap} label="Engagement rate" value={`${live.engagement_rate ?? 0}%`} meta="Reactions + comments + reshares / impressions" />
              </div>

              <div className="panel" style={{ border: '1px solid #eaecf0', boxShadow: 'none' }}>
                <div className="panel-head">
                  <div><div className="panel-title">Daily trend</div><div className="panel-subtitle">Impressions and engagement reported by LinkedIn.</div></div>
                </div>
                <div className="panel-body">
                  {trend.length ? (
                    <div style={{ display: 'grid', gap: 9 }}>
                      {trend.slice(-14).map((row: any) => (
                        <div key={row.date} style={{ display: 'grid', gridTemplateColumns: '72px 1fr 70px', gap: 9, alignItems: 'center', fontSize: 10 }}>
                          <span style={{ color: '#667085' }}>{new Date(row.date).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })}</span>
                          <div style={{ height: 8, background: '#f2f4f7', borderRadius: 99, overflow: 'hidden' }}>
                            <div style={{ width: `${Math.max(2, Math.round((Number(row.IMPRESSION || 0) / maxImpressions) * 100))}%`, height: '100%', background: '#5145cd', borderRadius: 99 }} />
                          </div>
                          <span style={{ textAlign: 'right', color: '#344054' }}>{Number(row.IMPRESSION || 0).toLocaleString()} imp.</span>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div className="empty-state" style={{ minHeight: 120 }}>
                      <strong>No daily activity returned yet</strong>
                      <span>LinkedIn may need more time to report analytics for newly published posts.</span>
                    </div>
                  )}
                </div>
              </div>
            </>
          ) : (
            <div className="empty-state" style={{ minHeight: 210 }}>
              <div className="empty-icon"><TrendingUp size={19}/></div>
              <strong>Official LinkedIn performance data is not connected yet</strong>
              <span>{live.message || 'The app needs LinkedIn Community Management member analytics access before it can show impressions, reach and engagement.'}</span>
              {live.authorization_required ? (
                <div style={{ maxWidth: 620, fontSize: 10, lineHeight: 1.6, color: '#667085', marginTop: 6 }}>
                  Required permissions: <b>r_member_postAnalytics</b> for post performance and <b>r_member_profileAnalytics</b> for follower/profile trends. After those permissions are enabled for the LinkedIn developer app, reconnect the LinkedIn account so the new consent is issued.
                </div>
              ) : null}
            </div>
          )}
        </div>
      </section>
      )}

{/* Temporarily hidden until LinkedIn Community Management analytics access is available. Code intentionally retained. */}
      {false && (
      <section className="panel" style={{ marginTop: 16 }}>
        <div className="panel-head"><div><div className="panel-title">What will appear here</div><div className="panel-subtitle">Only observed LinkedIn data is used.</div></div></div>
        <div className="panel-body" style={{ color: '#667085', fontSize: 11, lineHeight: 1.7 }}>
          Once analytics access is active, this view will show post impressions, reach, reactions, comments, reshares and engagement trends from LinkedIn's official member analytics API. Brand OS will not scrape LinkedIn or fabricate performance numbers.
        </div>
      </section>
      )}
    </>
  );
}

function SettingsView(props: any) {
  const {
    brand, profile, brandTitle, brandIndustry, brandAudience, brandPositioning,
    brandTone, brandGoals, posts, updatePost, addPost, removePost, building,
    onBuild, linkedin, onConnect, editing, setEditing, onCancel
  } = props;

  const count = posts.filter((x: string) => x.trim()).length;

  return (
    <>
      <div className="page-header">
        <div>
          <div className="page-kicker"><BrainCircuit size={13}/> Brand intelligence</div>
          <h1 className="page-title">Your brand memory.</h1>
          <p className="page-description">Your LinkedIn profile is used as the factual baseline. Brand OS derives the remaining brand signals from the profile and any content you explicitly provide.</p>
        </div>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          <span className={"status-pill " + (brand.ready ? 'approved' : 'edited')}>{brand.ready ? '● ACTIVE' : '● SETUP NEEDED'}</span>
          {linkedin.connected && <button className="button" onClick={onConnect}><Link2 size={14}/> Refresh LinkedIn profile</button>}
          {brand.ready && !editing && <button className="button" onClick={() => setEditing(true)}><Pencil size={14}/> Manage Brand DNA</button>}
        </div>
      </div>

      {!brand.ready || editing ? (
        <div className="settings-stack">
          <section className="panel settings-card">
            <div className="panel-head" style={{ padding: 0, border: 0 }}>
              <div>
                <h2 className="settings-title">Build your Brand DNA</h2>
                <p className="settings-copy">Profile facts are pulled from your connected LinkedIn account. You do not need to type your role or industry manually.</p>
              </div>
              {brand.ready && <button className="button" onClick={onCancel}><X size={14}/> Cancel</button>}
            </div>

            <div className="profile-grid" style={{ marginTop: 16 }}>
              <div className="form-group">
                <span className="form-label">Professional title</span>
                <div className="readonly-field">{brandTitle || 'LinkedIn did not provide a headline for this account yet.'}</div>
              </div>
              <div className="form-group">
                <span className="form-label">Industry</span>
                <div className="readonly-field">{brandIndustry || 'LinkedIn did not provide an industry field for this account.'}</div>
              </div>
              <div className="form-group">
                <span className="form-label">Who you want to reach</span>
                <div className="readonly-field">{brandAudience || 'Derived by Brand OS after Brand DNA analysis.'}</div>
              </div>
              <div className="form-group">
                <span className="form-label">Goals</span>
                <div className="readonly-field">{brandGoals || 'Derived from your LinkedIn profile and future content signals.'}</div>
              </div>
              <div className="form-group">
                <span className="form-label">Desired tone</span>
                <div className="readonly-field">{brandTone || 'Learned from your profile and writing signals.'}</div>
              </div>
              <div className="form-group">
                <span className="form-label">How you want to be known</span>
                <div className="readonly-field">{brandPositioning || 'Derived as part of Brand Intelligence.'}</div>
              </div>
            </div>

            <div style={{ marginTop: 14, padding: 11, borderRadius: 11, background: '#f8f7ff', color: '#667085', fontSize: 10, lineHeight: 1.55 }}>
              <b style={{ color: '#5145cd' }}>LinkedIn-sourced:</b> Name and any profile fields the connected LinkedIn API makes available. Brand OS will never invent credentials or experience.
            </div>
          </section>

          <section className="panel settings-card">
            <div style={{ display: 'flex', justifyContent: 'space-between', gap: 10, alignItems: 'center', flexWrap: 'wrap' }}>
              <div>
                <h2 className="settings-title">Optional voice calibration</h2>
                <p className="settings-copy">Add 3–10 previous LinkedIn posts if you want stronger evidence of your writing style. You can also skip this completely.</p>
              </div>
              <span className={"status-pill " + (count >= 3 ? 'approved' : 'edited')}>{count}/10 posts</span>
            </div>

            <div className="post-stack">
              {posts.map((post: string, index: number) => (
                <div className="post-entry" key={index}>
                  <div className="post-entry-head">
                    <span className="post-index">SOURCE POST {String(index + 1).padStart(2,'0')}</span>
                    {posts.length > 1 && <button className="link-button" onClick={() => removePost(index)}>Remove</button>}
                  </div>
                  <textarea className="textarea" style={{ minHeight: 125 }} value={post} onChange={(e) => updatePost(index, e.target.value)} placeholder={'Paste the complete text of LinkedIn post ' + (index + 1) + '…'} />
                </div>
              ))}
            </div>

            <div style={{ display: 'flex', justifyContent: 'space-between', gap: 10, alignItems: 'center', marginTop: 12, flexWrap: 'wrap' }}>
              <button className="button" onClick={addPost} disabled={posts.length >= 10}><Plus size={14}/>{posts.length >= 10 ? 'Maximum reached' : 'Add another post'}</button>
              <button className="button primary" onClick={onBuild} disabled={building || count === 1 || count === 2}>
                <RefreshCw size={14}/>
                {building ? 'Building…' : brand.ready ? 'Refresh Brand Intelligence' : 'Build Brand DNA'}
              </button>
            </div>
            {(count === 1 || count === 2) && (
              <div style={{ marginTop: 10, color: '#b42318', fontSize: 10 }}>
                Add one more post to reach 3, or remove the partial sample and build without historical posts.
              </div>
            )}
          </section>
        </div>
      ) : (
        <div className="settings-stack">
          <section className="panel settings-card">
            <div className="panel-head" style={{ padding: 0, border: 0 }}>
              <div><h2 className="settings-title">Saved Brand DNA</h2><p className="settings-copy">Read-only view of the profile and signals used by Brand OS.</p></div>
              <span className="tag"><ShieldCheck size={10}/> Frozen</span>
            </div>
            <div className="profile-grid" style={{ marginTop: 16 }}>
              {[
                ['Professional title', brandTitle],
                ['Industry', brandIndustry],
                ['Who you want to reach', brandAudience],
                ['Goals', brandGoals],
                ['Desired tone', brandTone],
                ['How you want to be known', brandPositioning],
              ].map(([label, value]) => (
                <div className="form-group" key={label as string}>
                  <span className="form-label">{label}</span>
                  <div className="readonly-field">{value || 'Not yet available'}</div>
                </div>
              ))}
            </div>
          </section>

          <section className="panel settings-card">
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 14 }}>
              <div><h2 className="settings-title">Voice calibration</h2><p className="settings-copy">Previous posts are optional. Brand OS can keep learning from approved and published content.</p></div>
              <span className="status-pill approved">● {count} SAVED</span>
            </div>
            {count ? (
              <div className="post-stack" style={{ marginTop: 14 }}>
                {posts.filter((x: string) => x.trim()).map((post: string, index: number) => (
                  <div className="post-entry" key={index}>
                    <div className="post-entry-head"><span className="post-index">SOURCE POST {String(index + 1).padStart(2,'0')}</span></div>
                    <textarea className="textarea readonly-textarea" readOnly value={post} />
                  </div>
                ))}
              </div>
            ) : (
              <div className="empty-state" style={{ minHeight: 120 }}>
                <strong>No historical posts imported</strong>
                <span>That is okay. Brand OS will learn from content you approve and publish.</span>
              </div>
            )}
          </section>

          <section className="panel settings-card">
            <h2 className="settings-title">Brand Intelligence status</h2>
            <p className="settings-copy">{brand.summary || 'Brand Intelligence is active and ready to shape content.'}</p>
            <div className="learning-flow">
              <div className="flow-step"><BrainCircuit size={15} color="#6d5dfc"/><b>Identity</b><span>{brand.profile?.professional_title || 'LinkedIn profile'}</span></div>
              <div className="flow-step"><Target size={15} color="#6d5dfc"/><b>Audience</b><span>{brand.profile?.audience || 'Derived by Brand Intelligence'}</span></div>
              <div className="flow-step"><Sparkles size={15} color="#6d5dfc"/><b>Voice</b><span>{brand.profile?.tone || 'Learned from content'}</span></div>
              <div className="flow-step"><Activity size={15} color="#6d5dfc"/><b>Memory</b><span>{brand.current_post_count ?? brand.source_post_count} signals · continuous</span></div>
            </div>
          </section>
        </div>
      )}

      <section className="panel settings-card" style={{ marginTop: 16 }}>
        <h2 className="settings-title">LinkedIn connection</h2>
        <p className="settings-copy">Signed in as <b>{profile.display_name}</b>. {linkedin.connected ? 'The official LinkedIn connection is active and is the source of your profile baseline.' : 'Connect LinkedIn to enable supported API actions.'}</p>
        <button className="button" onClick={onConnect}><Link2 size={14}/>{linkedin.connected ? 'Refresh LinkedIn profile' : 'Connect LinkedIn'}</button>
      </section>
    </>
  );
}

function EmptyState({ icon: Icon, title, text, action, onAction }: any) {
  return <div className="empty-state"><div className="empty-icon"><Icon size={19}/></div><strong>{title}</strong><span>{text}</span>{action && <div style={{ marginTop: 14 }}><button className="button primary" onClick={onAction}>{action}<ChevronRight size={13}/></button></div>}</div>;
}

function LinkedInMark({ size = 18, color }: { size?: number; color?: string }) {
  return <svg width={size} height={size} viewBox="0 0 24 24" fill={color || 'currentColor'} aria-hidden="true"><path d="M6.5 8.2H3.2V20h3.3V8.2ZM4.85 3A1.95 1.95 0 1 0 4.85 6.9 1.95 1.95 0 0 0 4.85 3ZM20.8 13.25c0-3.52-1.88-5.16-4.4-5.16-2.02 0-2.92 1.11-3.43 1.89V8.2H9.67V20h3.3v-5.84c0-1.54.29-3.03 2.2-3.03 1.88 0 1.91 1.76 1.91 3.13V20h3.3l.02-6.75Z"/></svg>;
}
