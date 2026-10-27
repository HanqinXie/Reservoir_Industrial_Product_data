from pathlib import Path
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import json
from acquire_root_sources import BASE, RECORDS, directory, write_json, digest

p=directory('D03');r=RECORDS['D03'].copy()
partials=[f for f in p.rglob('*')if f.is_file() and (f.suffix in ['.part','.tmp','.bin'])]
r.update(status='blocked_download_quota',files=[],reason='官方Google Drive亚洲pfaf04文件返回200 HTML，明确提示Quota exceeded。已停止重试；保留.part和.segments用于后续合法续传，分片尚不构成完整NetCDF数据。',scope='计划下载原始GRADES v01亚洲pfaf04（1979–2013）；未取得完整数据文件。',expected_bytes=23780171996,partial_bytes=sum(f.stat().st_size for f in partials))
write_json(p/'_provenance'/'manifest.json',r)
m=BASE/'_provenance'/'manifest_root.json';j=json.loads(m.read_text(encoding='utf-8'));j=[a for a in j if a['id']!='D03']+[r];write_json(m,sorted(j,key=lambda a:a['id']))
(p/'下载状态.md').write_text('# GRADES自然化河流流量\n\n'+r['reason']+'\n\n'+r['source_url']+'\n\n本目录分片不是完整数据，不能改成.nc后用于分析。\n',encoding='utf-8')

p=directory('D27');html=p/'SINTEF_SHOP_water_values.html';backup=p/'_provenance'/'官方原始HTML.html'
if not backup.exists():backup.write_bytes(html.read_bytes())
raw=backup.read_bytes()
soup=BeautifulSoup(raw,'html.parser');article=soup.find('article') or soup.find('main')
for img in article.find_all('img',src=True):img['src']='assets/'+Path(img['src']).name
source=RECORDS['D27']['source_url']
for anchor in article.find_all('a',href=True):
    if anchor['href'] and not anchor['href'].startswith(('#','http:','https:','mailto:','javascript:')):anchor['href']=urljoin(source,anchor['href'])
content='<!doctype html><html lang="en"><meta charset="utf-8"><title>SINTEF SHOP – Water value descriptions</title><style>body{max-width:1050px;margin:32px auto;padding:0 24px;font:17px/1.65 Georgia,serif;color:#222}img{max-width:100%;height:auto}pre{overflow:auto;padding:16px;background:#f3f3f3}table{border-collapse:collapse}td,th{border:1px solid #bbb;padding:8px}a{color:#1859a8}.source{font:14px/1.5 sans-serif;padding:12px;background:#eef3f8}</style><p class="source">Offline copy of <a href="'+source+'">official SINTEF SHOP documentation</a>. Retrieved 2026-10-27. Equations retain the source expressions.</p>'+str(article)+'</html>'
html.write_text(content,encoding='utf-8')
m=p/'_provenance'/'manifest.json';r=json.loads(m.read_text(encoding='utf-8'));f=r['files'][0];f['sha256']=digest(html);f['bytes']=html.stat().st_size;f['processing']='Offline reading HTML generated from official article; image references point to locally downloaded assets. Original HTML retained in _provenance.';write_json(m,r)
m=BASE/'_provenance'/'manifest_root.json';j=json.loads(m.read_text(encoding='utf-8'));j=[a for a in j if a['id']!='D27']+[r];write_json(m,sorted(j,key=lambda a:a['id']))
print('Recorded GRADES quota and repaired SHOP offline images')
