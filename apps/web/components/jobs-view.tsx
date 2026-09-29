'use client';

import { useEffect, useState } from 'react';
import { Briefcase, ChevronDown, ExternalLink, Search } from 'lucide-react';

type SearchParams = { jobTitle?: string; location?: string; experience?: number | ''; page?: number; append?: boolean };
type Props = { jobs: any[]; location: any; query: string; experience: number | ''; loading: boolean; page: number; hasMore: boolean; onSearch: (params?: SearchParams) => Promise<void> };

export default function JobsView({ jobs, location, query, experience, loading, page, hasMore, onSearch }: Props) {
  const [jobTitle, setJobTitle] = useState(query || '');
  const [jobLocation, setJobLocation] = useState(location?.city || '');
  const [years, setYears] = useState<number | ''>(experience ?? '');
  const [expandedId, setExpandedId] = useState<string | null>(null);
  useEffect(() => { if (query) setJobTitle(query); }, [query]);
  useEffect(() => { if (location?.city) setJobLocation(location.city); }, [location?.city]);
  useEffect(() => { setYears(experience ?? ''); }, [experience]);
  const submit = async () => { const title=jobTitle.trim(), locationValue=jobLocation.trim(); if(!title||!locationValue)return; await onSearch({jobTitle:title,location:locationValue,experience:years,page:1}); };
  return <>
    <div className="page-header"><div><div className="page-kicker"><Briefcase size={13}/> Career opportunities</div><h1 className="page-title">Jobs</h1><p className="page-description">Search current openings using a target job title, location and years of experience.</p></div></div>
    <section className="panel" style={{padding:18}}><div className="profile-grid">
      <div className="form-group"><label className="form-label" htmlFor="jobs-target-title">Target job title</label><input id="jobs-target-title" className="input" value={jobTitle} onChange={e=>setJobTitle(e.target.value)} placeholder="e.g. Product Manager"/></div>
      <div className="form-group"><label className="form-label" htmlFor="jobs-location">Location</label><input id="jobs-location" className="input" value={jobLocation} onChange={e=>setJobLocation(e.target.value)} placeholder="e.g. Hyderabad"/></div>
      <div className="form-group"><label className="form-label" htmlFor="jobs-experience">Years of experience</label><input id="jobs-experience" className="input" type="number" min={0} max={60} step={1} value={years} onChange={e=>setYears(e.target.value===''?'':Number(e.target.value))} placeholder="e.g. 5"/></div>
    </div><div style={{marginTop:14,display:'flex',justifyContent:'flex-end'}}><button className="button primary" onClick={()=>void submit()} disabled={loading||!jobTitle.trim()||!jobLocation.trim()}><Search size={14}/>{loading?'Searching…':'Search jobs'}</button></div>
    <div className="jobs-search-context">{location?.source==='ip'&&!query?'Default location detected from your network: '+(location.city||location.country)+'.':'Search uses exactly the fields above and does not use AI.'}</div></section>
    <section className="panel" style={{marginTop:16,padding:18}}><div className="panel-head"><div><h2 className="settings-title">Openings</h2><p className="settings-copy">{jobs.length?jobs.length+' openings shown':'No openings returned yet.'}</p></div></div>
    {loading&&!jobs.length?<div className="empty-state"><div className="empty-icon"><Briefcase size={19}/></div><strong>Loading jobs…</strong><span>Fetching current openings.</span></div>:jobs.length?<div style={{marginTop:12,display:'grid',gap:10}}>{jobs.map((job:any)=>{const open=expandedId===job.id;return <article className="post-entry" key={job.id}>
      <button type="button" onClick={()=>setExpandedId(open?null:job.id)} aria-expanded={open} style={{width:'100%',textAlign:'left',border:0,background:'transparent',padding:0,cursor:'pointer'}}><div style={{display:'flex',justifyContent:'space-between',gap:12,alignItems:'flex-start'}}><div style={{minWidth:0}}><div style={{fontWeight:800,color:'#10233f'}}>{job.title}</div><div style={{marginTop:5,display:'flex',flexWrap:'wrap',gap:8,color:'#5f6f86',fontSize:11}}><span>{job.location||'Location not specified'}</span>{job.experience?<span>{job.experience}</span>:null}<span>{job.source}</span></div></div><ChevronDown size={16} style={{flexShrink:0,transform:open?'rotate(180deg)':'none'}}/></div></button>
      {open?<div style={{marginTop:14,borderTop:'1px solid #e7edf5',paddingTop:14}}><div style={{display:'grid',gap:6,color:'#5f6f86',fontSize:11}}>{job.company?<div><b>Company:</b> {job.company}</div>:null}{job.salary?<div><b>Salary:</b> {job.salary}</div>:null}{job.postedAt?<div><b>Posted:</b> {String(job.postedAt)}</div>:null}</div><div style={{marginTop:12,color:'#334b66',fontSize:12,lineHeight:1.7,whiteSpace:'pre-wrap'}}>{job.description||'No description was supplied by the source.'}</div>{job.applyUrl?<div style={{marginTop:14}}><a className="button primary" href={job.applyUrl} target="_blank" rel="noopener noreferrer">Apply <ExternalLink size={13}/></a></div>:null}</div>:null}
    </article>})}</div>:<div className="empty-state"><div className="empty-icon"><Briefcase size={19}/></div><strong>No jobs to show</strong><span>Try another target job title or location.</span></div>}
    {hasMore&&jobs.length?<div style={{marginTop:16,display:'flex',justifyContent:'center'}}><button className="button" disabled={loading} onClick={()=>void onSearch({jobTitle,location:jobLocation,experience:years,page:page+1,append:true})}>{loading?'Loading…':'Load more'}</button></div>:null}</section>
  </>;
}
