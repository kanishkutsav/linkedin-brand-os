/* Production deployment marker: frontend and FastAPI service ship together. */
'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import ProductionJobsView from '../components/jobs-view';
import {
  Activity, ArrowUpRight, BarChart3, BrainCircuit, Briefcase, Check, ChevronRight, CircleCheck,
  Clock3, Command, Download, ExternalLink, FileText, Gauge, Globe2, LayoutDashboard, Link2,
  LoaderCircle, LogOut, MoreHorizontal, Pencil, Plus, RefreshCw, RotateCcw, Search, Settings,
  ShieldAlert, ShieldCheck, Sparkles, Target, ChevronDown, TrendingUp, UserRound, WandSparkles, MessageSquare, X, Zap
} from 'lucide-react';

const API_BASE = typeof window !== 'undefined' && window.location.hostname === 'localhost' ? (process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000') : '';

function getApiError(data: any, fallback: string) {
  if (typeof data?.detail === 'string') return data.detail;
  if (Array.isArray(data?.detail)) return data.detail.map((item: any) => item?.msg || String(item)).join('; ');
  if (typeof data?.message === 'string') return data.message;
  return fallback;
}

type ApprovalStatus = 'PENDING' | 'EDITED' | 'REGENERATED' | 'APPROVED' | 'PUBLISHING' | 'REJECTED' | 'EXECUTED';
type ApprovalItem = { id: number; status: ApprovalStatus; action_type: string; reason: string | null; content: string; title?: string; topic?: string; approved_at?: string | null; created_at?: string };
type Profile = { display_name: string; role?: string; picture_url?: string | null };
type LinkedInStatus = {
  connected: boolean;
  name?: string | null;
  email?: string | null;
  expires_at?: string | null;
  profile_sync_needed?: boolean;
  missing_profile_fields?: string[];
};
type BrandStatus = {
  ready: boolean; status: string; source_post_count: number; current_post_count?: number;
  continuous_learning?: boolean; historical_import_optional?: boolean; brand_bootstrap_completed?: boolean; last_updated?: string | null;
  summary?: string | null;
  profile?: { display_name?: string; professional_title?: string | null; industry?: string | null; experience_years?: number | null; job_location?: string | null; tone?: string | null };
  linkedin_profile?: { connected?: boolean; headline?: string | null; picture_url?: string | null; locale?: string | null; vanity_name?: string | null };
};
type Opportunity = {
  id: number; title: string; topic: string; angle: string; pillar: string; format?: string; objective?: string;
  total_score: number; scores: Record<string, number>; rationale?: string;
  evidence?: { summary?: string; why_now?: string; source_hints?: string[]; grounding_queries?: string[] };
  source_ids?: number[]; sources?: { title?: string; url?: string; domain?: string }[];
};
type PersonalThought = {
  id: number;
  content: string;
  title?: string | null;
  topic?: string | null;
  status?: string;
  created_at?: string | null;
};
type Tab = 'Dashboard' | 'Research' | 'Content Studio' | 'LinkedIn Posts' | 'Analytics' | 'Brand DNA' | 'Jobs' | 'Feedback' | 'Admin';

type BeforeInstallPromptEvent = Event & {
  prompt: () => Promise<void>;
  userChoice: Promise<{ outcome: 'accepted' | 'dismissed' }>;
};

const nav = [
  ['Dashboard', LayoutDashboard, 'Command center'],
  ['Research', Search, 'Find opportunities'],
  ['Content Studio', FileText, 'Draft & refine'],
  ['Jobs', Briefcase, 'Job opportunities'],
  ['LinkedIn Posts', ExternalLink, 'Published posts'],
  ['Analytics', BarChart3, 'Performance'],
  ['Brand DNA', Settings, 'Brand DNA'],
  ['Admin', ShieldAlert, 'Operations & reliability'],
] as const;

export default function Home() {
  const [token, setToken] = useState<string | null>(null);
  const [authChecking, setAuthChecking] = useState(true);
  const [profile, setProfile] = useState<Profile>({ display_name: '', role: 'owner', picture_url: null });
  const [identityLoading, setIdentityLoading] = useState(true);
  const [linkedinAvatarFailed, setLinkedinAvatarFailed] = useState(false);
  const [linkedin, setLinkedin] = useState<LinkedInStatus>({ connected: false });
  const linkedinSyncAttemptedToken = useRef<string | null>(null);
  const [brand, setBrand] = useState<BrandStatus>({ ready: false, status: 'NOT_INITIALIZED', source_post_count: 0 });
  const [brandStatusLoaded, setBrandStatusLoaded] = useState(false);
  const [brandStatusError, setBrandStatusError] = useState<string | null>(null);
  const [brandTitle, setBrandTitle] = useState('');
  const [brandIndustry, setBrandIndustry] = useState('');
  const [brandExperienceYears, setBrandExperienceYears] = useState<number | ''>('');
  const [brandLocation, setBrandLocation] = useState('');
  const [brandTone, setBrandTone] = useState('');
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
  const [statusFilter, setStatusFilter] = useState<'PENDING' | 'NEEDS_REVIEW' | 'EXECUTED' | 'REJECTED'>('PENDING');
  const initialReviewFilterResolved = useRef(false);
  const [searchTerm, setSearchTerm] = useState('');
  const [editedBody, setEditedBody] = useState('');
  const [reviewNote, setReviewNote] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [noticeTtl, setNoticeTtl] = useState(4500);
  const [isBusy, setIsBusy] = useState(false);
  const [busyAction, setBusyAction] = useState<'approve' | 'edit' | 'reject' | 'regenerate' | 'execute' | null>(null);
  const [operationProgress, setOperationProgress] = useState(0);
  const [operationStage, setOperationStage] = useState('');
  const initialTab = (() => {
    if (typeof window === 'undefined') return 'Dashboard' as Tab;
    const candidate = new URLSearchParams(window.location.search).get('tab') as Tab | null;
    const validTabs: Tab[] = ['Dashboard', 'Research', 'Content Studio', 'LinkedIn Posts', 'Analytics', 'Brand DNA', 'Jobs', 'Feedback', 'Admin'];
    return candidate && validTabs.includes(candidate) ? candidate : 'Dashboard';
  })();
  const [tab, setTab] = useState<Tab>(initialTab);
  const [draftTitle, setDraftTitle] = useState('');
  const [draftTopic, setDraftTopic] = useState('');
  const [draftBody, setDraftBody] = useState('');
  const [isGenerating, setIsGenerating] = useState(false);
  const [generationProgress, setGenerationProgress] = useState(0);
  const [generationStage, setGenerationStage] = useState('');
  const [opportunities, setOpportunities] = useState<Opportunity[]>([]);
  const [researchFocus, setResearchFocus] = useState('');
  const [isResearching, setIsResearching] = useState(false);
  const [researchProgress, setResearchProgress] = useState(0);
  const [researchStage, setResearchStage] = useState('');
  const [moreOpen, setMoreOpen] = useState(false);
  const [profileMenuOpen, setProfileMenuOpen] = useState(false);
  const researchLoadedRef = useRef(false);
  const analyticsLoadedRef = useRef(false);
  const learningLoadedRef = useRef(false);
  const dashboardDataLoadedRef = useRef(false);
  const [installPrompt, setInstallPrompt] = useState<BeforeInstallPromptEvent | null>(null);
  const [isStandalone, setIsStandalone] = useState(false);
  const [showIosInstallGuide, setShowIosInstallGuide] = useState(false);
  const [loading, setLoading] = useState(false);
  const [brandLoading, setBrandLoading] = useState(false);
  const [researchLoading, setResearchLoading] = useState(false);
  const [analyticsLoading, setAnalyticsLoading] = useState(false);
  const [learningLoading, setLearningLoading] = useState(false);
  const [learningStatus, setLearningStatus] = useState({ pending_events: 0, memory_count: 0 });
  const [personalThoughts, setPersonalThoughts] = useState<PersonalThought[]>([]);
  const [dashboardCounts, setDashboardCounts] = useState({
    total: 0, awaiting_approval: 0, approved: 0, published: 0,
    needs_review: 0, rejected: 0, pending_filter: 0,
  });
  const [savingThought, setSavingThought] = useState(false);
  const [expandedThoughtId, setExpandedThoughtId] = useState<number | null>(null);
  const [selectedThoughtIds, setSelectedThoughtIds] = useState<number[]>([]);
  const [thoughtSelectionMode, setThoughtSelectionMode] = useState(false);
  const [jobs, setJobs] = useState<any[]>([]); const [jobProviders, setJobProviders] = useState<any[]>([]); const [jobLocation, setJobLocation] = useState<any>(null); const [jobQuery, setJobQuery] = useState(''); const [jobExperience, setJobExperience] = useState<number | ''>(''); const [jobPage, setJobPage] = useState(1); const [jobHasMore, setJobHasMore] = useState(false); const [jobsLoading, setJobsLoading] = useState(false); const [expandedJobId, setExpandedJobId] = useState<string | null>(null);
  const [feedbackType, setFeedbackType] = useState('FEATURE'); const [feedbackSubject, setFeedbackSubject] = useState(''); const [feedbackDescription, setFeedbackDescription] = useState(''); const [feedbackContext, setFeedbackContext] = useState(''); const [feedbackSending, setFeedbackSending] = useState(false);
  const [adminOverview, setAdminOverview] = useState<any>(null);
  const [adminActivity, setAdminActivity] = useState<any[]>([]);
  const [adminFeedback, setAdminFeedback] = useState<any[]>([]);
  const [adminUsers, setAdminUsers] = useState<any[]>([]);
  const [adminAiProviders, setAdminAiProviders] = useState<any>(null);
  const [adminJobProviders, setAdminJobProviders] = useState<any>(null);
  const [adminSections, setAdminSections] = useState<Record<string, boolean>>({});
  const [adminSectionLoading, setAdminSectionLoading] = useState<Record<string, boolean>>({});

  const headers = (authToken = token) => (authToken && authToken !== 'cookie') ? { Authorization: `Bearer ${authToken}` } : {};

  const readCookie = (name: string) => document.cookie.split('; ').find((part) => part.startsWith(name + '='))?.slice(name.length + 1) || '';
  const apiFetch = (input: RequestInfo | URL, init: RequestInit = {}) => {
    const requestHeaders = new Headers(init.headers || {});
    const method = String(init.method || 'GET').toUpperCase();
    if (!['GET', 'HEAD', 'OPTIONS'].includes(method)) {
      const csrf = readCookie('__Host-suvacya-csrf') || readCookie('suvacya-csrf');
      if (csrf) requestHeaders.set('X-CSRF-Token', csrf);
    }
    return fetch(input, { ...init, headers: requestHeaders, credentials: 'include' });
  };

  useEffect(() => {
    if (!profileMenuOpen) return;
    const handlePointerDown = (event: PointerEvent) => {
      const target = event.target as Node | null;
      if (target && !document.querySelector('.profile-menu-wrap')?.contains(target)) {
        setProfileMenuOpen(false);
      }
    };
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setProfileMenuOpen(false);
    };
    document.addEventListener('pointerdown', handlePointerDown);
    document.addEventListener('keydown', handleKeyDown);
    return () => {
      document.removeEventListener('pointerdown', handlePointerDown);
      document.removeEventListener('keydown', handleKeyDown);
    };
  }, [profileMenuOpen]);

  useEffect(() => {
    const standalone = window.matchMedia('(display-mode: standalone)').matches || (window.navigator as any).standalone === true;
    setIsStandalone(standalone);

    const handleBeforeInstallPrompt = (event: Event) => {
      event.preventDefault();
      setInstallPrompt(event as BeforeInstallPromptEvent);
    };
    const handleAppInstalled = () => {
      setInstallPrompt(null);
      setIsStandalone(true);
      setMoreOpen(false);
      setNotice('Suvacya was added to your device.');
    };

    window.addEventListener('beforeinstallprompt', handleBeforeInstallPrompt);
    window.addEventListener('appinstalled', handleAppInstalled);
    if ('serviceWorker' in navigator) {
      navigator.serviceWorker.register('/sw.js').catch(() => undefined);
    }

    return () => {
      window.removeEventListener('beforeinstallprompt', handleBeforeInstallPrompt);
      window.removeEventListener('appinstalled', handleAppInstalled);
    };
  }, []);

  useEffect(() => {
    if (!notice) return;
    const timer = window.setTimeout(() => setNotice(null), noticeTtl);
    return () => window.clearTimeout(timer);
  }, [notice, noticeTtl]);

  useEffect(() => {
    if (!error) return;
    const timer = window.setTimeout(() => setError(null), 3000);
    return () => window.clearTimeout(timer);
  }, [error]);

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
    const oauthNonce = params.get('oauth_nonce');
    if (code) {
      const expectedNonce = window.sessionStorage.getItem('brand-os-oauth-nonce');
      window.history.replaceState({}, document.title, window.location.pathname);
      if (!expectedNonce || !oauthNonce || expectedNonce !== oauthNonce) {
        window.sessionStorage.removeItem('brand-os-oauth-nonce');
        setError('LinkedIn sign-in could not be verified in this browser. Please start the connection again.');
        setAuthChecking(false);
        return;
      }
      window.sessionStorage.removeItem('brand-os-oauth-started-at');
      apiFetch(`${API_BASE}/api/auth/linkedin/exchange`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ code, oauth_nonce: oauthNonce }),
      }).then(async (res) => {
        const data = await res.json();
        if (!res.ok) throw new Error(getApiError(data, 'LinkedIn connection failed'));
        window.sessionStorage.removeItem('brand-os-oauth-nonce');
        window.sessionStorage.removeItem('brand-os-oauth-started-at');
        setToken('cookie');
        setNotice('LinkedIn account connected successfully.');
      }).catch((e) => {
        window.sessionStorage.removeItem('brand-os-oauth-nonce');
        setError(e instanceof Error ? e.message : 'LinkedIn connection failed');
      }).finally(() => setAuthChecking(false));
      return;
    }
    apiFetch(API_BASE + '/api/auth/me')
      .then((res) => { if (res.ok) setToken('cookie'); })
      .catch(() => undefined)
      .finally(() => setAuthChecking(false));
  }, []);

  const fetchData = async (authToken: string | null = token) => {
    if (!authToken) return;
    setLoading(true);
    setBrandLoading(true);
    setBrandStatusLoaded(false);
    setBrandStatusError(null);
    try {
      const profilePromise = apiFetch(`${API_BASE}/api/auth/me`, { headers: headers(authToken) });
      const approvalsPromise = apiFetch(`${API_BASE}/api/dashboard/approvals`, { headers: headers(authToken) });
      const linkedinPromise = apiFetch(`${API_BASE}/api/linkedin/status`, { headers: headers(authToken) });
      const brandPromise = apiFetch(`${API_BASE}/api/brand/status`, { headers: headers(authToken) });

      const [profileSettled, approvalsSettled] = await Promise.allSettled([profilePromise, approvalsPromise]);
      if (profileSettled.status !== 'fulfilled') {
        throw new Error('Unable to verify your session. Please refresh and try again.');
      }
      const profileRes = profileSettled.value;
      if (profileRes.status === 401) {
        setToken(null);
        setQueue([]);
        setLinkedin({ connected: false });
        throw new Error('Your session expired. Please sign in with LinkedIn again.');
      }
      if (!profileRes.ok) throw new Error('Unable to load your account. Please refresh and try again.');

      const profileJson = await profileRes.json();
      let approvalsJson: any = { pending_approvals: [], counts: {} };
      if (approvalsSettled.status === 'fulfilled') {
        const approvalsRes = approvalsSettled.value;
        if (approvalsRes.status === 401) {
          setToken(null);
          setQueue([]);
          setLinkedin({ connected: false });
          throw new Error('Your session expired. Please sign in with LinkedIn again.');
        }
        if (approvalsRes.ok) {
          approvalsJson = await approvalsRes.json();
        } else {
          setNotice('Dashboard activity is temporarily unavailable. Your account is still loaded.');
        }
      } else {
        setNotice('Dashboard activity is temporarily unavailable. Your account is still loaded.');
      }
      setProfile({
        display_name: profileJson.display_name || profileJson.name || '',
        role: profileJson.role || 'owner',
        picture_url: profileJson.picture_url || profileJson.avatar_url || null,
      });
      setIdentityLoading(false);
      if (profileJson.role === 'admin' && new URLSearchParams(window.location.search).get('admin') === '1') setTab('Admin');
      if (profileJson.role !== 'admin' && tab === 'Admin') {
        setTab('Dashboard');
        const url = new URL(window.location.href);
        url.searchParams.delete('tab');
        window.history.replaceState({}, document.title, url.toString());
      }

      const nextQueue: ApprovalItem[] = (approvalsJson.pending_approvals || []).map((item: any) => ({
        id: item.id, status: item.status, action_type: item.action_type, reason: item.reason, content: item.content || '',
        title: item.title || '', topic: item.topic || '', approved_at: item.approved_at || null, created_at: item.created_at,
      }));
      setQueue(nextQueue);
      dashboardDataLoadedRef.current = true;
      const pendingFilterCount = Number(approvalsJson.counts?.pending_filter ?? 0);
      const needsReviewCount = Number(approvalsJson.counts?.needs_review ?? 0);
      setDashboardCounts({
        total: Number(approvalsJson.counts?.total ?? 0),
        awaiting_approval: Number(approvalsJson.counts?.awaiting_approval ?? 0),
        approved: Number(approvalsJson.counts?.approved ?? 0),
        published: Number(approvalsJson.counts?.published ?? 0),
        needs_review: needsReviewCount,
        rejected: Number(approvalsJson.counts?.rejected ?? 0),
        pending_filter: pendingFilterCount,
      });

      if (!initialReviewFilterResolved.current) {
        setStatusFilter(pendingFilterCount > 0 ? 'PENDING' : needsReviewCount > 0 ? 'NEEDS_REVIEW' : 'PENDING');
        initialReviewFilterResolved.current = true;
      }
      if (nextQueue.length && !nextQueue.some((i) => i.id === selectedId)) setSelectedId(nextQueue[0].id);

      setLoading(false);

      void Promise.allSettled([linkedinPromise, brandPromise]).then(async ([linkedinResult, brandResult]) => {
        const linkedinJson = linkedinResult.status === 'fulfilled' && linkedinResult.value.ok
          ? await linkedinResult.value.json()
          : null;
        if (linkedinJson) setLinkedin(linkedinJson);

        if (brandResult.status !== 'fulfilled' || !brandResult.value.ok) {
          setBrandStatusError('Brand DNA status is temporarily unavailable. Your saved Brand DNA has not been changed.');
          setBrandStatusLoaded(true);
          return;
        }

        const brandJson = await brandResult.value.json();
        setBrand(brandJson);
        setBrandStatusError(null);
        setBrandStatusLoaded(true);
        const resolvedPicture = linkedinJson?.picture_url || brandJson.linkedin_profile?.picture_url || null;
        if (resolvedPicture) {
          setProfile((current) => ({ ...current, picture_url: current.picture_url || resolvedPicture }));
        }

        if (
          linkedinJson.connected &&
          linkedinJson.profile_sync_needed &&
          linkedinSyncAttemptedToken.current !== authToken
        ) {
          linkedinSyncAttemptedToken.current = authToken;
          void apiFetch(`${API_BASE}/api/linkedin/profile/sync-missing`, {
            method: 'POST',
            headers: headers(authToken),
          }).then(async (syncRes) => {
            if (!syncRes.ok) return;
            const syncJson = await syncRes.json();
            if (!syncJson.updated || !syncJson.profile) return;
            setBrand((current) => ({
              ...current,
              linkedin_profile: {
                ...(current.linkedin_profile || {}),
                ...syncJson.profile,
                connected: true,
              },
            }));
          }).catch(() => undefined);
        }

        const p = brandJson.profile || {};
        setBrandTitle(p.professional_title || '');
        setBrandIndustry(p.industry || '');
        setBrandExperienceYears(typeof p.experience_years === 'number' ? Math.round(p.experience_years) : '');
        setBrandLocation(p.job_location || '');
        setBrandTone(p.tone || '');

        const sourcePosts = (brandJson.source_posts || [])
          .map((item: any) => item.body)
          .filter((body: any) => typeof body === 'string' && body.trim());
        setHistoricalPostEntries(sourcePosts.slice(0, 10));

        if (linkedinJson.connected && brandJson.brand_bootstrap_completed === false) {
          void apiFetch(`${API_BASE}/api/brand/bootstrap`, {
            method: 'POST',
            headers: headers(authToken),
          }).then(async (bootstrapRes) => {
            if (!bootstrapRes.ok) return;
            const bootstrapJson = await bootstrapRes.json();
            const bootstrapProfile = bootstrapJson.profile || {};
            if (bootstrapProfile.professional_title !== undefined) setBrandTitle(bootstrapProfile.professional_title || '');
            if (bootstrapProfile.industry !== undefined) setBrandIndustry(bootstrapProfile.industry || '');
            if (bootstrapProfile.experience_years !== undefined) setBrandExperienceYears(typeof bootstrapProfile.experience_years === 'number' ? Math.round(bootstrapProfile.experience_years) : '');
            if (bootstrapProfile.job_location !== undefined) setBrandLocation(bootstrapProfile.job_location || '');
            if (bootstrapProfile.tone !== undefined) setBrandTone(bootstrapProfile.tone || '');
            if (bootstrapJson.brand_memory) setBrand({ ...bootstrapJson.brand_memory, ready: bootstrapJson.ready === true });
          }).catch(() => undefined);
        }
      }).catch(() => {
        setBrandStatusError('Brand DNA status is temporarily unavailable. Your saved Brand DNA has not been changed.');
        setBrandStatusLoaded(true);
        // Supplemental identity/Brand DNA data is non-blocking.
      }).finally(() => {
        setBrandLoading(false);
      });
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Unable to load dashboard data');
      setLoading(false);
      setBrandLoading(false);
    }
  };

  const loadResearchData = async (force = false) => {
    if (!token || (researchLoadedRef.current && !force)) return;
    setResearchLoading(true);
    try {
      const response = await apiFetch(`${API_BASE}/api/research/opportunities`, { headers: headers() });
      if (!response.ok) throw new Error('Failed to load. Please try again.');
      const data = await response.json();
      setOpportunities(data.opportunities || []);
      researchLoadedRef.current = true;
    } catch (e) {
      setError('Failed to load. Please try again.');
    } finally {
      setResearchLoading(false);
    }
  };

  const loadAnalyticsData = async (force = false) => {
    if (!token || (analyticsLoadedRef.current && !force)) return;
    setAnalyticsLoading(true);
    try {
      const response = await apiFetch(`${API_BASE}/api/analytics/overview`, { headers: headers() });
      if (!response.ok) throw new Error('Analytics data could not be loaded.');
      setAnalytics(await response.json());
      analyticsLoadedRef.current = true;
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Analytics data could not be loaded.');
    } finally {
      setAnalyticsLoading(false);
    }
  };

  const loadLearningData = async (force = false) => {
    if (!token || (learningLoadedRef.current && !force)) return;
    setLearningLoading(true);
    try {
      const [learningRes, thoughtsRes] = await Promise.all([
        apiFetch(`${API_BASE}/api/learning/status`, { headers: headers() }),
        apiFetch(`${API_BASE}/api/learning/thoughts`, { headers: headers() }),
      ]);
      if (learningRes.ok) setLearningStatus(await learningRes.json());
      if (thoughtsRes.ok) {
        const thoughtsJson = await thoughtsRes.json();
        setPersonalThoughts(thoughtsJson.thoughts || []);
      }
      if (!learningRes.ok && !thoughtsRes.ok) throw new Error('Learning data could not be loaded.');
      learningLoadedRef.current = true;
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Learning data could not be loaded.');
    } finally {
      setLearningLoading(false);
    }
  };

  useEffect(() => {
    if (!token) return;
    // Load section data on demand. The previous broad background prefetch
    // fired Research, Analytics and Learning together from the Dashboard,
    // multiplying API/database work and contributing to connection pressure.
    if (tab === 'Research') void loadResearchData();
    if (tab === 'Analytics') void loadAnalyticsData();
    if (tab === 'Content Studio' || tab === 'Brand DNA') void loadLearningData();
  }, [tab, token]);

  const persistTab = (next: Tab) => {
    const url = new URL(window.location.href);
    if (next === 'Dashboard') url.searchParams.delete('tab');
    else url.searchParams.set('tab', next);
    window.history.replaceState({}, document.title, url.toString());
  };

  useEffect(() => { fetchData(token); }, [token]);
  const loadJobs = async (params?: { jobTitle?: string; location?: string; experience?: number | ''; page?: number; append?: boolean }) => {
    if (!token) return;
    const append = Boolean(params?.append);
    const page = params?.page || 1;
    setJobsLoading(true);
    try {
      const body = params?.jobTitle?.trim()
        ? { mode: 'manual', job_title: params.jobTitle.trim(), location: (params.location || '').trim(), experience: params.experience === '' || params.experience == null ? null : Number(params.experience), page, limit: 20 }
        : { mode: 'recommended', page, limit: 20 };
      const res = await apiFetch(API_BASE + '/api/jobs/search', { method: 'POST', headers: { ...headers(), 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
      const data = await res.json();
      if (!res.ok) throw new Error(getApiError(data, 'Job search is temporarily unavailable.'));
      setJobs((current) => append ? [...current, ...(data.jobs || [])] : (data.jobs || []));
      setJobProviders(data.providers || []);
      setJobLocation(data.location || null);
      setJobQuery(data.query || params?.jobTitle || '');
      setJobExperience(data.experience ?? params?.experience ?? '');
      setJobPage(data.page || page);
      setJobHasMore(Boolean(data.has_more));
      setExpandedJobId(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Job search is temporarily unavailable.');
    } finally { setJobsLoading(false); }
  };
  const loadAdminOverview = async () => {
    if (!token || profile.role !== 'admin') return;
    try {
      const response = await apiFetch(API_BASE + '/api/admin/overview', { headers: headers() });
      if (response.ok) setAdminOverview(await response.json());
      else throw new Error('Admin overview could not be loaded.');
    } catch (e) { setError(e instanceof Error ? e.message : 'Admin overview could not be loaded.'); }
  };
  const loadAdminSection = async (section: string, force = false) => {
    if (!token || profile.role !== 'admin') return;
    if (!force && adminSectionLoading[section]) return;
    if (!force && ((section === 'failures' && adminActivity.length) || (section === 'feedback' && adminFeedback.length) || (section === 'users' && adminUsers.length) || (section === 'ai-providers' && adminAiProviders) || (section === 'job-providers' && adminJobProviders))) return;
    const paths: Record<string, string> = { failures: '/api/admin/failures', feedback: '/api/admin/feedback', users: '/api/admin/users', 'ai-providers': '/api/admin/ai-providers', 'job-providers': '/api/admin/job-providers' };
    const path = paths[section]; if (!path) return;
    setAdminSectionLoading((prev) => ({ ...prev, [section]: true }));
    try {
      const response = await apiFetch(API_BASE + path, { headers: headers() });
      if (!response.ok) throw new Error('Admin section could not be loaded.');
      const data = await response.json();
      if (section === 'failures') setAdminActivity(data.items || []);
      if (section === 'feedback') setAdminFeedback(data.items || []);
      if (section === 'users') setAdminUsers(data.items || []);
      if (section === 'ai-providers') setAdminAiProviders(data);
      if (section === 'job-providers') setAdminJobProviders(data);
    } catch (e) { setError(e instanceof Error ? e.message : 'Admin section could not be loaded.'); }
    finally { setAdminSectionLoading((prev) => ({ ...prev, [section]: false })); }
  };
  const toggleAdminSection = (section: string) => {
    const nextOpen = !adminSections[section];
    setAdminSections((prev) => ({ ...prev, [section]: nextOpen }));
    if (nextOpen) void loadAdminSection(section);
  };
  const refreshAdmin = async () => {
    await loadAdminOverview();
    await Promise.all(Object.entries(adminSections).filter(([, open]) => open).map(([section]) => loadAdminSection(section, true)));
  };
  useEffect(() => { if (tab === 'Jobs' && token && !jobs.length) void loadJobs(); if (tab === 'Admin' && token && profile.role === 'admin') void loadAdminOverview(); }, [tab, token, profile.role]);
  useEffect(() => {
    const selected = queue.find((item) => item.id === selectedId);
    if (!selected) return;
    setEditedBody(selected.content || '');
    const savedFeedback = window.localStorage.getItem(`brand-os-regeneration-feedback:${selected.id}`);
    setReviewNote(savedFeedback || '');
  }, [selectedId, queue]);

  const filteredQueue = useMemo(() => {
    const query = searchTerm.trim().toLowerCase();
    return queue.filter((item) => {
      const normalizedStatus = String(item.status || '').trim().toUpperCase();
      const statusMatch = statusFilter === 'PENDING'
        ? ['PENDING', 'APPROVED', 'PUBLISHING'].includes(normalizedStatus)
        : statusFilter === 'NEEDS_REVIEW'
          ? ['EDITED', 'REGENERATED'].includes(normalizedStatus)
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
  const summary = {
    pending: dashboardCounts.awaiting_approval,
    reviewed: dashboardCounts.approved,
    rejected: dashboardCounts.rejected,
    executed: dashboardCounts.published,
  };

  const initials = (profile.display_name || 'User').trim().split(/\s+/).map((x) => x[0]).slice(0, 2).join('').toUpperCase();
  const linkedinAvatarUrl = profile.picture_url || brand.linkedin_profile?.picture_url || null;
  useEffect(() => { setLinkedinAvatarFailed(false); }, [linkedinAvatarUrl]);
  const closeMore = () => setMoreOpen(false);
  const isIosDevice = () => /iphone|ipad|ipod/i.test(window.navigator.userAgent) || (window.navigator.platform === 'MacIntel' && window.navigator.maxTouchPoints > 1);
  const installSuvacya = async () => {
    if (isStandalone) return;
    if (installPrompt) {
      const prompt = installPrompt;
      setInstallPrompt(null);
      await prompt.prompt();
      const choice = await prompt.userChoice;
      if (choice.outcome === 'accepted') setNotice('Installing Suvacya…');
      return;
    }
    if (isIosDevice()) {
      setMoreOpen(false);
      setShowIosInstallGuide(true);
      return;
    }
    setNotice('Use your browser menu to install Suvacya or add it to your home screen.');
  };
  const connectLinkedIn = () => {
    // OAuth attempts are independent. If a user cancels or abandons LinkedIn,
    // the next click must start a fresh transaction instead of being blocked
    // by stale browser state from the previous attempt.
    const nonce = window.crypto?.randomUUID?.() || (Date.now().toString(36) + '-' + Math.random().toString(36).slice(2));
    window.sessionStorage.setItem('brand-os-oauth-nonce', nonce);
    window.sessionStorage.setItem('brand-os-oauth-started-at', String(Date.now()));
    setError(null);
    window.location.href = '/api/auth/linkedin/start?browser_nonce=' + encodeURIComponent(nonce);
  };
  const cancelBrandEdit = async () => { await fetchData(); setBrandEditing(false); };
  const deleteAccount = async () => {
    const confirmation = window.prompt('This permanently deletes your Suvacya account and application data. Type DELETE to confirm.');
    if (confirmation !== 'DELETE') return;
    try {
      const csrf = readCookie('__Host-suvacya-csrf') || readCookie('suvacya-csrf');
      const res = await apiFetch(API_BASE + '/api/account', {
        method: 'DELETE',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json', ...(csrf ? { 'X-CSRF-Token': csrf } : {}) },
        body: JSON.stringify({ confirmation }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(getApiError(data, 'Account deletion failed'));
      window.location.href = '/';
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Account deletion failed');
    }
  };

  const logout = async () => {
    try {
      if (token) {
        await apiFetch(API_BASE + '/api/auth/logout', { method: 'POST', headers: headers(token) });
      }
    } finally {
      setToken(null); setQueue([]); setLinkedin({ connected: false });
    }
  };
  const go = (next: Tab) => {
    setMoreOpen(false);
    // A failed/unfinished Brand DNA status request must never be interpreted as
    // "not initialized". The backend remains the authority for protected actions.
    if (brandStatusLoaded && !brandStatusError && !brand.ready && next !== 'Brand DNA') {
      setTab('Brand DNA');
      persistTab('Brand DNA');
      setNotice('Before using the workspace, complete your Brand DNA setup once.');
      window.scrollTo({ top: 0, behavior: 'smooth' });
      return;
    }
    setTab(next);
    persistTab(next);
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  const requireBrand = (actionLabel: string) => {
    if (brand.ready || brandStatusError || !brandStatusLoaded) return true;
    go('Brand DNA');
    setError('Brand DNA is not set up yet. Before ' + actionLabel + ', complete the suggested Brand DNA details. Previous LinkedIn posts are optional and can be added later to improve voice calibration.');
    return false;
  };

  const runApprovalAction = async (action: 'approve' | 'edit' | 'reject' | 'regenerate' | 'execute', payload?: Record<string, string> | File | null) => {
    if (!selectedApproval || !token) return;
    if (action === 'regenerate' && !requireBrand('regenerating content')) return;
    if (action === 'regenerate' && !reviewNote.trim()) {
      setError('Add feedback for the regeneration first. The Regenerate button will stay disabled until you do.');
      return;
    }
    setIsBusy(true); setBusyAction(action); setError(null); setNotice(null);
    if (action === 'approve') {
      setOperationProgress(20);
      setOperationStage('Locking the approved version…');
    } else if (action === 'execute') {
      setOperationProgress(20);
      setOperationStage('Preparing LinkedIn publication…');
    }
    try {
      const isExecute = action === 'execute';
      const requestInit: RequestInit = {
        method: 'POST',
        headers: isExecute ? headers() : { ...headers(), 'Content-Type': 'application/json' },
        body: isExecute
          ? (() => {
              const form = new FormData();
              if (payload instanceof File) form.append('image', payload);
              return form;
            })()
          : JSON.stringify(payload || {}),
      };
      const res = await apiFetch(`${API_BASE}/api/approvals/${selectedApproval.id}/${action}`, requestInit);
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(getApiError(data, `Action failed: ${action}`));
      if (action === 'execute' && data.published === false) {
        throw new Error(data.message || 'Execution was not completed.');
      }
      if (action === 'regenerate') {
        window.localStorage.removeItem(`brand-os-regeneration-feedback:${selectedApproval.id}`);
        setReviewNote('');
      }
      if (action === 'approve') {
        window.localStorage.removeItem(`brand-os-regeneration-feedback:${selectedApproval.id}`);
        setReviewNote('');
        setStatusFilter('PENDING');
      }
      if (action === 'execute') setStatusFilter('EXECUTED');
      setOperationProgress(action === 'approve' || action === 'execute' ? 82 : 88);
      setOperationStage(action === 'regenerate' ? 'Refreshing the approval queue…' : 'Refreshing the workspace…');
      await fetchData();
      setOperationProgress(100);
      setOperationStage('Done');
      setNoticeTtl(action === 'regenerate' ? 1800 : 4500);
      setNotice(
        action === 'regenerate'
          ? 'Regenerated successfully.'
          : action === 'approve'
            ? 'Approved. The post is now locked and ready to execute.'
            : action === 'execute'
              ? 'Published to LinkedIn successfully.'
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
      const res = await apiFetch(API_BASE + '/api/agent/events', {
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
            : data.duplicate_blocked
              ? 'The generated draft matched content already in your brand memory, so it was not added to the approval queue.'
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
      const res = await apiFetch(API_BASE + '/api/research/discover', {
        method: 'POST', headers: { ...headers(), 'Content-Type': 'application/json' }, body: JSON.stringify({ topic: researchFocus.trim() || null }),
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
      // Never expose provider/source configuration or infrastructure details to end users.
      setError('Failed to load. Please try again.');
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
    const title = brandTitle.trim();
    const industry = brandIndustry.trim();
    const tone = brandTone.trim();
    const experience = typeof brandExperienceYears === 'number' ? brandExperienceYears : null;

    if (!title || !industry || !tone) {
      setError('Professional title, industry and desired tone are required. Years of experience and previous posts are optional.');
      return;
    }
    if (typeof experience === 'number' && (!Number.isFinite(experience) || experience < 0)) {
      setError('Years of experience must be a valid non-negative number.');
      return;
    }

    setIsBuildingBrand(true); setError(null); setNoticeTtl(4500); setNotice(null);
    try {
      const endpoint = '/api/brand/onboard';
      const body = {
        display_name: profile.display_name,
        professional_title: title,
        industry,
        tone,
        experience_years: typeof experience === 'number' ? Math.round(experience) : null,
        job_location: brandLocation.trim() || null,
        posts: blocks.map((body) => ({ body })),
      };

      const res = await apiFetch(API_BASE + endpoint, {
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
          ? 'Brand Intelligence updated using your saved Brand DNA details and ' + blocks.length + ' imported posts.'
          : 'Brand Intelligence updated. You can add previous LinkedIn posts later to strengthen voice calibration.'
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
    if (!token || !draftBody.trim()) { setError('Write a draft first, then ask Suvacya to polish it.'); return; }
    if (!requireBrand('polishing content')) return;
    setIsImproving(true); setError(null); setNoticeTtl(4500); setNotice(null);
    try {
      const res = await apiFetch(API_BASE + '/api/content/improve', {
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

  const saveThought = async () => {
    if (!token || !draftBody.trim()) {
      setError('Write something first so Suvacya has a useful thought to learn from.');
      return;
    }
    if (!requireBrand('saving a personal thought')) return;
    setSavingThought(true); setError(null); setNotice(null);
    try {
      const res = await apiFetch(API_BASE + '/api/learning/thought', {
        method: 'POST',
        headers: { ...headers(), 'Content-Type': 'application/json' },
        body: JSON.stringify({ content: draftBody, topic: draftTopic, title: draftTitle }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(getApiError(data, 'Could not save this thought'));
      setNotice('Personal thought saved. Suvacya will use it as a learning signal for future research and content.');
      const thoughtsRes = await apiFetch(API_BASE + '/api/learning/thoughts', { headers: headers() });
      if (thoughtsRes.ok) {
        const thoughtsJson = await thoughtsRes.json();
        setPersonalThoughts(thoughtsJson.thoughts || []);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not save this thought');
    } finally {
      setSavingThought(false);
    }
  };

  const createDraft = async () => {
    if (!token || !draftTitle.trim() || !draftTopic.trim() || !draftBody.trim()) {
      setError('Title, topic and draft body are required.'); return;
    }
    if (!requireBrand('sending content to approval')) return;
    setIsBusy(true); setError(null); setNoticeTtl(4500); setNotice(null);
    try {
      const res = await apiFetch(`${API_BASE}/api/content/drafts`, {
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

  const authLoadingMessage = 'Loading your workspace…';

  if (authChecking) return <div style={{ minHeight: '100vh', background: '#f5f8fc' }}><WorkspaceLoading message={authLoadingMessage} /></div>;
  if (!token) return <LoginScreen error={error} onConnect={connectLinkedIn} />;

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand-lockup">
          <div className="brand-mark"><Sparkles size={18} /></div>
          <div><div className="brand-name">Suvacya</div><div className="brand-sub">Personal Brand Manager</div></div>
        </div>
        <div className="nav-label">Workspace</div>
        {nav.filter(([label]) => label !== 'Admin' || profile.role === 'admin').map(([label, Icon, sub]) => (
          <button key={label} className={`nav-item ${tab === label ? 'active' : ''}`} onClick={() => go(label as Tab)}>
            <Icon size={16} /><span>{label}</span>{label === 'Dashboard' && summary.pending > 0 ? <em>{summary.pending}</em> : <ChevronRight size={13} opacity={.35} />}
          </button>
        ))}
        <div className="sidebar-spacer" />
        <div className="connection-card">
          <div className="connection-row"><ShieldCheck size={15} color="#4c8fef" /><span className="connection-title">Human approval gate</span></div>
          <div className="connection-meta">No external LinkedIn action is executed without your explicit approval.</div>
        </div>
        <button className="side-button" onClick={logout}><LogOut size={14} /> Sign out <span style={{ marginLeft: 'auto' }}>⌘Q</span></button>
        <div className="brand-footer">Suvacya · by Kanishka</div>
      </aside>

      <div className="main-shell">
        <header className="topbar">
          <div className="topbar-left">
            <div><div className="eyebrow">Workspace / {tab}</div><div className="topbar-title">{tab === 'Dashboard' ? 'Command center' : nav.find((x) => x[0] === tab)?.[2] || (tab === 'Feedback' ? 'Share feedback' : '')}</div></div>
          </div>
          <div className="topbar-actions">
            <div className="profile-menu-wrap">
              <button className="avatar profile-trigger" title="Account menu" onClick={() => setProfileMenuOpen((v) => !v)} aria-expanded={profileMenuOpen}>
                {identityLoading ? <span className="avatar-loading" aria-label="Loading profile" /> : linkedinAvatarUrl && !linkedinAvatarFailed ? <img src={linkedinAvatarUrl} alt={profile.display_name ? profile.display_name + ' profile' : 'Profile'} onError={() => setLinkedinAvatarFailed(true)} referrerPolicy="no-referrer" /> : initials}
              </button>
              {profileMenuOpen && <div className="profile-menu">
                <div className="profile-menu-head"><strong>{profile.display_name || 'Profile'}</strong><span>{profile.role || 'user'}</span></div>
                <button onClick={() => { setProfileMenuOpen(false); connectLinkedIn(); }}><Link2 size={14}/> {linkedin.connected ? 'Reconnect LinkedIn' : 'Connect LinkedIn'}</button>
                <button onClick={() => { setProfileMenuOpen(false); void fetchData(); }}><RefreshCw size={14}/> Refresh dashboard</button>
                <button onClick={() => { setProfileMenuOpen(false); go('Feedback'); }}><MessageSquare size={14}/> Send feedback</button>
                <a href="/privacy" onClick={() => setProfileMenuOpen(false)}><ShieldCheck size={14}/> Privacy Policy</a>
                <a href="/terms" onClick={() => setProfileMenuOpen(false)}><FileText size={14}/> Terms</a>
                <button className="danger" onClick={() => { setProfileMenuOpen(false); void deleteAccount(); }}><X size={14}/> Delete account</button>
              </div>}
            </div>
          </div>
        </header>

        <main className="page">
          {notice && <div className="notice success"><CircleCheck size={15} /><span>{notice}</span></div>}
          {error && <div className="notice error"><X size={15} /><span>{error}</span></div>}
          {tab === 'Dashboard' && (
            loading && !dashboardDataLoadedRef.current ? <DashboardSkeleton /> : <>
              {brandLoading ? <DashboardHeroSkeleton /> : <section className="hero" onClick={!brand.ready ? () => go('Brand DNA') : undefined} style={!brand.ready ? { cursor: 'pointer' } : undefined}>
                <div className="hero-grid">
                  <div>
                    <div className="page-kicker" style={{ color: '#b9d7f7' }}>
                      {brand.ready ? <><Sparkles size={13} /> Brand intelligence active</> : <><BrainCircuit size={13} /> Brand DNA setup required</>}
                    </div>
                    <h1>{brand.ready ? 'Turn your expertise into a recognizable point of view.' : 'Start by teaching Suvacya your voice.'}</h1>
                    <p>{brand.ready
                      ? 'Research, content strategy, drafting and review — orchestrated around your brand voice, with you always in control of what reaches LinkedIn.'
                      : 'Review the Brand DNA we prefilled from LinkedIn. Previous posts are optional and can be added later to strengthen your writing style.'}</p>
                    <div className="hero-actions">
                      <button
                        className="button primary progress-button"
                        onClick={(event) => {
                          event.stopPropagation();
                          if (!brand.ready) {
                            go('Brand DNA');
                            return;
                          }
                          void generateContent();
                        }}
                        disabled={isGenerating}
                      >
                        <span className="button-content"><WandSparkles size={15} /> {isGenerating ? generationStage || 'Generating…' : brand.ready ? 'Generate content' : 'Build Brand DNA'}</span>
                        {isGenerating && <span className="button-progress-track"><span style={{ width: generationProgress + '%' }} /></span>}
                      </button>
                      <button className="button ghost-dark" onClick={(event) => { event.stopPropagation(); go('Research'); }}><Search size={15} /> Discover opportunities</button>
                    </div>
                  </div>
                  <div className="hero-status">
                    <div className="status-orb"><div className="orb-inner"><BrainCircuit size={30} /></div></div>
                    <div style={{ color: '#8f9ab1', fontSize: 10, textAlign: 'right' }}>AI prepared · human approved<br />No autonomous publishing</div>
                  </div>
                </div>
              </section>}

              <div className="metrics">
                <Metric icon={Clock3} label="Awaiting approval" value={summary.pending} meta="Needs your decision" />
                <Metric icon={CircleCheck} label="Approved" value={summary.reviewed} meta="Approved for publication" />
                <Metric icon={TrendingUp} label="Published" value={summary.executed} meta="Tracked by Suvacya" />
                <Metric icon={ShieldCheck} label="Guardrail status" value="ON" meta="Claims · voice · duplicate · action" />
                <Metric icon={BrainCircuit} label="Brand Pulse" value={brand.ready ? 'ACTIVE' : 'INACTIVE'} meta={brand.ready ? ((brand.current_post_count ?? brand.source_post_count) + ' signals in memory') : 'Set up before AI actions'} />
              </div>

              <section className="panel approval-panel">
                <div className="panel-head">
                  <div><div className="panel-title">Approval queue</div><div className="panel-subtitle">Your editorial desk — review the exact content before anything external happens.</div></div>
                  <button className="button" onClick={() => go('Content Studio')}><Plus size={14} /> New draft</button>
                </div>
                <ApprovalWorkspace
                  queue={filteredQueue} selected={selectedApproval} selectedId={selectedId}
                  setSelectedId={setSelectedId} searchTerm={searchTerm} setSearchTerm={setSearchTerm}
                  statusFilter={statusFilter} setStatusFilter={setStatusFilter}
                  dashboardCounts={dashboardCounts}
                  editedBody={editedBody} setEditedBody={setEditedBody}
                  reviewNote={reviewNote} setReviewNote={setReviewNote}
                  isBusy={isBusy} busyAction={busyAction} operationProgress={operationProgress} operationStage={operationStage}
                  onAction={runApprovalAction}
                />
              </section>
            </>
          )}

          {tab === 'Research' && <ResearchView loading={researchLoading} opportunities={opportunities} researchFocus={researchFocus} setResearchFocus={setResearchFocus} isResearching={isResearching} researchProgress={researchProgress} researchStage={researchStage} onResearch={discoverResearch} />}
          {tab === 'Content Studio' && <ContentStudio learningLoading={learningLoading} profile={profile} title={draftTitle} setTitle={setDraftTitle} topic={draftTopic} setTopic={setDraftTopic} body={draftBody} setBody={setDraftBody} language={draftLanguage} setLanguage={setDraftLanguage} busy={isBusy} improving={isImproving} improvementProgress={improvementProgress} improvementNotes={improvementNotes} onImprove={improveDraft} onSubmit={createDraft} savingThought={savingThought} onSaveThought={saveThought} learningStatus={learningStatus} />}
          {tab === 'LinkedIn Posts' && (loading && !queue.length ? <LinkedInPostsSkeleton /> : <LinkedInPostsView posts={queue.filter((item) => item.status === 'EXECUTED').slice(0, 10)} totalPublished={dashboardCounts.published} />)}
          {tab === 'Analytics' && <AnalyticsView loading={analyticsLoading} analytics={analytics} />}
          {tab === 'Jobs' && <ProductionJobsView jobs={jobs} location={jobLocation} query={jobQuery} experience={jobExperience} loading={jobsLoading} page={jobPage} hasMore={jobHasMore} onSearch={loadJobs} />}
          {tab === 'Feedback' && <FeedbackView type={feedbackType} setType={setFeedbackType} subject={feedbackSubject} setSubject={setFeedbackSubject} description={feedbackDescription} setDescription={setFeedbackDescription} context={feedbackContext} setContext={setFeedbackContext} sending={feedbackSending} onSubmit={async () => { if (!feedbackSubject.trim() || !feedbackDescription.trim() || !token) return; setFeedbackSending(true); try { const res = await apiFetch(API_BASE + '/api/feedback', { method: 'POST', headers: { ...headers(), 'Content-Type': 'application/json' }, body: JSON.stringify({ feedback_type: feedbackType, subject: feedbackSubject, description: feedbackDescription, context: feedbackContext }) }); const data = await res.json(); if (!res.ok) throw new Error(getApiError(data, 'Feedback could not be submitted.')); setFeedbackSubject(''); setFeedbackDescription(''); setFeedbackContext(''); setNotice('Thanks. Your feedback was submitted.'); } catch (e) { setError(e instanceof Error ? e.message : 'Feedback could not be submitted.'); } finally { setFeedbackSending(false); } }} />}
          {tab === 'Admin' && profile.role === 'admin' && <AdminView overview={adminOverview} activity={adminActivity} feedback={adminFeedback} users={adminUsers} aiProviders={adminAiProviders} jobProviders={adminJobProviders} sections={adminSections} sectionLoading={adminSectionLoading} onToggle={toggleAdminSection} onRefresh={refreshAdmin} />}
          {tab === 'Brand DNA' && (
            ((loading || brandLoading) && !brand.profile) ? <SettingsSkeleton /> : <SettingsView
              brand={brand}
              profile={profile}
              brandTitle={brandTitle}
              setBrandTitle={setBrandTitle}
              brandIndustry={brandIndustry}
              setBrandIndustry={setBrandIndustry}
              brandExperienceYears={brandExperienceYears}
              setBrandExperienceYears={setBrandExperienceYears}
              brandLocation={brandLocation}
              setBrandLocation={setBrandLocation}
              brandTone={brandTone}
              setBrandTone={setBrandTone}
              posts={historicalPostEntries}
              updatePost={updateHistoricalPost}
              addPost={addHistoricalPost}
              removePost={removeHistoricalPost}
              building={isBuildingBrand}
              onBuild={buildBrand}
              linkedin={linkedin}
              onConnect={connectLinkedIn}
              editing={brandEditing}
              setEditing={setBrandEditing}              onCancel={cancelBrandEdit}
              personalThoughts={personalThoughts}
              learningLoading={learningLoading}
              onDeletePersonalThoughts={async (ids: number[]) => {
                if (!ids.length) return;
                if (!window.confirm(ids.length === 1
                  ? 'Delete this personal insight? Suvacya will stop using it as a learning signal.'
                  : `Delete ${ids.length} personal insights? Suvacya will stop using them as learning signals.`)) return;
                try {
                  const res = await apiFetch(API_BASE + '/api/learning/thoughts', {
                    method: 'DELETE',
                    headers: { ...headers(), 'Content-Type': 'application/json' },
                    body: JSON.stringify({ ids }),
                  });
                  const data = await res.json().catch(() => ({}));
                  if (!res.ok) throw new Error(getApiError(data, 'Could not delete personal insights'));
                  const deletedIds = new Set(ids);
                  setPersonalThoughts((current) => current.filter((thought) => !deletedIds.has(thought.id)));
                  setExpandedThoughtId((current) => current !== null && deletedIds.has(current) ? null : current);
                  setNotice(data.deleted === 1 ? 'Personal insight deleted.' : `${data.deleted || ids.length} personal insights deleted.`);
                } catch (e) {
                  setError(e instanceof Error ? e.message : 'Could not delete personal insights');
                }
              }}
              expandedThoughtId={expandedThoughtId}
              setExpandedThoughtId={setExpandedThoughtId}
              selectedThoughtIds={selectedThoughtIds}
              setSelectedThoughtIds={setSelectedThoughtIds}
              thoughtSelectionMode={thoughtSelectionMode}
              setThoughtSelectionMode={setThoughtSelectionMode}
            />
          )}
        </main>
      </div>

      <nav className="mobile-bottom-nav" aria-label="Mobile workspace navigation">
        {[
          ['Dashboard', LayoutDashboard, 'Dashboard'],
          ['Research', Search, 'Research'],
          ['Content Studio', FileText, 'Content Studio'],
          ['Jobs', Briefcase, 'Jobs'],
        ].map(([key, Icon, label]) => (
          <button key={key as string} className={`mobile-nav-item ${tab === key ? 'active' : ''}`} onClick={() => go(key as Tab)}>
            <Icon size={18} />
            <span>{label as string}</span>
          </button>
        ))}
        <button className={`mobile-nav-item ${moreOpen ? 'active' : ''}`} onClick={() => setMoreOpen((open) => !open)}>
          <MoreHorizontal size={19} />
          <span>More</span>
        </button>
      </nav>

      {moreOpen && (
        <>
          <div className="mobile-more-backdrop" onClick={closeMore} />
          <section className="mobile-more-sheet" aria-label="More workspace options">
            <div className="mobile-sheet-handle" />
            <div className="mobile-sheet-title">More</div>
            <div className="mobile-more-grid">
              <button onClick={() => go('LinkedIn Posts')}><ExternalLink size={18} /><span>LinkedIn Posts</span></button>
              <button onClick={() => go('Analytics')}><BarChart3 size={18} /><span>Analytics</span></button>
              <button onClick={() => go('Brand DNA')}><Settings size={18} /><span>Brand DNA</span></button>
              {profile.role === 'admin' && <button onClick={() => go('Admin')}><ShieldAlert size={18} /><span>Admin</span></button>}
              <button onClick={() => { closeMore(); connectLinkedIn(); }}><Link2 size={18} /><span>{linkedin.connected ? 'LinkedIn' : 'Connect LinkedIn'}</span></button>
              <button onClick={installSuvacya} disabled={isStandalone}><Download size={18} /><span>{isStandalone ? 'Installed' : 'Install Suvacya'}</span></button>
            </div>
            <button className="mobile-more-signout" onClick={logout}><LogOut size={17} /> Sign out</button>
            <div className="mobile-more-footer">Suvacya · by Kanishka</div>
          </section>
        </>
      )}

      {showIosInstallGuide && (
        <div className="install-guide-backdrop" onClick={() => setShowIosInstallGuide(false)}>
          <section className="install-guide" onClick={(event) => event.stopPropagation()} role="dialog" aria-modal="true" aria-label="Install Suvacya">
            <div className="install-guide-icon"><Download size={20} /></div>
            <h2>Add Suvacya to your iPhone</h2>
            <p>Safari can install Suvacya as an app on your Home Screen.</p>
            <ol>
              <li>Tap the <strong>Share</strong> button in Safari.</li>
              <li>Choose <strong>Add to Home Screen</strong>.</li>
              <li>Turn on <strong>Open as Web App</strong>, then tap <strong>Add</strong>.</li>
            </ol>
            <button className="button primary" onClick={() => setShowIosInstallGuide(false)}>Got it</button>
          </section>
        </div>
      )}
    </div>
  );
}

function LoginScreen({ error, onConnect }: { error: string | null; onConnect: () => void }) {
  return (
    <main style={{ minHeight: '100vh', display: 'grid', placeItems: 'center', padding: 22, background: 'radial-gradient(circle at 20% 10%, #eaf3ff, transparent 28%), radial-gradient(circle at 90% 80%, #e8f3ff, transparent 30%), #f5f8fc' }}>
      <div className="login-shell">
        <div className="login-visual">
          <div className="brand-lockup" style={{ padding: 0 }}><div className="brand-mark"><Sparkles size={18}/></div><div><div className="brand-name">Suvacya</div><div className="brand-sub" style={{ color: '#8ea1b8' }}>Personal Brand Manager</div></div></div>
          <div style={{ position: 'relative', zIndex: 1, marginTop: 74 }}>
            <div className="page-kicker" style={{ color: '#b9d7f7' }}><Sparkles size={13}/> AI + human editorial control</div>
            <h1 style={{ fontFamily: 'Space Grotesk', fontSize: 47, lineHeight: 1.02, letterSpacing: '-.055em', margin: '12px 0 16px' }}>Your brand,<br/>with a brain.</h1>
            <p style={{ color: '#b8c9dc', maxWidth: 430, lineHeight: 1.65, fontSize: 13 }}>A professional operating system for discovering ideas, shaping your voice and preparing content — without giving an AI free rein over your identity.</p>
            <div style={{ display: 'grid', gap: 9, marginTop: 28 }}>
              {['Learns from approved content', 'Researches before drafting', 'Human approval before external actions'].map((x) => <div key={x} style={{ display: 'flex', gap: 9, alignItems: 'center', color: '#d8e3ee', fontSize: 11 }}><CircleCheck size={15} color="#4c8fef"/>{x}</div>)}
            </div>
          </div>
        </div>
        <div className="login-form">
          <div className="page-kicker"><ShieldCheck size={13}/> Secure official connection</div>
          <h2 style={{ fontFamily: 'Space Grotesk', fontSize: 29, letterSpacing: '-.04em', margin: '10px 0 8px' }}>Connect LinkedIn</h2>
          <p style={{ color: '#5f6f86', fontSize: 13, lineHeight: 1.6, margin: 0 }}>Suvacya uses LinkedIn's official OAuth flow. Your LinkedIn password is never entered into Suvacya.</p>
           <p style={{ color: '#5f6f86', fontSize: 11, lineHeight: 1.55, margin: '10px 0 0' }}>You'll authenticate securely on LinkedIn. If you're already signed in, LinkedIn may take you straight in.</p>
          {error && <div className="notice error" style={{ marginTop: 16 }}><X size={15}/><span>{error}</span></div>}
          <button className="button primary" style={{ width: '100%', minHeight: 46, marginTop: 24 }} onClick={onConnect}><LinkedInMark size={18}/> Continue with LinkedIn</button>
          <p style={{ color: '#6b7d92', fontSize: 10, lineHeight: 1.55, margin: '12px 0 0' }}>By continuing, you confirm that you are at least 18 years old and agree to the <a href="/terms" style={{ color: '#1769e0', fontWeight: 700 }}>Terms of Service</a> and <a href="/privacy" style={{ color: '#1769e0', fontWeight: 700 }}>Privacy Policy</a>. You can disconnect LinkedIn or delete your account later from Suvacya.</p>
          <div style={{ marginTop: 17, padding: 12, borderRadius: 12, background: '#f4f8fc', color: '#5f6f86', fontSize: 10, lineHeight: 1.55 }}>OAuth permissions requested are limited to supported identity and posting capabilities. External actions remain behind the approval gate.</div>
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
  const { queue, selected, selectedId, setSelectedId, searchTerm, setSearchTerm, statusFilter, setStatusFilter, dashboardCounts, editedBody, setEditedBody, reviewNote, setReviewNote, isBusy, busyAction, operationProgress, operationStage, onAction } = props;
  const [selectedImage, setSelectedImage] = useState<File | null>(null);
  const [mobileReviewOpen, setMobileReviewOpen] = useState(false);
  const [imagePreview, setImagePreview] = useState<string | null>(null);

  useEffect(() => {
    setSelectedImage(null);
    setImagePreview(null);
  }, [selectedId]);

  const chooseImage = (file: File | null) => {
    if (!file) return;
    if (!['image/jpeg', 'image/png', 'image/gif'].includes(file.type)) {
      window.alert('Only JPEG or PNG images are supported.');
      return;
    }
    if (file.size > 10 * 1024 * 1024) {
      window.alert('Image must be 4 MB or smaller.');
      return;
    }
    if (imagePreview) URL.revokeObjectURL(imagePreview);
    setSelectedImage(file);
    setImagePreview(URL.createObjectURL(file));
  };

  return (
    <div className="queue-layout">
      <div className="queue-list">
        <div className="queue-tools">
          <div className="searchbox"><Search size={13}/><input className="input" placeholder="Search drafts…" value={searchTerm} onChange={(e) => setSearchTerm(e.target.value)} /></div>
          <div className="filter-row">
            {([
              ['PENDING', 'Pending'],
              ['NEEDS_REVIEW', 'Needs review'],
              ['REJECTED', 'Rejected'],
              ['EXECUTED', 'Published'],
            ] as const).map(([value, label]) => (
              <button key={value} className={`filter-chip ${statusFilter === value ? 'active' : ''}`} onClick={() => setStatusFilter(value)}>
  <span>{label}</span>
  <em className="filter-count">{value === 'PENDING' ? dashboardCounts.pending_filter : value === 'NEEDS_REVIEW' ? dashboardCounts.needs_review : value === 'REJECTED' ? dashboardCounts.rejected : dashboardCounts.published}</em>
</button>
            ))}
          </div>
        </div>
        <div className="queue-items">
          {queue.length ? queue.map((item: ApprovalItem) => (
            <button key={item.id} className={`queue-item ${selectedId === item.id ? 'selected' : ''}`} onClick={() => { setSelectedId(item.id); setMobileReviewOpen(true); }}>
              <div className="queue-item-top"><span className="queue-id">POST #{item.id}</span><StatusPill status={item.status}/></div>
              <div className="queue-action">{item.action_type}</div>
              <div className="queue-preview">{item.content.slice(0, 88)}{item.content.length > 88 ? '…' : ''}</div>
            </button>
          )) : <div className="empty-state"><div className="empty-icon"><FileText size={18}/></div><strong>Queue is clear</strong><span>Create a draft or generate content to start the review flow.</span></div>}
        </div>
      </div>
      <div className={`review-pane ${mobileReviewOpen ? 'mobile-review-open' : ''}`}>
        {selected ? (
          <>
            <button className="mobile-review-back" onClick={() => setMobileReviewOpen(false)}><ChevronRight size={16} style={{ transform: 'rotate(180deg)' }} /> Back to queue</button>
            <div className="review-head"><div><div className="review-label">Editorial review · post #{selected.id}</div><div className="review-title">{selected.action_type}</div></div><StatusPill status={selected.status}/></div>

            {['PENDING','EDITED','REGENERATED'].includes(selected.status) ? (
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
                <div className="review-actions">
                  <button className="button success progress-button" disabled={isBusy} onClick={() => onAction('approve')}>
                    <span className="button-content"><Check size={14}/> {busyAction === 'approve' ? operationStage || 'Approving…' : 'Approve'}</span>
                    {busyAction === 'approve' && <span className="button-progress-track"><span style={{ width: operationProgress + '%' }} /></span>}
                  </button>
                  <button className="button" disabled={isBusy || editedBody === selected.content} onClick={() => onAction('edit', { edited_body: editedBody, reason: reviewNote || 'Edited during review.' })}><Pencil size={14}/> Save edit</button>
                  <button className="button progress-button" disabled={isBusy || !reviewNote.trim()} title={!reviewNote.trim() ? 'Add feedback before regenerating.' : 'Regenerate using your feedback'} onClick={() => onAction('regenerate', { reason: reviewNote.trim() })}>
                    <span className="button-content"><RotateCcw size={14}/> {busyAction === 'regenerate' ? operationStage || 'Regenerating…' : 'Regenerate'}</span>
                    {busyAction === 'regenerate' && <span className="button-progress-track"><span style={{ width: operationProgress + '%' }} /></span>}
                  </button>
                  <button className="button danger" disabled={isBusy} onClick={() => onAction('reject', { reason: reviewNote || 'Rejected by reviewer.' })}><X size={14}/> Reject</button>
                </div>
                <div className="form-help" style={{ marginTop: 8 }}>{reviewNote.trim() ? 'Regenerate will use this feedback and keep the new version behind the approval gate.' : 'Add feedback above to enable Regenerate.'}</div>
              </div>
            ) : selected.status === 'APPROVED' ? (
              <div className="review-editor">
                <div className="notice success" style={{ marginTop: 0 }}><CircleCheck size={15}/><span>Approved and locked. The content can no longer be edited or regenerated.</span></div>
                <div className="editor-toolbar" style={{ marginTop: 12 }}><span>Locked approved content</span><span>{selected.content.length} chars</span></div>
                <div className="readonly-field" style={{ whiteSpace: 'pre-wrap', lineHeight: 1.65, minHeight: 150 }}>{selected.content}</div>
                <div style={{ marginTop: 14, padding: 12, border: '1px dashed #c8d4e2', borderRadius: 12, background: '#fbfdff' }}>
                  <div className="review-label" style={{ marginBottom: 7 }}>Optional photograph</div>
                  <div className="form-help" style={{ marginBottom: 9 }}>Add one JPEG or PNG image (up to 4 MB). The image is sent directly to LinkedIn during execution and is not stored by Suvacya.</div>
                  <input type="file" accept="image/jpeg,image/png" onChange={(e) => chooseImage(e.target.files?.[0] || null)} disabled={isBusy} />
                  {imagePreview && (
                    <div style={{ marginTop: 10 }}>
                      <img src={imagePreview} alt="Selected LinkedIn post image preview" style={{ display: 'block', width: '100%', maxHeight: 280, objectFit: 'contain', borderRadius: 10, background: '#f1f5f9' }} />
                      <button className="link-button" style={{ marginTop: 7 }} onClick={() => { if (imagePreview) URL.revokeObjectURL(imagePreview); setImagePreview(null); setSelectedImage(null); }}>Remove image</button>
                    </div>
                  )}
                </div>
                <div className="review-actions" style={{ marginTop: 14 }}>
                  <button className="button success progress-button" disabled={isBusy} onClick={() => onAction('execute', selectedImage)}>
                    <span className="button-content"><ExternalLink size={14}/> {busyAction === 'execute' ? operationStage || 'Publishing…' : 'Execute'}</span>
                    {busyAction === 'execute' && <span className="button-progress-track"><span style={{ width: operationProgress + '%' }} /></span>}
                  </button>
                </div>
              </div>
            ) : (
              <div className={selected.status === 'EXECUTED' ? 'notice success' : 'notice error'} style={{ marginTop: 0 }}>
                <CircleCheck size={15}/><span>{selected.status === 'EXECUTED' ? 'Approved and published to LinkedIn. This post is permanently locked.' : 'This post is no longer awaiting a decision.'}</span>
              </div>
            )}

            <div style={{ marginTop: 17 }}>
              <div className="review-label" style={{ marginBottom: 9 }}>Safety rail</div>
              <div style={{ display: 'flex', gap: 7, flexWrap: 'wrap' }}>{['Claim guard','Voice guard','Duplicate guard','Action guard'].map((x) => <span key={x} className="tag"><ShieldCheck size={10}/>{x}</span>)}</div>
            </div>
          </>
        ) : <EmptyState icon={FileText} title="Select a draft" text="Your editorial workspace will appear here." />}
      </div>
    </div>
  );
}

function StatusPill({ status, label }: { status: string; label?: string }) {
  const cls = status.toLowerCase();
  return <span className={`status-pill ${cls}`}><span>●</span>{label || status}</span>;
}

function LinkedInPostsView({ posts, totalPublished }: { posts: ApprovalItem[]; totalPublished: number }) {
  return (
    <>
      <div className="page-header">
        <div>
          <div className="page-kicker"><ExternalLink size={13}/> LinkedIn content</div>
          <h1 className="page-title">Your published LinkedIn posts.</h1>
          <p className="page-description">Your 10 most recently published LinkedIn posts are shown here. Older posts are retained as learning signals, not as a full content archive.</p>
        </div>
      </div>
      <section className="panel">
        <div className="panel-head">
          <div><div className="panel-title">Published posts</div><div className="panel-subtitle">{totalPublished > 10 ? `Showing the 10 most recent of ${totalPublished} published posts` : `Showing all ${totalPublished} published posts`}</div></div>
        </div>
        <div className="post-stack">
          {posts.length ? posts.map((post) => (
            <article className="post-entry" key={post.id}>
              <div className="post-entry-head">
                <span className="post-index">POST #{post.id}</span>
                <StatusPill status={post.status} label="Published"/>
              </div>
              {post.title ? <div style={{ fontWeight: 700, fontSize: 13, marginBottom: 7 }}>{post.title}</div> : null}
              {post.topic ? <div className="form-help" style={{ marginBottom: 9 }}>{post.topic}</div> : null}
              <div style={{ whiteSpace: 'pre-wrap', fontSize: 12, lineHeight: 1.7, color: '#334b66' }}>{post.content}</div>
              {post.approved_at ? <div className="form-help" style={{ marginTop: 10 }}>Approved {new Date(post.approved_at).toLocaleString()}</div> : null}
            </article>
          )) : <EmptyState icon={ExternalLink} title="No published posts yet" text="Once you publish a post through Suvacya, it will appear here automatically." />}
        </div>
      </section>
    </>
  );
}

// Surface-level skeletons keep the workspace interactive while each API-backed section hydrates.
function SkeletonBlock({ width = '100%', height = 14, radius = 8 }: { width?: string | number; height?: number; radius?: number }) {
  return <div className="skeleton" style={{ width, height, borderRadius: radius }} aria-hidden="true" />;
}

function DashboardHeroSkeleton() {
  return <section className="hero">
    <div className="hero-grid">
      <div style={{ width: '100%' }}>
        <SkeletonBlock width={170} height={10} />
        <div style={{ marginTop: 14, display: 'grid', gap: 9 }}>
          <SkeletonBlock width="82%" height={32} radius={10} />
          <SkeletonBlock width="68%" height={32} radius={10} />
        </div>
        <div style={{ marginTop: 14, display: 'grid', gap: 7, maxWidth: 620 }}>
          <SkeletonBlock width="100%" height={11} />
          <SkeletonBlock width="92%" height={11} />
        </div>
        <div className="hero-actions" style={{ marginTop: 22 }}>
          <SkeletonBlock width={138} height={38} radius={10} />
          <SkeletonBlock width={170} height={38} radius={10} />
        </div>
      </div>
      <div className="hero-status"><SkeletonBlock width={72} height={72} radius={24} /></div>
    </div>
  </section>;
}

function DashboardSkeleton() {
  return <>
    <section className="hero">
      <div className="hero-grid">
        <div style={{ width: '100%' }}>
          <SkeletonBlock width={170} height={10} />
          <div style={{ marginTop: 14, display: 'grid', gap: 9 }}>
            <SkeletonBlock width="82%" height={32} radius={10} />
            <SkeletonBlock width="68%" height={32} radius={10} />
          </div>
          <div style={{ marginTop: 14, display: 'grid', gap: 7, maxWidth: 620 }}>
            <SkeletonBlock width="100%" height={11} />
            <SkeletonBlock width="92%" height={11} />
          </div>
          <div className="hero-actions" style={{ marginTop: 22 }}>
            <SkeletonBlock width={138} height={38} radius={10} />
            <SkeletonBlock width={170} height={38} radius={10} />
          </div>
        </div>
        <div className="hero-status"><SkeletonBlock width={72} height={72} radius={24} /></div>
      </div>
    </section>
    <div className="metrics">
      {[1,2,3,4,5].map((item) => <div className="metric-card" key={item}><SkeletonBlock width="52%" height={10}/><div style={{ marginTop: 15 }}><SkeletonBlock width="38%" height={26}/></div><div style={{ marginTop: 9 }}><SkeletonBlock width="72%" height={9}/></div></div>)}
    </div>
    <section className="panel approval-panel">
      <div className="panel-head"><div style={{ width: '48%' }}><SkeletonBlock width={150} height={15}/><div style={{ marginTop: 8 }}><SkeletonBlock width="90%" height={9}/></div></div><SkeletonBlock width={92} height={34} radius={9}/></div>
      <div style={{ display: 'grid', gap: 9, padding: '0 18px 18px' }}>
        {[1,2,3].map((item) => <div className="post-entry" key={item}><SkeletonBlock width="28%" height={9}/><div style={{ marginTop: 10 }}><SkeletonBlock width="72%" height={13}/></div><div style={{ marginTop: 8 }}><SkeletonBlock width="94%" height={9}/></div></div>)}
      </div>
    </section>
  </>;
}

function LinkedInPostsSkeleton() {
  return <>
    <div className="page-header"><div><SkeletonBlock width={170} height={10}/><div style={{ marginTop: 10 }}><SkeletonBlock width={280} height={28}/></div><div style={{ marginTop: 9 }}><SkeletonBlock width={420} height={10}/></div></div></div>
    <section className="panel settings-card">
      {[1,2,3].map((item) => <div className="post-entry" key={item} style={{ marginTop: item === 1 ? 0 : 10 }}><SkeletonBlock width="24%" height={9}/><div style={{ marginTop: 10 }}><SkeletonBlock width="82%" height={13}/></div><div style={{ marginTop: 8 }}><SkeletonBlock width="96%" height={9}/><div style={{ marginTop: 6 }}><SkeletonBlock width="76%" height={9}/></div></div></div>)}
    </section>
  </>;
}

function SettingsSkeleton() {
  return <>
    <div className="page-header"><div><SkeletonBlock width={120} height={10}/><div style={{ marginTop: 10 }}><SkeletonBlock width={230} height={28}/></div><div style={{ marginTop: 9 }}><SkeletonBlock width={520} height={10}/></div></div></div>
    <section className="panel settings-card">
      <div className="profile-grid">{[1,2,3,4].map((item) => <div className="form-group" key={item}><SkeletonBlock width={90} height={9}/><div style={{ marginTop: 7 }}><SkeletonBlock width="100%" height={40} radius={9}/></div></div>)}</div>
      <div style={{ marginTop: 18 }}><SkeletonBlock width={150} height={10}/><div style={{ marginTop: 9 }}><SkeletonBlock width="100%" height={70} radius={10}/></div></div>
    </section>
    <section className="panel settings-card" style={{ marginTop: 16 }}><SkeletonBlock width={150} height={14}/><div style={{ marginTop: 10 }}><SkeletonBlock width="72%" height={9}/></div><div style={{ marginTop: 16 }}><SkeletonBlock width="100%" height={90} radius={10}/></div></section>
  </>;
}

function ResearchSkeleton() {
  return <>
    <div className="page-header"><div><SkeletonBlock width={130} height={10}/><div style={{ marginTop: 10 }}><SkeletonBlock width={310} height={28}/></div><div style={{ marginTop: 9 }}><SkeletonBlock width={520} height={10}/></div></div><SkeletonBlock width={118} height={36} radius={9}/></div>
    <section className="panel research-focus-panel"><SkeletonBlock width={180} height={13}/><div style={{ marginTop: 8 }}><SkeletonBlock width="78%" height={9}/></div><div style={{ marginTop: 14 }}><SkeletonBlock width="100%" height={42} radius={9}/></div></section>
    <div className="research-grid">{[1,2,3].map((item) => <article className="research-card" key={item}><SkeletonBlock width={130} height={9}/><div style={{ marginTop: 12 }}><SkeletonBlock width="82%" height={16}/></div><div style={{ marginTop: 8 }}><SkeletonBlock width="95%" height={9}/><div style={{ marginTop: 6 }}><SkeletonBlock width="72%" height={9}/></div></div><div className="research-relevance-grid" style={{ marginTop: 16 }}><SkeletonBlock width="100%" height={55} radius={9}/><SkeletonBlock width="100%" height={55} radius={9}/></div></article>)}</div>
  </>;
}

function AnalyticsSkeleton() {
  return <>
    <div className="page-header"><div><SkeletonBlock width={150} height={10}/><div style={{ marginTop: 10 }}><SkeletonBlock width={320} height={28}/></div><div style={{ marginTop: 9 }}><SkeletonBlock width={550} height={10}/></div></div></div>
    <div className="metrics">{[1,2,3,4].map((item) => <div className="metric-card" key={item}><SkeletonBlock width="50%" height={10}/><div style={{ marginTop: 15 }}><SkeletonBlock width="36%" height={25}/></div><div style={{ marginTop: 9 }}><SkeletonBlock width="78%" height={9}/></div></div>)}</div>
  </>;
}

function ResearchView({ loading, opportunities, researchFocus, setResearchFocus, isResearching, researchProgress, researchStage, onResearch }: { loading: boolean; opportunities: Opportunity[]; researchFocus: string; setResearchFocus: (value: string) => void; isResearching: boolean; researchProgress: number; researchStage: string; onResearch: () => void }) {
  if (loading && !opportunities.length) return <ResearchSkeleton />;
  const hasResearch = opportunities.length > 0;
  return (
    <>
      <div className="page-header">
        <div><div className="page-kicker"><Search size={13}/> Intelligence layer</div><h1 className="page-title">Research</h1><p className="page-description">{hasResearch ? 'Your latest research is below. Add a focus whenever you want Suvacya to explore a specific topic.' : 'Live evidence is combined with your Brand DNA, recent research interests and learned context before an idea reaches the drafting engine.'}</p></div>
        <button className="button primary progress-button" onClick={onResearch} disabled={isResearching}>
          <span className="button-content"><Search size={14}/>{isResearching ? researchStage || 'Researching…' : hasResearch ? 'Research now' : 'Run research'}</span>
          {isResearching && <span className="button-progress-track"><span style={{ width: researchProgress + '%' }} /></span>}
        </button>
      </div>

      <section className="panel research-focus-panel">
        <div className="research-focus-copy">
          <div className="panel-title">Guide the research <span className="form-help">(optional)</span></div>
          <div className="panel-subtitle">Tell Suvacya what you want to explore. Leave it blank and Suvacya will use your Brand DNA plus what it has learned from your research and content.</div>
        </div>
        <div className="research-focus-row">
          <div className="research-focus-input">
            <Search size={15}/>
            <input
              className="input"
              value={researchFocus}
              onChange={(e) => setResearchFocus(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter' && !isResearching) onResearch(); }}
              placeholder="e.g. AI adoption in consulting, stakeholder management, project governance"
              aria-label="Optional research focus"
            />
          </div>
          <button className="button primary" onClick={onResearch} disabled={isResearching}>
            <Search size={14}/>{isResearching ? 'Researching…' : hasResearch ? 'Research now' : 'Run research'}
          </button>
        </div>
      </section>

      <div className="research-grid">
        {opportunities.length ? opportunities.map((item) => <ResearchCard key={item.id} item={item}/>) :
          <section className="panel"><EmptyState icon={Search} title="No research yet" text="Add an optional focus above, or let Suvacya discover current topics from your Brand DNA." action="Run research" onAction={onResearch}/></section>}
      </div>
    </>
  );
}

function ResearchCard({ item }: { item: Opportunity }) {
  const brandRelevance = Number(item.scores?.brand_fit ?? 0);
  const evidenceStrength = Number(item.scores?.evidence_strength ?? 0);
  return (
    <article className="research-card">
      <div className="research-top">
        <div style={{ minWidth: 0 }}>
          <div className="tag-row"><span className="tag">{item.pillar}</span><span className="tag">{item.format || 'Insight post'}</span></div>
          <div className="research-title">{item.title}</div>
          <p className="research-angle">{item.angle}</p>
        </div>
      </div>

      <div className="research-relevance-grid">
        <div className="research-relevance-item">
          <div className="score-name">Relevant to your profile</div>
          <div className="research-relevance-value">{Math.round(brandRelevance)}%</div>
          <div className="score-bar"><span style={{ width: `${Math.min(100, Math.max(0, brandRelevance))}%` }}/></div>
        </div>
        <div className="research-relevance-item">
          <div className="score-name">Evidence quality</div>
          <div className="research-relevance-value">{Math.round(evidenceStrength)}%</div>
          <div className="score-bar"><span style={{ width: `${Math.min(100, Math.max(0, evidenceStrength))}%` }}/></div>
        </div>
      </div>

      {item.evidence?.summary && <div className="evidence-box"><b>What the source says:</b> {item.evidence.summary}</div>}
      {item.evidence?.why_now && <p className="research-why"><b>Why it matters now:</b> {item.evidence.why_now}</p>}
      {item.rationale && <p className="research-rationale">{item.rationale}</p>}
      {item.sources?.length ? (
        <div className="source-row">
          {item.sources.slice(0, 3).map((source, i) => source.url ? (
            <a className="source-link" key={i} href={source.url} target="_blank" rel="noreferrer">
              {source.domain || source.title || 'Read source'} <ExternalLink size={10}/>
            </a>
          ) : null)}
        </div>
      ) : null}
      {item.sources?.length ? (
        <div className="research-read-more">
          {item.sources.slice(0, 1).map((source, i) => source.url ? (
            <a className="button" key={i} href={source.url} target="_blank" rel="noreferrer">Read more <ArrowUpRight size={13}/></a>
          ) : null)}
        </div>
      ) : null}
    </article>
  );
}

function ContentStudio({ learningLoading, profile, title, setTitle, topic, setTopic, body, setBody, language, setLanguage, busy, improving, improvementProgress, improvementNotes, onImprove, onSubmit, savingThought, onSaveThought, learningStatus }: any) {
  return (
    <>
      <div className="page-header">
        <div>
          <div className="page-kicker"><WandSparkles size={13}/> Editorial studio</div>
          <h1 className="page-title">Write it your way. Let Suvacya polish it.</h1>
          <p className="page-description">Start with your own idea and wording in any language. Suvacya can improve structure and clarity using your Brand DNA, then you preview the exact version before it enters the approval queue.</p>
          <div className="form-help" style={{ marginTop: 8 }}>
            {learningLoading ? <span style={{ display: 'inline-flex', width: 280 }}><SkeletonBlock width="100%" height={10} /></span> : <>Brand learning is active · {learningStatus?.memory_count ?? 0} learned signals · {learningStatus?.pending_events ?? 0} queued for processing</>}
          </div>
        </div>
      </div>
      <section className="panel studio-grid">
        <div className="studio-form">
          <div className="form-group"><label className="form-label">Post heading / working title</label><input className="input" value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Write the idea or heading you have in mind" /></div>
          <div className="form-group"><label className="form-label">Topic / theme <span className="form-help">(optional)</span></label><input className="input" value={topic} onChange={(e) => setTopic(e.target.value)} placeholder="What is this post about?" /></div>
          <div className="form-group"><label className="form-label">Your language</label><input className="input" value={language} onChange={(e) => setLanguage(e.target.value)} placeholder="e.g. English, Hindi, Hinglish" /></div>
          <div className="form-group">
            <label className="form-label">Your draft</label>
            <textarea className="textarea" style={{ minHeight: 270 }} value={body} onChange={(e) => setBody(e.target.value)} placeholder="Write naturally. Do not worry about formatting — Suvacya will preserve your meaning and improve the presentation." />
          </div>
          <div style={{ display: 'flex', gap: 9, alignItems: 'center', flexWrap: 'wrap' }}>
            <button className="button primary progress-button" disabled={improving || !body.trim()} onClick={onImprove}>
              <span className="button-content"><WandSparkles size={14}/>{improving ? 'Polishing…' : 'Improvise / polish with Suvacya'}</span>
              {improving && <span className="button-progress-track"><span style={{ width: improvementProgress + '%' }} /></span>}
            </button>
            <button className="button dark" disabled={busy || !body.trim()} onClick={onSubmit}><ShieldCheck size={14}/>{busy ? 'Sending…' : 'Send this version to approval'}</button>
            <button className="button" disabled={savingThought || !body.trim()} onClick={onSaveThought}>{savingThought ? 'Saving…' : 'Save as personal thought'}</button>
          </div>
          {improvementNotes?.length ? <div style={{ marginTop: 12, padding: 11, borderRadius: 11, background: '#eaf3ff', color: '#5f6f86', fontSize: 10, lineHeight: 1.5 }}><b style={{ color: '#1558b0' }}>What changed:</b> {improvementNotes.join(' · ')}</div> : null}
        </div>
        <div className="live-preview">
          <div className="panel-title" style={{ marginBottom: 4 }}>Preview before approval</div>
          <div className="panel-subtitle" style={{ marginBottom: 14 }}>This is the exact text you can send to the HITL queue. Nothing is published from this screen.</div>
          <div className="linkedin-card">
            <div className="li-head"><div className="li-avatar">{(profile.display_name || 'U').slice(0,1).toUpperCase()}</div><div><div className="li-name">{profile.display_name}</div><div className="li-meta">Professional profile · Draft</div></div></div>
            <div className="li-body">{body || 'Your polished post preview will appear here.'}</div>
            <div className="li-actions"><span>Like</span><span>Comment</span><span>Share</span></div>
          </div>
          <div style={{ marginTop: 12, padding: 11, borderRadius: 11, background: '#eaf3ff', color: '#5f6f86', fontSize: 10, lineHeight: 1.5 }}><b style={{ color: '#1558b0' }}>HITL:</b> Polish → preview → send to approval → approve → publish. The AI never bypasses the approval gate.</div>
        </div>
      </section>
    </>
  );
}

function AnalyticsView({ loading, analytics }: { loading: boolean; analytics: any }) {
  if (loading && !analytics) return <AnalyticsSkeleton />;
  const p = analytics?.pipeline || {};
  const live = analytics?.linkedin_performance || {};
  const totals = live.totals || {};
  const trend = Array.isArray(live.trend) ? live.trend : [];
  const cards = [
    ['Historical posts', p.historical_posts ?? 0, 'User-provided brand evidence'],
    ['Content created', p.content_items ?? 0, 'Drafts generated in Suvacya'],
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

              <div className="panel" style={{ border: '1px solid #e5ebf2', boxShadow: 'none' }}>
                <div className="panel-head">
                  <div><div className="panel-title">Daily trend</div><div className="panel-subtitle">Impressions and engagement reported by LinkedIn.</div></div>
                </div>
                <div className="panel-body">
                  {trend.length ? (
                    <div style={{ display: 'grid', gap: 9 }}>
                      {trend.slice(-14).map((row: any) => (
                        <div key={row.date} style={{ display: 'grid', gridTemplateColumns: '72px 1fr 70px', gap: 9, alignItems: 'center', fontSize: 10 }}>
                          <span style={{ color: '#5f6f86' }}>{new Date(row.date).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })}</span>
                          <div style={{ height: 8, background: '#f1f5f9', borderRadius: 99, overflow: 'hidden' }}>
                            <div style={{ width: `${Math.max(2, Math.round((Number(row.IMPRESSION || 0) / maxImpressions) * 100))}%`, height: '100%', background: '#1558b0', borderRadius: 99 }} />
                          </div>
                          <span style={{ textAlign: 'right', color: '#334b66' }}>{Number(row.IMPRESSION || 0).toLocaleString()} imp.</span>
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
                <div style={{ maxWidth: 620, fontSize: 10, lineHeight: 1.6, color: '#5f6f86', marginTop: 6 }}>
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
        <div className="panel-body" style={{ color: '#5f6f86', fontSize: 11, lineHeight: 1.7 }}>
          Once analytics access is active, this view will show post impressions, reach, reactions, comments, reshares and engagement trends from LinkedIn's official member analytics API. Suvacya will not scrape LinkedIn or fabricate performance numbers.
        </div>
      </section>
      )}
    </>
  );
}

function SettingsView(props: any) {
  const {
    brand, profile, brandTitle, setBrandTitle, brandIndustry, setBrandIndustry,
    brandExperienceYears, setBrandExperienceYears, brandLocation, setBrandLocation, brandTone, setBrandTone,
    posts, updatePost, addPost, removePost, building, onBuild, linkedin, onConnect,
    editing, setEditing, onCancel, learningLoading = false, personalThoughts = [], onDeletePersonalThoughts,
    expandedThoughtId, setExpandedThoughtId, selectedThoughtIds = [], setSelectedThoughtIds,
    thoughtSelectionMode = false, setThoughtSelectionMode
  } = props;

  const count = posts.filter((x: string) => x.trim()).length;
  const experienceValue = brandExperienceYears === '' ? '' : String(Math.round(Number(brandExperienceYears)));
  const linkedinProfile = brand.linkedin_profile || {};
  const hasLinkedInProfile = Boolean(linkedinProfile.connected || linkedin.connected);
  const linkedinPicture = linkedinProfile.picture_url || '';
  const linkedinPhotoAvailable = Boolean(linkedinPicture);

  return (
    <>
      <div className="page-header">
        <div>
          <div className="page-kicker"><BrainCircuit size={13}/> Brand intelligence</div>
          <h1 className="page-title">Your brand memory.</h1>
          <p className="page-description">
            {hasLinkedInProfile
              ? 'We use the LinkedIn profile data available through the official connection to create your starting Brand DNA. Review it before you continue.'
              : 'Your Brand DNA stays under your control. Connect LinkedIn to prefill the starting profile where data is available.'}
          </p>
        </div>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          <span className={"status-pill " + (brand.ready ? 'approved' : 'edited')}>{brand.ready ? '● ACTIVE' : '● REVIEW NEEDED'}</span>
          {brand.ready && !editing && <button className="button" onClick={() => setEditing(true)}><Pencil size={14}/> Manage Brand DNA</button>}
        </div>
      </div>

      {!brand.ready || editing ? (
        <div className="settings-stack">
          <section className="panel settings-card">
            <div className="panel-head" style={{ padding: 0, border: 0 }}>
              <div>
                <h2 className="settings-title">Review your starting Brand DNA</h2>
                <p className="settings-copy">
                  {hasLinkedInProfile
                    ? 'Suvacya has prefilled what it could from your LinkedIn connection. Keep it, edit it, or complete anything that is missing.'
                    : 'Complete the few profile details below. Historical posts are optional.'}
                </p>
              </div>
              {brand.ready && <button className="button" onClick={onCancel}><X size={14}/> Cancel</button>}
            </div>

            {hasLinkedInProfile && (
              <div style={{ marginTop: 14, padding: 12, borderRadius: 11, background: '#eaf3ff', color: '#5f6f86', fontSize: 10, lineHeight: 1.55, display: 'flex', gap: 12, alignItems: 'center' }}>
                {linkedinPhotoAvailable ? (
                  <img
                    src={linkedinPicture}
                    alt="LinkedIn profile"
                    style={{ width: 48, height: 48, borderRadius: '50%', objectFit: 'cover', flex: '0 0 auto', border: '1px solid #e4e7ec' }}
                    referrerPolicy="no-referrer"
                  />
                ) : (
                  <div style={{ width: 48, height: 48, borderRadius: '50%', display: 'grid', placeItems: 'center', background: '#e4e7ec', color: '#334b66', fontWeight: 700, flex: '0 0 auto' }}>
                    {(profile.display_name || 'U').slice(0, 1).toUpperCase()}
                  </div>
                )}
                <div>
                  <div style={{ color: '#1558b0', fontWeight: 700, marginBottom: 4 }}>LinkedIn profile data</div>
                  <div><b>Name:</b> {profile.display_name || 'Available'}</div>
                  <div><b>Photo:</b> {linkedinPhotoAvailable ? 'Fetched from LinkedIn' : 'Not returned by LinkedIn'}</div>
                  <div><b>Headline:</b> {linkedinProfile.headline || 'Not Shared by LinkedIn'}</div>
                </div>
              </div>
            )}

            {linkedinProfile.headline && (
              <div style={{ marginTop: 14, padding: 12, borderRadius: 11, background: '#eaf3ff', color: '#5f6f86', fontSize: 10, lineHeight: 1.55 }}>
                <div style={{ color: '#1558b0', fontWeight: 700, marginBottom: 4 }}>LinkedIn profile signal</div>
                <div><b>Headline:</b> {linkedinProfile.headline}</div>
              </div>
            )}

            <div className="profile-grid" style={{ marginTop: 16 }}>
              <div className="form-group">
                <label className="form-label">Professional title</label>
                <input className="input" value={brandTitle} onChange={(e) => setBrandTitle(e.target.value)} placeholder="e.g. Product Leader, Founder, Engineering Manager" />
              </div>
              <div className="form-group">
                <label className="form-label">Industry</label>
                <input className="input" value={brandIndustry} onChange={(e) => setBrandIndustry(e.target.value)} placeholder="e.g. SaaS, FinTech, Healthcare, Consulting" />
              </div>
              <div className="form-group">
                <label className="form-label">Desired tone</label>
                <input className="input" value={brandTone} onChange={(e) => setBrandTone(e.target.value)} placeholder="e.g. Direct, practical and credible" />
              </div>
              <div className="form-group">
                <label className="form-label">Years of work experience <span style={{ fontWeight: 500, color: '#8a98ab' }}>(optional)</span></label>
                <input
                  className="input"
                  type="number"
                  min="0"
                  max="100"
                  step="1"
                  value={experienceValue}
                  onChange={(e) => {
                    const raw = e.target.value;
                    setBrandExperienceYears(raw === '' ? '' : Math.round(Number(raw)));
                  }}
                  placeholder="e.g. 8"
                />
                <span className="form-help">Use whole years. If a decimal is entered, it is rounded to the nearest whole year.</span>
              </div>
              <div className="form-group">
                <label className="form-label">Job search location <span style={{ fontWeight: 500, color: '#8a98ab' }}>(optional)</span></label>
                <input
                  className="input"
                  value={brandLocation}
                  onChange={(e) => setBrandLocation(e.target.value)}
                  placeholder="e.g. Hyderabad, Bengaluru, Remote"
                />
                <span className="form-help">Used for Jobs. If blank, Suvacya falls back to your network-detected location.</span>
              </div>
            </div>

            <div style={{ marginTop: 14, padding: 11, borderRadius: 11, background: '#eaf3ff', color: '#5f6f86', fontSize: 10, lineHeight: 1.55 }}>
              <b style={{ color: '#1558b0' }}>What happens next:</b> these reviewed details become the profile context used by Brand Intelligence. LinkedIn does not overwrite anything you change here.
            </div>
          </section>

          <section className="panel settings-card">
            <div style={{ display: 'flex', justifyContent: 'space-between', gap: 10, alignItems: 'center', flexWrap: 'wrap' }}>
              <div>
                <h2 className="settings-title">Voice calibration <span style={{ fontWeight: 500, color: '#8a98ab' }}>(optional)</span></h2>
                <p className="settings-copy">Add 3–10 previous LinkedIn posts if you want Suvacya to learn your writing style from real examples. You can skip this and add them later.</p>
              </div>
              <span className={"status-pill " + (count ? 'approved' : 'edited')}>{count}/10 posts</span>
            </div>

            {posts.length > 0 && (
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
            )}

            <div style={{ display: 'flex', justifyContent: 'space-between', gap: 10, alignItems: 'center', marginTop: 12, flexWrap: 'wrap' }}>
              <button className="button" onClick={addPost} disabled={posts.length >= 10}><Plus size={14}/>{posts.length >= 10 ? 'Maximum reached' : count ? 'Add another post' : 'Add previous posts'}</button>
              <button className="button primary" onClick={onBuild} disabled={building || !brandTitle.trim() || !brandIndustry.trim() || !brandTone.trim()}>
                <RefreshCw size={14}/>
                {building ? 'Building…' : brand.ready ? 'Save & refresh Brand Intelligence' : 'Save & build Brand DNA'}
              </button>
            </div>
            {!count && (
              <div style={{ marginTop: 10, color: '#5f6f86', fontSize: 10 }}>
                No posts added. That is okay. Suvacya can start from your profile and learn from your content over time.
              </div>
            )}
          </section>
        </div>
      ) : (
        <div className="settings-stack">
          <section className="panel settings-card">
            <div className="panel-head" style={{ padding: 0, border: 0 }}>
              <div><h2 className="settings-title">Saved Brand DNA</h2><p className="settings-copy">Read-only view of the profile context used by Suvacya.</p></div>
              <span className="tag"><ShieldCheck size={10}/> Frozen</span>
            </div>
            <div className="profile-grid" style={{ marginTop: 16 }}>
              {[
                ['Professional title', brandTitle],
                ['Industry', brandIndustry],
                ['Desired tone', brandTone],
                ['Years of work experience', experienceValue ? experienceValue + ' years' : 'Optional / not provided'],
                ['Job search location', brandLocation || 'Optional / uses network location'],
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
              <div><h2 className="settings-title">Voice calibration</h2><p className="settings-copy">These imported posts are optional source evidence for writing style. Suvacya can also learn from approved and published content afterward.</p></div>
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
                <span>You can add previous LinkedIn posts later if you want stronger voice calibration.</span>
              </div>
            )}
          </section>

          <section className="panel settings-card">
            <h2 className="settings-title">Brand Intelligence status</h2>
            <p className="settings-copy">{brand.summary || 'Brand Intelligence is active and ready to shape content.'}</p>
            <div className="learning-flow">
              <div className="flow-step"><BrainCircuit size={15} color="#1769e0"/><b>Professional title</b><span>{brand.profile?.professional_title || 'Not set'}</span></div>
              <div className="flow-step"><Target size={15} color="#1769e0"/><b>Industry</b><span>{brand.profile?.industry || 'Not set'}</span></div>
              <div className="flow-step"><Sparkles size={15} color="#1769e0"/><b>Voice</b><span>{brand.profile?.tone || 'Not set'}</span></div>
              <div className="flow-step"><Activity size={15} color="#1769e0"/><b>Experience</b><span>{brand.profile?.experience_years != null ? Math.round(brand.profile.experience_years) + ' years' : 'Optional / not provided'} · {brand.current_post_count ?? brand.source_post_count} signals</span></div>
              <div className="flow-step"><Target size={15} color="#1769e0"/><b>Job search location</b><span>{brand.profile?.job_location || 'Network location fallback'}</span></div>
            </div>
          </section>
        </div>
      )}

      <section className="panel settings-card" style={{ marginTop: 16 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 14 }}>
          <div>
            <h2 className="settings-title">Personal Insights</h2>
            <p className="settings-copy">Things you have explicitly shared with Suvacya. These help personalize future research and content without automatically changing your core Brand DNA.</p>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap', justifyContent: 'flex-end' }}>
            <span className="status-pill approved">● {personalThoughts.length} SAVED</span>
            {personalThoughts.length > 1 && (
              <button className="button" onClick={() => {
                setThoughtSelectionMode?.((current: boolean) => !current);
                setSelectedThoughtIds?.([]);
              }}>
                {thoughtSelectionMode ? 'Cancel selection' : 'Select'}
              </button>
            )}
          </div>
        </div>
        {learningLoading ? (
          <div className="post-stack" style={{ marginTop: 14 }}>
            {[1,2].map((item) => <article className="post-entry" key={item}><SkeletonBlock width={120} height={9}/><div style={{ marginTop: 10 }}><SkeletonBlock width="62%" height={13}/></div><div style={{ marginTop: 9 }}><SkeletonBlock width="96%" height={9}/><div style={{ marginTop: 6 }}><SkeletonBlock width="78%" height={9}/></div></div></article>)}
          </div>
        ) : personalThoughts.length ? (
          <div className="post-stack" style={{ marginTop: 14 }}>
            {personalThoughts.map((thought: PersonalThought) => {
              const expanded = expandedThoughtId === thought.id;
              const preview = thought.content.trim().length > 180
                ? thought.content.trim().slice(0, 180).replace(/\s+\S*$/, '') + '…'
                : thought.content.trim();
              return (
                <article className="post-entry" key={thought.id} style={thoughtSelectionMode ? { borderColor: selectedThoughtIds.includes(thought.id) ? '#1769e0' : undefined } : undefined}>
                  <div className="post-entry-head">
                    {thoughtSelectionMode && (
                      <label style={{ display: 'flex', alignItems: 'center', gap: 6, color: '#5f6f86', fontSize: 10 }}>
                        <input
                          type="checkbox"
                          checked={selectedThoughtIds.includes(thought.id)}
                          onChange={(e) => setSelectedThoughtIds?.((current: number[]) => e.target.checked
                            ? [...current, thought.id]
                            : current.filter((id) => id !== thought.id))}
                        />
                        Select
                      </label>
                    )}
                    <span className="post-index">PERSONAL INSIGHT</span>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                      {thought.created_at ? (
                        <span style={{ color: '#8a98ab', fontSize: 10 }}>
                          {new Date(thought.created_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })}
                        </span>
                      ) : null}
                      <button
                        className="link-button"
                        style={{ color: '#b91c1c' }}
                        onClick={() => onDeletePersonalThoughts?.([thought.id])}
                        title="Delete personal insight"
                        aria-label="Delete personal insight"
                      >
                        Delete
                      </button>
                    </div>
                  </div>
                  {thought.title ? <div style={{ fontWeight: 700, color: '#334b66', marginBottom: 5 }}>{thought.title}</div> : null}
                  {thought.topic ? <div style={{ color: '#5f6f86', fontSize: 10, marginBottom: 7 }}>Topic · {thought.topic}</div> : null}
                  <div style={{ color: '#334b66', fontSize: 11, lineHeight: 1.65, whiteSpace: 'pre-wrap' }}>
                    {expanded ? thought.content : preview}
                  </div>
                  {thought.content.trim().length > 180 && (
                    <button
                      className="link-button"
                      style={{ marginTop: 7 }}
                      onClick={() => setExpandedThoughtId(expanded ? null : thought.id)}
                      aria-expanded={expanded}
                    >
                      {expanded ? 'Show less ↑' : 'Read more →'}
                    </button>
                  )}
                </article>
              );
            })}
          </div>
        ) : (
          <div className="empty-state" style={{ minHeight: 120, marginTop: 14 }}>
            <strong>No personal insights saved yet</strong>
            <span>When you save a thought from Content Studio, it will appear here and become available as a learning signal.</span>
          </div>
        )}
        {thoughtSelectionMode && selectedThoughtIds.length > 0 && (
          <div style={{ marginTop: 12, display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
            <span style={{ color: '#5f6f86', fontSize: 10 }}>{selectedThoughtIds.length} selected</span>
            <button
              className="link-button"
              style={{ color: '#b91c1c', fontWeight: 700 }}
              onClick={async () => {
                await onDeletePersonalThoughts?.(selectedThoughtIds);
                setSelectedThoughtIds?.([]);
                setThoughtSelectionMode?.(false);
              }}
            >
              Delete selected
            </button>
          </div>
        )}
      </section>


    </>
  );
}

function WorkspaceLoading({ message = 'Loading your workspace…' }: { message?: string }) {
  return (
    <div className="workspace-loading-overlay" role="status" aria-live="polite" aria-busy="true">
      <div className="workspace-loading-card">
        <div className="workspace-loading-spinner"><LoaderCircle size={18} className="spin" /></div>
        <div>
          <strong>{message}</strong>
          <span>Fetching the latest data securely from Suvacya.</span>
        </div>
      </div>
    </div>
  );
}

function EmptyState({ icon: Icon, title, text, action, onAction }: any) {
  return <div className="empty-state"><div className="empty-icon"><Icon size={19}/></div><strong>{title}</strong><span>{text}</span>{action && <div style={{ marginTop: 14 }}><button className="button primary" onClick={onAction}>{action}<ChevronRight size={13}/></button></div>}</div>;
}

function LinkedInMark({ size = 18, color }: { size?: number; color?: string }) {
  return <svg width={size} height={size} viewBox="0 0 24 24" fill={color || 'currentColor'} aria-hidden="true"><path d="M6.5 8.2H3.2V20h3.3V8.2ZM4.85 3A1.95 1.95 0 1 0 4.85 6.9 1.95 1.95 0 0 0 4.85 3ZM20.8 13.25c0-3.52-1.88-5.16-4.4-5.16-2.02 0-2.92 1.11-3.43 1.89V8.2H9.67V20h3.3v-5.84c0-1.54.29-3.03 2.2-3.03 1.88 0 1.91 1.76 1.91 3.13V20h3.3l.02-6.75Z"/></svg>;
}
function JobsView({ jobs, location, query, setQuery, loading, expandedId, setExpandedId, onSearch }: any) {
  if (loading && !jobs.length) return <>
    <div className="page-header"><div><SkeletonBlock width={140} height={10}/><div style={{ marginTop: 10 }}><SkeletonBlock width={260} height={28}/></div><div style={{ marginTop: 9 }}><SkeletonBlock width={510} height={10}/></div></div></div>
    <section className="panel" style={{ padding: 18 }}><SkeletonBlock width="100%" height={42} radius={9}/><div style={{ marginTop: 10 }}><SkeletonBlock width={340} height={9}/></div><div style={{ marginTop: 8 }}><SkeletonBlock width={230} height={9}/></div></section>
    <section className="panel" style={{ marginTop: 16, padding: 18 }}><SkeletonBlock width={110} height={15}/><div style={{ marginTop: 10 }}><SkeletonBlock width={180} height={9}/></div><div style={{ marginTop: 14, display: 'grid', gap: 10 }}>{[1,2,3].map((item) => <div className="post-entry" key={item}><SkeletonBlock width="45%" height={13}/><div style={{ marginTop: 8 }}><SkeletonBlock width="70%" height={9}/></div><div style={{ marginTop: 12 }}><SkeletonBlock width={170} height={30} radius={8}/></div></div>)}</div></section>
  </>;

  return <>
    <div className="page-header"><div><div className="page-kicker"><Briefcase size={13}/> Career opportunities</div><h1 className="page-title">Job opportunities</h1><p className="page-description">Search openings using your professional title, experience and domain. Suvacya does not apply for jobs on your behalf.</p></div></div>
    <section className="panel" style={{ padding: 18 }}><div style={{ display: 'flex', gap: 10, alignItems: 'center' }}><input className="input" style={{ flex: 1 }} value={query} onChange={(e) => setQuery(e.target.value)} onKeyDown={(e) => { if (e.key === 'Enter') void onSearch(query); }} placeholder="Search a position, e.g. Product Manager" /><button className="button primary" onClick={() => void onSearch(query)} disabled={loading}><Search size={14}/>{loading ? 'Searching…' : 'Search jobs'}</button></div><div className="jobs-search-context">Profile context is used when the search box is empty. Matching is deterministic and does not use AI.</div></section>
    <section className="panel" style={{ marginTop: 16, padding: 18 }}><div className="panel-head"><div><h2 className="settings-title">Openings</h2><p className="settings-copy">{jobs.length ? jobs.length + ' openings found' : 'No openings returned yet.'}</p></div></div>
      {jobs.length ? jobs.map((job: any) => { const id = job.provider + ':' + job.provider_job_id; const open = expandedId === id; return <article key={id} className="post-entry" style={{ marginTop: 10 }}><div style={{ display: 'flex', justifyContent: 'space-between', gap: 14 }}><div><div style={{ fontWeight: 800, color: '#10233f' }}>{job.title}</div><div style={{ marginTop: 4, fontSize: 12, color: '#5f6f86' }}>{job.company} · {job.location}{job.experience_level ? ' · ' + job.experience_level : ''}</div></div></div><div style={{ marginTop: 9, display: 'flex', gap: 8, flexWrap: 'wrap' }}><button className="button" onClick={() => setExpandedId(open ? null : id)}>{open ? 'Hide description' : 'View description'}</button>{job.application_url ? <a className="button primary" href={job.application_url} target="_blank" rel="noopener noreferrer">Apply externally <ExternalLink size={13}/></a> : null}</div>{open ? <div style={{ marginTop: 12, color: '#334b66', fontSize: 12, lineHeight: 1.7, whiteSpace: 'pre-wrap' }}>{job.description || 'No description supplied by the source.'}</div> : null}</article>; }) : <EmptyState icon={Briefcase} title="No jobs to show yet" text="Try a broader search or check again later." />}
    </section>
  </>;
}
function FeedbackView({ type, setType, subject, setSubject, description, setDescription, context, setContext, sending, onSubmit }: any) {
  return <>
    <div className="page-header"><div><div className="page-kicker"><MessageSquare size={13}/> Product feedback</div><h1 className="page-title">Help shape Suvacya</h1><p className="page-description">Suggest a feature, report a bug, or tell us what would make the product more useful.</p></div></div>
    <section className="panel settings-card"><div className="profile-grid"><div className="form-group"><label className="form-label">Type</label><select className="input" value={type} onChange={(e) => setType(e.target.value)}><option value="FEATURE">Feature / improvement</option><option value="BUG">Bug report</option><option value="GENERAL">General feedback</option><option value="OTHER">Other</option></select></div><div className="form-group"><label className="form-label">Subject</label><input className="input" value={subject} onChange={(e) => setSubject(e.target.value)} placeholder="Short summary" /></div></div><div className="form-group" style={{ marginTop: 14 }}><label className="form-label">Description</label><textarea className="textarea" value={description} onChange={(e) => setDescription(e.target.value)} placeholder="What happened or what would you like to see?" rows={7} /></div><div className="form-group" style={{ marginTop: 14 }}><label className="form-label">Context (optional)</label><input className="input" value={context} onChange={(e) => setContext(e.target.value)} placeholder="What were you trying to do?" /></div><button className="button primary" style={{ marginTop: 14 }} onClick={onSubmit} disabled={sending || !subject.trim() || !description.trim()}>{sending ? 'Sending…' : 'Submit feedback'} <ArrowUpRight size={13}/></button></section>
  </>;
}

function AdminView({ overview, activity, feedback, users, aiProviders, jobProviders, sections, sectionLoading, onToggle, onRefresh }: any) {
  if (!overview) return <div className="admin-page">
    <div className="page-header"><div><SkeletonBlock width={130} height={10}/><div style={{ marginTop: 10 }}><SkeletonBlock width={310} height={28}/></div><div style={{ marginTop: 9 }}><SkeletonBlock width={520} height={10}/></div></div><SkeletonBlock width={82} height={34} radius={9}/></div>
    <div className="admin-metric-grid">{[1,2,3,4].map((item) => <div className="admin-metric-card" key={item}><SkeletonBlock width="48%" height={10}/><div style={{ marginTop: 15 }}><SkeletonBlock width="35%" height={25}/></div></div>)}</div>
    {[1,2,3,4,5].map((item) => <section className="panel admin-section-card" key={item}><div className="admin-section-loading"><SkeletonBlock width={180} height={14}/></div></section>)}
  </div>;

  const Section = ({ id, title, eyebrow, children }: any) => {
    const open = !!sections[id];
    return <section className="panel admin-section-card">
      <button type="button" onClick={() => onToggle(id)} aria-expanded={open} className="admin-section-toggle">
        <span>{eyebrow && <span className="admin-section-kicker">{eyebrow}</span>}<span className="admin-section-title">{title}</span></span>
        <ChevronDown size={17} style={{ transform: open ? 'rotate(180deg)' : 'none', transition: 'transform 160ms ease', flexShrink: 0 }} />
      </button>
      {open && <div className="admin-section-body">{sectionLoading[id] ? <div className="post-entry"><SkeletonBlock width="72%" height={12}/><div style={{ marginTop: 10 }}><SkeletonBlock width="94%" height={9}/><div style={{ marginTop: 8 }}><SkeletonBlock width="68%" height={9}/></div></div></div> : children}</div>}
    </section>;
  };
  return <div className="admin-page">
    <div className="page-header admin-page-header"><div><div className="page-kicker"><ShieldAlert size={13}/> Admin operations</div><h1 className="page-title">Operations & reliability</h1><p className="page-description">Open a section only when you need its data; each section loads on demand.</p></div><button className="button admin-refresh-button" onClick={() => void onRefresh()}><RefreshCw size={13}/> Refresh</button></div>
    <div className="admin-metric-grid">
      <div className="admin-metric-card"><div className="admin-metric-top"><span>Successful activity</span><span className="admin-metric-icon"><Activity size={15}/></span></div><strong>{overview?.reliability?.successful_requests ?? 0} / {overview?.reliability?.events ?? 0}</strong><small>successful / total API activity</small></div>
      <div className="admin-metric-card"><div className="admin-metric-top"><span>Failed requests</span><span className="admin-metric-icon"><ShieldAlert size={15}/></span></div><strong>{overview?.reliability?.failed_requests ?? 0}</strong><small>Requests requiring attention</small></div>
      <div className="admin-metric-card"><div className="admin-metric-top"><span>Users</span><span className="admin-metric-icon"><UserRound size={15}/></span></div><strong>{overview?.users?.total ?? 0}</strong><small>Accounts in the workspace</small></div>
      <div className="admin-metric-card"><div className="admin-metric-top"><span>Open feedback</span><span className="admin-metric-icon"><MessageSquare size={15}/></span></div><strong>{overview?.feedback?.open ?? 0}</strong><small>Feedback awaiting review</small></div>
    </div>
    <Section id="ai-providers" title="AI providers" eyebrow="PROVIDER READINESS"><div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>{Object.entries(aiProviders?.configured || {}).map(([k,v]: any) => <span className="tag" key={k}>{k} · {v ? 'configured' : 'not configured'}</span>)}</div></Section>
    <Section id="job-providers" title="Job providers" eyebrow="PROVIDER READINESS"><div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>{Object.entries(jobProviders?.configured || {}).map(([k,v]: any) => <span className="tag" key={k}>{k} · {v ? 'available' : 'not configured'}</span>)}</div></Section>
    <Section id="failures" title="Failed requests" eyebrow="OBSERVABILITY">{activity.length ? activity.slice(0, 30).map((x:any) => <div className="post-entry" key={x.id} style={{ marginTop: 8 }}><b>{x.activity_type}</b> · {x.failure_category || 'UNKNOWN'} · {x.http_status || '—'} · {x.latency_ms ?? 0}ms<div style={{ marginTop: 4, color: '#6f7f93' }}>Correlation #{x.correlation_id}</div>{x.details && Object.keys(x.details).length > 0 && <div style={{ marginTop: 5, color: '#5f6f86' }}>{JSON.stringify(x.details)}</div>}</div>) : <div className="post-entry" style={{ color: '#6f7f93' }}>No failed requests recorded.</div>}</Section>
    <Section id="feedback" title="Feedback inbox" eyebrow="PRODUCT FEEDBACK">{feedback.length ? feedback.slice(0, 30).map((x:any) => <div className="post-entry" key={x.id} style={{ marginTop: 8 }}><b>{x.type}</b> · {x.subject} · {x.status} · {x.priority}<div style={{ marginTop: 5, color:'#5f6f86' }}>{x.description}</div></div>) : <div className="post-entry" style={{ color: '#6f7f93' }}>No feedback submitted.</div>}</Section>
    <Section id="users" title="Users" eyebrow="ACCOUNT DIRECTORY">{users.length ? users.slice(0, 30).map((x:any) => <div className="post-entry" key={x.id} style={{ marginTop: 8 }}>{x.display_name || 'User'} · {x.email} · <b>{x.role}</b> · {x.active ? 'active' : 'inactive'}</div>) : <div className="post-entry" style={{ color: '#6f7f93' }}>No users found.</div>}</Section>
  </div>;
}
