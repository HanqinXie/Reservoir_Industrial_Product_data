"""Download the assigned catalogue sources; preserve originals and audit metadata."""
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import hashlib, json, re, shutil, stat, time, zipfile, posixpath
from urllib.parse import urljoin, urlparse
import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / 'dataset'
CAT = next(ROOT.glob('*/03_data_catalog.md')).read_text(encoding='utf-8-sig')
RECORDS = {}
for m in re.finditer(r'^### (D\d+) · (.+?)\n(.*?)(?=^### |^## |\Z)', CAT, re.M | re.S):
    identifier, title, body = m.groups()
    RECORDS[identifier] = {'id': identifier, 'title': title, 'source_url': re.search(r'\[官方/原始入口\]\((.*?)\)',body).group(1)}

def write_json(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding='utf-8')

def directory(identifier):
    r = RECORDS[identifier]
    title = re.sub(r'[<>:"/\\|?*]', '_', r['title'])
    p = BASE / (identifier + '_' + title)
    p.mkdir(parents=True, exist_ok=True)
    return p

def digest(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(8*1024*1024),b''): h.update(b)
    return h.hexdigest()

def download(url, path, expected=None, kind=None, params=None):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and (expected is None or path.stat().st_size == expected):
        return {'path':str(path.relative_to(BASE)), 'bytes':path.stat().st_size,'sha256':digest(path),'url':url,'reused':True}
    temp=path.with_name(path.name+'.part')
    headers={'User-Agent':'research-data-acquisition/1.0'}
    offset=temp.stat().st_size if temp.exists() else 0
    if offset: headers['Range']=f'bytes={offset}-'
    with requests.get(url,params=params,headers=headers,stream=True,timeout=(20,90)) as r:
        r.raise_for_status()
        content_type=r.headers.get('content-type','')
        if kind in ('zip','netcdf') and ('html' in content_type or 'json' in content_type):
            raise ValueError('Expected binary data, received '+content_type)
        mode='ab' if offset and r.status_code==206 else 'wb'
        if mode=='wb':offset=0
        total=int(r.headers.get('content-length',0))+offset
        written=offset; last=time.monotonic()
        with temp.open(mode) as f:
            for b in r.iter_content(2*1024*1024):
                if not b:continue
                f.write(b);written+=len(b)
                if time.monotonic()-last>30:
                    print(f'PROGRESS {path.name} {written}/{total}',flush=True);last=time.monotonic()
        if total and written!=total:raise ValueError(f'HTTP size mismatch {written}/{total}')
        if expected and written!=expected:raise ValueError(f'Expected size mismatch {written}/{expected}')
        final_url=r.url
    with temp.open('rb') as f: magic=f.read(8)
    if kind=='zip' and not magic.startswith(b'PK'):raise ValueError('ZIP signature missing')
    if kind=='netcdf' and not (magic.startswith(b'CDF') or magic==b'\x89HDF\r\n\x1a\n'):raise ValueError('NetCDF signature missing')
    temp.replace(path)
    return {'path':str(path.relative_to(BASE)),'bytes':written,'sha256':digest(path),'url':url,'final_url':final_url,'content_type':content_type}

def safe_extract(path):
    dest=path.parent/'extracted'; dest.mkdir(exist_ok=True)
    with zipfile.ZipFile(path) as z:
        links=[]
        for a in z.infolist():
            resolved=(dest/a.filename).resolve()
            if not resolved.is_relative_to(dest.resolve()):
                raise ValueError('Unsafe archive path '+a.filename)
            if (a.external_attr>>16)&0o170000==stat.S_IFLNK:
                target=posixpath.normpath(posixpath.join(posixpath.dirname(a.filename),z.read(a).decode('utf-8')))
                if target.startswith('../') or target.startswith('/') or target not in z.namelist():
                    raise ValueError('External archive symlink '+a.filename)
                links.append((a.filename,target))
        bad=z.testzip()
        if bad:raise ValueError('CRC failure '+bad)
        z.extractall(dest)
        for link,target in links:shutil.copyfile(dest/target,dest/link)
        return {'archive':str(path.relative_to(BASE)),'directory':str(dest.relative_to(BASE)),'members':len(z.infolist()),'crc':'passed','internal_symlinks_materialized':links}

def portal(identifier):
    r=RECORDS[identifier].copy();p=directory(identifier);meta=p/'_provenance'
    slug=urlparse(r['source_url']).path.split('/')[-1]
    host='https://cds.climate.copernicus.eu' if identifier in ['D09','D10'] else 'https://ewds.climate.copernicus.eu'
    u=host+'/api/catalogue/v1/collections/'+slug
    r['files']=[];r['attempts']=[]
    try:
        j=requests.get(u,timeout=(15,60));j.raise_for_status();j=j.json()
        write_json(meta/'catalogue_metadata.json',j)
        for link in j.get('links',[]):
            if link.get('rel') in ('form','license'):
                name='download_form.json' if link['rel']=='form' else ('data_licence.pdf' if urlparse(link['href']).path.endswith('.pdf') else 'data_licence.html')
                try: r['files'].append(download(link['href'],meta/name))
                except Exception as e:r['attempts'].append({'url':link['href'],'error':str(e)})
        r.update(status='requires_account_and_subset',reason='未发现本机CDS/EWDS API凭据；须账户登录并接受该数据条款后提交区域和时段请求。已保存元数据与许可，未下载气象/流量数据。',scope='用户指定云南及相关上游流域；尚未提交检索任务。')
    except Exception as e:r.update(status='metadata_failed',reason=str(e))
    (p/'下载状态.md').write_text('# '+r['title']+'\n\n'+r['reason']+'\n\n官方入口：'+r['source_url']+'\n\n范围：云南及相关上游流域；需在官方表单明确变量、日期、版本、区域。账号凭据请保存在本机，不写入聊天或本目录。\n',encoding='utf-8')
    write_json(meta/'manifest.json',r);return r

def grdc():
    r=RECORDS['D04'].copy();p=directory('D04');r['files']=[]
    r['files'].append(download(r['source_url'],p/'_provenance'/'官方获取条件.html'))
    soup=BeautifulSoup((p/'_provenance'/'官方获取条件.html').read_bytes(),'html.parser')
    for a in soup.find_all('a',href=True):
        if 'English' in a.get_text():
            r['guide_url']=urljoin(r['source_url'],a['href']);break
    r.update(status='requires_application',reason='官方要求选择测站/区域，填写申请人资料与邮箱并同意使用条款，数据下载链接通过邮件提供。未代填身份或发送申请。未取得测站流量数据。')
    (p/'下载状态.md').write_text('# GRDC\n\n'+r['reason']+'\n\n'+r['source_url']+'\n',encoding='utf-8')
    write_json(p/'_provenance'/'manifest.json',r);return r

def code(identifier,repo,commit,version):
    r=RECORDS[identifier].copy();p=directory(identifier)
    name='PyPSA-China-THU' if identifier=='D26' else 'TSAM'
    r['files']=[download(f'https://codeload.github.com/{repo}/zip/{commit}',p/f'{name}_{version}_{commit[:12]}.zip',kind='zip')]
    r['extraction']=safe_extract(BASE/r['files'][0]['path'])
    r.update(status='downloaded_code',commit=commit,version=version,reason='已下载并解压固定版本源代码；此项为技术方法资料，不是实测数据库。')
    r['files'].append(download(r['source_url'],p/'_provenance'/'原始入口.html'))
    write_json(p/'_provenance'/'manifest.json',r);return r

def shop():
    r=RECORDS['D27'].copy();p=directory('D27');r['files']=[download(r['source_url'],p/'SINTEF_SHOP_water_values.html')]
    soup=BeautifulSoup((p/'SINTEF_SHOP_water_values.html').read_bytes(),'html.parser')
    article=soup.find('article') or soup.find('main')
    (p/'SINTEF_SHOP_water_values_正文.txt').write_text(article.get_text('\n',strip=True),encoding='utf-8')
    r['assets']=[]
    for tag in (article or soup).find_all('img',src=True):
        u=urljoin(r['source_url'],tag['src']);n=Path(urlparse(u).path).name
        try:r['assets'].append(download(u,p/'assets'/n))
        except Exception as e:r.setdefault('attempts',[]).append({'url':u,'error':str(e)})
    r.update(status='downloaded_documentation',reason='已保存指定水价值技术文档正文和图像；不是商业SHOP软件或运行数据。')
    write_json(p/'_provenance'/'manifest.json',r);return r

def grades():
    r=RECORDS['D03'].copy();p=directory('D03');r['files']=[]
    r['files'].append(download(r['source_url'],p/'_provenance'/'GRADES_项目说明.html'))
    ids={'root':'1cNJ1Z4R7fdO1myz5ztJSI9xwqwsAU93e','discharge':'1klgeDr4dWXonGDGaGP_B0wxIyoC7UpeS','runoff':'13BCvmcC4ln2pSW4kILm4r2l7aRugoihQ'}
    listing=[]
    for label,fid in ids.items():
        s=requests.get('https://drive.google.com/drive/folders/'+fid,timeout=(15,60)).text
        m=re.search(r"window\['_DRIVE_ivd'\] = '(.*?)';",s)
        data=json.loads(m.group(1).encode().decode('unicode_escape'))[0]
        for a in data:listing.append({'folder':label,'id':a[0],'name':a[2],'mime':a[3],'bytes':a[13] if len(a)>13 and isinstance(a[13],int) else None})
    write_json(p/'_provenance'/'官方公开文件目录.json',listing)
    r['files'].append(download('https://drive.google.com/uc',p/'GRADES_官方ReadMe.txt',params={'export':'download','id':'1xyy2V_dU7PglhdIid7T9pYfE0k3NDJnB'}))
    target=next(a for a in listing if 'pfaf_04' in a['name'])
    fid=target['id'];session=requests.Session()
    response=session.get('https://drive.google.com/uc',params={'export':'download','id':fid},timeout=(15,60))
    form=BeautifulSoup(response.text,'html.parser').find('form')
    params={x['name']:x.get('value','')for x in form.select('input[name]')}
    try:
        r['files'].append(download(form['action'],p/target['name'],expected=target['bytes'],kind='netcdf',params=params))
        import h5py
        with h5py.File(p/target['name'],'r') as h:r['netcdf_variables']={k:{'shape':list(v.shape),'dtype':str(v.dtype)}for k,v in h.items() if isinstance(v,h5py.Dataset)}
        r.update(status='downloaded_regional_subset',reason='按用户云南及相关上游流域范围下载原始GRADES v01亚洲pfaf04文件。保留原NetCDF无需解压；未下载其他洲和全球格点径流。此为旧版1979–2013；官方页面推荐GRADES-hydroDL，未混用版本。',scope='pfaf04亚洲；1979-01-01至2013-12-31（按原始文件名，实际时间坐标另核）')
    except Exception as e:r.update(status='download_failed',reason=str(e))
    write_json(p/'_provenance'/'manifest.json',r);return r

if __name__=='__main__':
    jobs=[(i,lambda i=i:portal(i))for i in ['D02','D09','D10','D11','D12','D13']]
    jobs.extend([('D04',grdc),('D26',lambda:code('D26','ruikelyu/PyPSA-China-THU','f353474b43e20686c42094b04441372dadb68b0a','main_20261027')),('D27',shop),('D28',lambda:code('D28','FZJ-IEK3-VSA/tsam','009d1496c198e275755c23a6ae7ac143728a4436','v3.2.0')),('D03',grades)])
    results=[]
    with ThreadPoolExecutor(max_workers=5) as pool:
        tasks={pool.submit(fn):i for i,fn in jobs}
        for future in as_completed(tasks):
            i=tasks[future]
            try:r=future.result()
            except Exception as e:r={**RECORDS[i],'status':'download_failed','reason':repr(e)}
            results.append(r);write_json(BASE/'_provenance'/'manifest_root.json',sorted(results,key=lambda r:r['id']))
            print('RESULT',i,r['status'],flush=True)
