from pathlib import Path
import json,re,hashlib,sys,fitz
from pypdf import PdfReader
sys.stdout.reconfigure(encoding='utf-8');p=Path('standards/_provenance');items=json.loads((p/'manifest_standards.json').read_text(encoding='utf-8'))
for id,src,url,status in [
 ('S03','S03_mirror_response.bin','https://kkk.kqqw.com/bzgf/BB188984A876717CB20191121vn.pdf','fulltext_downloaded_public_mirror'),
 ('S04','S04_full.pdf','https://hbba.sacinfo.org.cn/portal/download/dad3b1e8b98ce2592cce217014d06fac01164059be7fe4f05be4ee0c44b8fdb2','fulltext_downloaded'),
 ('S05','S05_download.pdf','https://hbba.sacinfo.org.cn/portal/download/dad3b1e8b98ce2592cce217014d06fac4505027e19a89fc2f26b8d60fece7f01','fulltext_downloaded'),
 ('S09','S09_gov.pdf','http://ft.panzhihua.gov.cn/uploadfiles/202108/12/2021081217202347802674.pdf','fulltext_downloaded'),
 ('S10','S10_mirror.pdf','https://23922130.s21i.faiusr.com/61/3/ABUIABA9GAAgkdD5wQYogLDzHA.pdf','fulltext_downloaded_public_mirror')]:
 a=next(a for a in items if a['id']==id);b=(p/src).read_bytes();assert b.find(b'%PDF')<100;name=re.sub(r'[<>:"/\\|?*]','_',a['title']+'_'+a['code'])+'.pdf';out=Path('standards')/name;out.write_bytes(b);d=fitz.open(out);txt='\n'.join(pg.get_text() for pg in d);(p/(id+'_verified_text.txt')).write_text(txt,encoding='utf-8');a.update(status=status,files=[name],download_url=url,pages=len(d),bytes=len(b),sha256=hashlib.sha256(b).hexdigest(),pdf_header_offset=b.find(b'%PDF'),reason='公开全文已下载；PDF页面可解析，保留原始下载字节。'+('原文件PDF头前有33字节发布站提示，未删改。' if id=='S03' else '')+('政府官网公开完整附件，替换早期3页节选。' if id=='S09' else ''));print(id,len(d),len(txt),b[:10])
a=next(a for a in items if a['id']=='S17');b=(p/'S17_doc.doc').read_bytes();t=b.decode('utf-16le',errors='ignore');print('S17 binary',b[:8],len(b),'title',a['title'][:10] in t,'first',t.find('第一条'),'last',t.find('第一百'));print(t[t.find('电力现货'):t.find('电力现货')+200]);name=re.sub(r'[<>:"/\\|?*]','_',a['title']+'_2026年10月公开征求意见稿')+'.doc';(Path('standards')/name).write_bytes(b);a.update(status='fulltext_downloaded_draft',files=[name],download_url='https://picpolicy.mofcom.gov.cn/file/20261020/20261020163423512.doc',landing_url='https://policy.mofcom.gov.cn/claw/opinionInfo.shtml?id=7690',bytes=len(b),sha256=hashlib.sha256(b).hexdigest(),reason='商务部全球法规网转载的公开征求意见稿原始Word附件；OLE文件魔数、中文标题和条文内容已核。仅草案，不作为现行运行依据。')
(p/'manifest_standards.json').write_text(json.dumps(items,ensure_ascii=False,indent=2),encoding='utf-8')
