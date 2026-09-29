from __future__ import annotations
import asyncio, html, re
from typing import Any
from urllib.parse import quote_plus
import httpx
from app.core.config import settings

_COUNTRY_DOMAINS={"IN":"in.indeed.com","US":"www.indeed.com","GB":"uk.indeed.com","CA":"ca.indeed.com","AU":"au.indeed.com","DE":"de.indeed.com","FR":"fr.indeed.com","IT":"it.indeed.com","ES":"es.indeed.com","NL":"nl.indeed.com","SG":"sg.indeed.com","JP":"jp.indeed.com"}
_SOURCE_LIMIT=20

def _clean_text(value: Any, limit: int=6000)->str:
    text=html.unescape(str(value or "")); text=re.sub(r"<[^>]+>"," ",text); return re.sub(r"\s+"," ",text).strip()[:limit]
def _normalize_title(value: Any)->str: return re.sub(r"[^a-z0-9]+"," ",_clean_text(value,300).lower()).strip()
def _title_matches(job_title:str, requested_title:str)->bool:
    requested,actual=_normalize_title(requested_title),_normalize_title(job_title); return bool(requested and actual and requested in actual)
def _experience_matches(min_years:Any,max_years:Any,requested:float|None)->bool:
    if requested is None:return True
    try: minimum=float(min_years) if min_years not in (None,"") else None; maximum=float(max_years) if max_years not in (None,"") else None
    except (TypeError,ValueError): return True
    if minimum is None and maximum is None:return True
    return not (minimum is not None and requested<minimum) and not (maximum is not None and requested>maximum)
def _parse_experience_text(value:Any)->tuple[float|None,float|None]:
    text=_clean_text(value,120).lower()
    pair=re.search(r"(\d+(?:\.\d+)?)\s*(?:-|to)\s*(\d+(?:\.\d+)?)\s*(?:years?|yrs?)",text)
    if pair:return float(pair.group(1)),float(pair.group(2))
    plus=re.search(r"(\d+(?:\.\d+)?)\s*\+\s*(?:years?|yrs?)",text)
    if plus:return float(plus.group(1)),None
    single=re.search(r"(\d+(?:\.\d+)?)\s*(?:years?|yrs?)",text)
    if single:return float(single.group(1)),float(single.group(1))
    return None,None
def _indeed_input(title:str,location:dict[str,str],page:int)->dict[str,Any]:
    exact=f'"{title.strip()}"'; country=(location.get("country_code") or "IN").upper(); country=country if country in _COUNTRY_DOMAINS else "IN"; city=location.get("city","").strip()
    if page==1:return {"position":exact,"maxItemsPerSearch":_SOURCE_LIMIT,"country":country,"location":city,"parseCompanyDetails":False,"saveOnlyUniqueItems":True}
    return {"maxItemsPerSearch":_SOURCE_LIMIT,"country":country,"parseCompanyDetails":False,"saveOnlyUniqueItems":True,"startUrls":[{"url":f"https://{_COUNTRY_DOMAINS[country]}/jobs?q={quote_plus(title.strip())}&l={quote_plus(city)}&start={(page-1)*_SOURCE_LIMIT}"}]}
def _naukri_input(title:str,experience:float|None,location:dict[str,str],page:int)->dict[str,Any]:
    city=location.get("city","").strip() or location.get("country","").strip() or "India"; payload={"position":title.strip(),"location":city,"maxItems":min(page*_SOURCE_LIMIT,60),"maxPages":page,"sort":"relevance","proxyConfiguration":{"useApifyProxy":True,"apifyProxyGroups":["RESIDENTIAL"],"apifyProxyCountry":"IN"}
    }
    if experience is not None:payload["experience"]=str(int(experience) if float(experience).is_integer() else experience)
    return payload
def _naukri_fallback_input(title:str,location:dict[str,str],page:int)->dict[str,Any]:
    city=location.get("city","").strip() or location.get("country","").strip() or "India"
    return {"position":title.strip(),"location":city,"maxItems":min(page*_SOURCE_LIMIT,60),"maxPages":page,"sort":"relevance"}
async def _call_actor(actor:str,payload:dict[str,Any])->list[dict[str,Any]]:
    if not settings.apify_api_token:raise RuntimeError("Apify integration is not configured.")
    timeout=max(15,min(int(settings.apify_timeout_seconds),300)); url=f"https://api.apify.com/v2/actors/{actor.replace('/','~')}/run-sync-get-dataset-items"
    async with httpx.AsyncClient(timeout=httpx.Timeout(timeout,connect=5.0)) as client:
        response=await client.post(url,params={"timeout":timeout,"format":"json"},headers={"Authorization":f"Bearer {settings.apify_api_token}","Content-Type":"application/json","Accept":"application/json"},json=payload)
    response.raise_for_status(); data=response.json()
    if not isinstance(data,list):raise RuntimeError("Apify returned an unexpected dataset response.")
    return [item for item in data if isinstance(item,dict)]
def _normalize_indeed(item:dict[str,Any])->dict[str,Any]:
    return {"id":f"indeed:{item.get('id') or item.get('url')}","source":"Indeed","title":_clean_text(item.get("positionName"),300),"company":_clean_text(item.get("company"),220) or None,"location":_clean_text(item.get("location"),300) or None,"experience":_clean_text(item.get("experienceLevel"),120) or None,"description":_clean_text(item.get("description"),10000) or None,"salary":_clean_text(item.get("salary"),180) or None,"postedAt":item.get("postingDateParsed") or item.get("postedAt"),"applyUrl":str(item.get("externalApplyLink") or item.get("url") or ""),"sourceUrl":str(item.get("url") or "")}
def _normalize_naukri(item:dict[str,Any])->dict[str,Any]:
    return {"id":f"naukri:{item.get('jobId') or item.get('url')}","source":"Naukri","title":_clean_text(item.get("title"),300),"company":_clean_text(item.get("employer"),220) or None,"location":_clean_text(item.get("location"),300) or None,"experience":_clean_text(item.get("experienceText"),120) or None,"description":_clean_text(item.get("description"),10000) or None,"salary":_clean_text(item.get("salaryNote"),180) or None,"postedAt":item.get("postedAt") or item.get("postedAtRelative"),"applyUrl":str(item.get("url") or ""),"sourceUrl":str(item.get("url") or ""),"_experienceMin":item.get("experienceMin"),"_experienceMax":item.get("experienceMax")}
def _filter_and_dedupe(jobs:list[dict[str,Any]],title:str,experience:float|None)->list[dict[str,Any]]:
    output=[];seen=set()
    for job in jobs:
        if not _title_matches(job.get("title",""),title):continue
        minimum,maximum=job.pop("_experienceMin",None),job.pop("_experienceMax",None)
        if minimum is None and maximum is None:minimum,maximum=_parse_experience_text(job.get("experience"))
        if not _experience_matches(minimum,maximum,experience):continue
        key=str(job.get("sourceUrl") or job.get("applyUrl") or job.get("id"))
        if not key or key in seen:continue
        seen.add(key);output.append(job)
    return output
async def search_jobs_apify(*,title:str,experience:float|None,location:dict[str,str],page:int=1,limit:int=20)->dict[str,Any]:
    requested_limit,requested_page=min(max(int(limit),1),_SOURCE_LIMIT),max(int(page),1)
    async def call(actor,payload):
        try:return await _call_actor(actor,payload)
        except Exception:return []
    async def call_naukri():
        try:
            return await _call_actor(settings.apify_naukri_actor,_naukri_input(title,experience,location,requested_page))
        except httpx.HTTPStatusError as exc:
            # Some Naukri actor configurations reject optional proxy/experience
            # fields with HTTP 400. Retry once with the actor's minimal stable
            # input; experience is still filtered deterministically below.
            if exc.response.status_code in {400, 422}:
                try:return await _call_actor(settings.apify_naukri_actor,_naukri_fallback_input(title,location,requested_page))
                except Exception:return []
            return []
        except Exception:return []
    indeed_result,naukri_result=await asyncio.gather(
        call(settings.apify_indeed_actor,_indeed_input(title,location,requested_page)),
        call_naukri(),
    )
    indeed=_filter_and_dedupe([_normalize_indeed(x) for x in indeed_result],title,experience);naukri=_filter_and_dedupe([_normalize_naukri(x) for x in naukri_result],title,experience)
    if requested_page>1:naukri=naukri[(requested_page-1)*requested_limit:requested_page*requested_limit]
    combined=_filter_and_dedupe(indeed+naukri,title,experience);start=(requested_page-1)*requested_limit;jobs=combined[start:start+requested_limit]
    # Provider outages or overly strict deterministic matching must never turn
    # a Jobs navigation/search into a 500. An empty result set is a valid
    # user-facing state; provider details remain server-side only.
    return {"query":title,"experience":experience,"location":location,"page":requested_page,"limit":requested_limit,"jobs":jobs,"has_more":len(jobs)==requested_limit}
