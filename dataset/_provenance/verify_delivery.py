"""Independent final size/hash/format checks, without executing downloaded code."""
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import hashlib,json,shutil,zipfile,logging
from pypdf import PdfReader

parser_warnings=[]
class CaptureParserWarnings(logging.Handler):
    def emit(self,record):parser_warnings.append(record.getMessage())
pdf_logger=logging.getLogger('pypdf')
pdf_logger.handlers=[CaptureParserWarnings()]
pdf_logger.propagate=False

ROOT=Path(__file__).resolve().parents[2]
DATA=ROOT/'dataset'
index=json.loads((DATA/'_provenance'/'manifest_all_sources.json').read_text(encoding='utf-8'))
standards=json.loads((ROOT/'standards'/'_provenance'/'manifest_standards.json').read_text(encoding='utf-8'))
expected={}
for source in index['sources']:
    for f in source.get('files',[])+source.get('evidence_files',[]):
        path=DATA/f['path']
        expected[str(path)]={'id':source['id'],'path':str(path.relative_to(ROOT)),'bytes':f.get('bytes'),'sha256':f.get('sha256')}
for source in standards:
    for i,name in enumerate(source['files']):
        path=ROOT/'standards'/name
        expected[str(path)]={'id':source['id'],'path':str(path.relative_to(ROOT)),'bytes':source.get('bytes')if i==0 else None,'sha256':source.get('sha256')if i==0 else None,'pdf_pages':source.get('pages')if i==0 else None}

def check(pair):
    path,exp=pair;p=Path(path);out={**exp,'errors':[]}
    if not p.is_file():out['errors'].append('missing');return out
    size=p.stat().st_size;out['actual_bytes']=size
    if exp['bytes']is not None and size!=exp['bytes']:out['errors'].append('size_mismatch')
    h=hashlib.sha256()
    with p.open('rb')as f:
        for b in iter(lambda:f.read(8*1024*1024),b''):h.update(b)
    out['actual_sha256']=h.hexdigest()
    if exp['sha256'] and exp['sha256']!=out['actual_sha256']:out['errors'].append('hash_mismatch')
    if p.suffix.lower()=='.pdf':
        try:
            r=PdfReader(p);out['actual_pdf_pages']=len(r.pages)
            if exp.get('pdf_pages')and exp['pdf_pages']!=len(r.pages):out['errors'].append('pdf_page_count_mismatch')
        except Exception as e:out['errors'].append('pdf_parse_error: '+str(e))
    if p.suffix.lower()=='.zip':
        try:
            with zipfile.ZipFile(p)as z:out['zip_members']=len(z.infolist());out['zip_uncompressed_bytes']=sum(m.file_size for m in z.infolist())
        except Exception as e:out['errors'].append('zip_directory_error: '+str(e))
    return out

results=[]
with ThreadPoolExecutor(max_workers=4)as pool:
    for future in as_completed([pool.submit(check,item)for item in expected.items()]):results.append(future.result())
errors=[r for r in results if r['errors']]
usage=shutil.disk_usage(ROOT)
report={'verified_utc':datetime.now(timezone.utc).isoformat(),'dataset_summary':index['summary'],'dataset_source_count':len(index['sources']),'standards_source_count':len(standards),'checked_files':len(results),'checked_bytes':sum(r.get('actual_bytes',0)for r in results),'errors':errors,'warnings_from_index':index['warnings'],'pdf_parser_warnings':sorted(set(parser_warnings)),'disk_free_bytes':usage.free,'policy':'Recomputed actual SHA256 and sizes for originals and named evidence; parsed PDFs and ZIP directories. Nonfatal source-PDF object-offset warnings retained separately. Archive extraction CRC/member verification is separately retained in each acquisition manifest. No downloaded scripts executed or pickle deserialized.','files':sorted(results,key=lambda r:r['path'])}
path=DATA/'_provenance'/'delivery_verification.json';path.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({k:v for k,v in report.items()if k!='files'},ensure_ascii=True,indent=2))
raise SystemExit(1 if errors or index['warnings']else 0)
