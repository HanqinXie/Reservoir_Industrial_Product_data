"""Verify acquired scientific files and build per-database manifests."""
import hashlib, json, pathlib, sys, urllib.parse, zipfile
from datetime import datetime, timezone

sys.stdout.reconfigure(encoding='utf-8')
ROOT=pathlib.Path(__file__).resolve().parents[1]
TASKS=json.loads((ROOT/'_provenance/scientific_tasks_final.json').read_text(encoding='utf-8'))
COVERAGE={
 'D01':{'spatial':'China energy-system model regions','version':'Zenodo record 19600477, v1, published 2026-04-16','content':'Complete supplementary data.zip supplied by the study, including hydropower, industrial, demand and technology inputs. No pickle deserialization.'},
 'D05':{'spatial':'China, 3254 reservoirs','version':'Res-CN, Zenodo record 7664489, fixed latest record confirmed during acquisition','content':'All seven publicly listed files: full and intermediate catchments, reservoir states, reservoir locations, shapefiles, English information, validation figures.'},
 'D06':{'spatial':'Global, 41145 barrier points and 35295 reservoir polygons','version':'GDW v1.0, Figshare article 25988293 version 1','content':'Complete global geodatabase and technical documentation. Duplicate shapefile representation omitted.'},
 'D07':{'spatial':'Global','version':'HydroLAKES v1.0','content':'Complete global lake polygons and pour points in shapefile format, plus technical documentation. Duplicate geodatabase representation omitted.'},
 'D08':{'spatial':'Global','version':'HydroATLAS v1.0: BasinATLAS, RiverATLAS and LakeATLAS','content':'All three complete global shapefile datasets, technical documentation, and the three attribute catalogs. Duplicate geodatabase representations omitted.'},
 'D24':{'spatial':'China large reservoirs and associated drainage areas','version':'Figshare article 28503167 version 3, CLEAR update log v1.2','content':'All four publicly listed files: Appendix1.xlsx, Appendix2.xlsx, Appendix3.zip, and CLEARv1.2UpdateLog.docx.'},
 'D25':{'spatial':'China, 97435 reservoirs including 5143 documented reservoirs','version':'ScienceDB record V3; CRD v1.1 ZIP; DOI 10.57760/sciencedb.05331','content':'Complete public CRD v1.1.zip obtained through the official public file-tree and download APIs.'}
}

def hashes(p):
    sha=hashlib.sha256();md5=hashlib.md5()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(8*1024*1024),b''):sha.update(b);md5.update(b)
    return sha.hexdigest(),md5.hexdigest()

def main():
    rows=[];checks=[]
    for t in TASKS:
        p=ROOT/t['directory']/t['name']
        mf=ROOT/t['directory']/'_provenance'/(t['name']+'.manifest.json')
        issues=[]
        if not p.is_file() or not mf.is_file():
            checks.append({'id':t['id'],'name':t['name'],'status':'incomplete','issues':['file or download manifest missing']});continue
        r=json.loads(mf.read_text(encoding='utf-8'))
        if r['status'] not in ['downloaded','downloaded_and_extracted']:issues.append('download manifest not successful')
        sha,md5=hashes(p)
        if sha!=r.get('sha256'):issues.append('SHA256 differs from acquisition manifest')
        if t.get('expected_md5') and md5!=t['expected_md5']:issues.append('MD5 differs from official repository')
        if t.get('expected_bytes') and p.stat().st_size!=t['expected_bytes']:issues.append('size differs from official metadata')
        if p.stat().st_size!=r.get('byte_size'):issues.append('size differs from acquisition manifest')
        r.update(title=t.get('title') or t['directory'][4:], expected_bytes=t.get('expected_bytes'), expected_md5=t.get('expected_md5'), official_md5_verified=bool(t.get('expected_md5')), path=str(p.relative_to(ROOT)))
        if r.get('resolved_url'):
            u=urllib.parse.urlsplit(r['resolved_url'])
            if 'amazonaws.com' in u.netloc:r['resolved_url']=urllib.parse.urlunsplit((u.scheme,u.netloc,u.path,'',''))
        if p.suffix.lower()=='.zip':
            ext=r.get('extraction',{})
            if ext.get('status')!='extracted_verified_crc':issues.append('ZIP extraction has not completed')
            recorded=ext.get('members',[])
            with zipfile.ZipFile(p) as z:
                members=[i for i in z.infolist() if not i.is_dir()]
                if len(members)!=len(recorded):issues.append('extraction member count differs from ZIP directory')
                if sum(i.file_size for i in members)!=sum(i['byte_size'] for i in recorded):issues.append('extraction bytes differ from ZIP directory')
            for item in recorded:
                target=(ROOT/item['path']).resolve()
                if not target.is_relative_to(ROOT.resolve()) or not target.is_file() or target.is_symlink() or target.stat().st_size!=item['byte_size']:
                    issues.append('missing, linked, unsafe or wrong-size extraction member: '+item['path'])
        else:
            with p.open('rb') as f: magic=f.read(8)
            if p.suffix.lower()=='.pdf' and not magic.startswith(b'%PDF-'):issues.append('PDF magic signature missing')
            if p.suffix.lower() in ['.xlsx','.docx'] and not magic.startswith(b'PK'):issues.append('Office ZIP container signature missing')
        r['audit_status']='passed' if not issues else 'failed'
        r['audit_utc']=datetime.now(timezone.utc).isoformat()
        mf.write_text(json.dumps(r,ensure_ascii=False,indent=2),encoding='utf-8')
        rows.append(r)
        checks.append({'id':t['id'],'name':t['name'],'status':r['audit_status'],'original_bytes':p.stat().st_size,'extracted_bytes':r.get('extraction',{}).get('uncompressed_bytes',0),'sha256':sha,'official_md5_verified':bool(t.get('expected_md5')),'extraction_member_sizes_verified':len(r.get('extraction',{}).get('members',[])),'issues':issues})
        print(r['audit_status'].upper(),t['id'],t['name'],p.stat().st_size,flush=True)
    groups=[]
    for id in sorted(set(t['id'] for t in TASKS)):
        tasks=[t for t in TASKS if t['id']==id];files=[r for r in rows if r['id']==id]
        g={'id':id,'title':tasks[0].get('title') or tasks[0]['directory'][4:],'directory':tasks[0]['directory'],'status':'complete' if len(files)==len(tasks) and all(r['audit_status']=='passed' for r in files) else 'incomplete','expected_file_count':len(tasks),'verified_file_count':sum(r['audit_status']=='passed' for r in files),'original_bytes':sum(r['byte_size'] for r in files),'extracted_bytes':sum(r.get('extraction',{}).get('uncompressed_bytes',0) for r in files),'files':files}
        (ROOT/tasks[0]['directory']/'manifest.json').write_text(json.dumps(g,ensure_ascii=False,indent=2),encoding='utf-8');groups.append(g)
    summary={'generated_utc':datetime.now(timezone.utc).isoformat(),'status':'complete' if all(g['status']=='complete' for g in groups) else 'incomplete','dataset_count':len(groups),'file_count':len(rows),'original_bytes':sum(r['byte_size'] for r in rows),'extracted_bytes':sum(r.get('extraction',{}).get('uncompressed_bytes',0) for r in rows),'groups':groups,'files':rows}
    (ROOT/'_provenance/manifest_scientific.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    (ROOT/'_provenance/scientific_verification.json').write_text(json.dumps({'generated_utc':summary['generated_utc'],'status':summary['status'],'checks':checks},ensure_ascii=False,indent=2),encoding='utf-8')
    sources=[]
    for g in groups:
        files=[]
        for r in g['files']:
            files.append({'path':pathlib.PureWindowsPath(r['path']).as_posix(),'source_url':r['source_url'],'byte_size':r['byte_size'],'sha256':r['sha256'],'official_md5_verified':r['official_md5_verified'],'status':r['audit_status'],'extraction':{k:v for k,v in r.get('extraction',{}).items() if k!='members'}})
        sources.append({'id':g['id'],'title':g['title'],'status':g['status'],'files':files,'coverage':COVERAGE[g['id']],'reason':'All selected unique publicly listed files downloaded, original archives retained, archive extraction verified.' if g['status']=='complete' else 'One or more expected files or extraction checks are incomplete; see scientific_verification.json.','original_bytes':g['original_bytes'],'extracted_bytes':g['extracted_bytes'],'expected_file_count':g['expected_file_count'],'verified_file_count':g['verified_file_count']})
    (ROOT/'_provenance/manifest_scientific_sources.json').write_text(json.dumps({'generated_utc':summary['generated_utc'],'status':summary['status'],'sources':sources,'expected_source_count':7,'expected_file_count':25},ensure_ascii=False,indent=2),encoding='utf-8')
    print('AUDIT',summary['status'],len(groups),'databases',len(rows),'files','original_bytes',summary['original_bytes'],'extracted_bytes',summary['extracted_bytes'],flush=True)
    if summary['status']!='complete':sys.exit(1)

if __name__=='__main__':main()
