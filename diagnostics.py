"""Export only button metadata, never field values, passwords, cookies or POST data."""
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

ACTION_METADATA = r"""() => {
 const norm=s=>(s||'').normalize('NFKC').replace(/\s/g,'');
 const names=['送り状作成','送り状を作成する','新しく作成する'];
 const info=(raw)=>{
   if(!raw)return null;
   const commands=[...raw.matchAll(/submitCommand\s*\(\s*['"]([A-Za-z0-9_-]+)['"]\s*\)/g)].map(m=>m[1]);
   const functions=[...raw.matchAll(/([A-Za-z_$][\w$]*)\s*\(/g)].map(m=>m[1]);
   if(/^\s*javascript:/i.test(raw))return {kind:'javascript',commands,functions};
   try{const u=new URL(raw,location.href);return {kind:u.protocol,origin:u.origin,path:u.pathname.split(';')[0]};}catch{return {kind:'unparsed'};}
 };
 return [...document.querySelectorAll('a,button,img,input[type="button"],input[type="submit"],input[type="image"]')].filter(e=>{
  const label=e.getAttribute('alt')||e.getAttribute('aria-label')||e.getAttribute('title')||(e.tagName==='INPUT'?e.value:e.textContent?.trim())||e.querySelector('img')?.getAttribute('alt')||'';
  return names.includes(norm(label));
 }).map(e=>{
  const a=e.closest('a');const r=e.getBoundingClientRect();const style=getComputedStyle(e);
  return {tag:e.tagName,id:e.id||null,alt:e.getAttribute('alt'),visible:!!e.getClientRects().length,disabled:!!e.disabled,
    rectangle:{x:Math.round(r.x),y:Math.round(r.y),width:Math.round(r.width),height:Math.round(r.height)},
    pointerEvents:style.pointerEvents,parentTag:e.parentElement?.tagName,
    action:info(e.getAttribute('href')||a?.getAttribute('href')),
    ownHandlerFunctions:[...(e.getAttribute('onclick')||'').matchAll(/([A-Za-z_$][\w$]*)\s*\(/g)].map(m=>m[1])};
 });
}"""


def _read_report(path):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return {}


def _write_report(path, report):
    path=Path(path)
    path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_suffix('.tmp')
    temp.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    os.chmod(temp,0o600)
    temp.replace(path)


class DiagnosticJournal:
    def __init__(self, output, build):
        self.path=Path(output)/'diagnostic-main-menu.json'
        _write_report(self.path,{'build':build,'stage':'startup','events':[],'controls':[]})
        self.event('startup')

    def event(self, stage, **details):
        report=_read_report(self.path)
        report['stage']=stage
        report.setdefault('events',[]).append({'time':datetime.now(timezone.utc).isoformat(),'stage':stage,**details})
        report['events']=report['events'][-100:]
        try:
            _write_report(self.path,report)
        except OSError as error:
            print('诊断文件更新失败：'+type(error).__name__+'；路径：'+str(self.path))


def reveal_report(path):
    if sys.platform=='darwin':
        try:
            subprocess.Popen(['open','-R',str(path)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        except OSError:
            pass


def write_menu_diagnostic(page, output, error, pages=(), attempts=()):
    def safe_location(url):
        value=urlsplit(url)
        return value.scheme+'://'+value.netloc+value.path.split(';')[0]
    path=Path(output)/'diagnostic-main-menu.json'
    report=_read_report(path)
    report.update({'page':safe_location(page.url),'exceptionType':type(error).__name__ if error is not None else None,'attempts':list(attempts),'windows':[]})
    if hasattr(error,'last'):
        report['lastStages']=error.last
    # Native menu click errors contain selectors, not credential-entry values.
    message=re.sub(r'https?://\S+','[网址已省略]',str(error) if error is not None else '')
    message=re.sub(r'value=[\"\'][^\"\']*[\"\']','value=[已省略]',message)
    report['error']=message[:600]
    # Persist the basic report before trying a possibly failing DOM inspection.
    _write_report(path,report)
    try:
        controls=page.evaluate(ACTION_METADATA)
        report['controls']=controls
        report['domInspection']='complete'
    except Exception as inspection_error:
        report['domInspection']='failed'
        report['domInspectionErrorType']=type(inspection_error).__name__
    for candidate in pages:
        if urlsplit(candidate.url).hostname in {'www.int-mypage.post.japanpost.jp','int-mypage.post.japanpost.jp'}:
            report['windows'].append(safe_location(candidate.url))
    _write_report(path,report)
    return path
