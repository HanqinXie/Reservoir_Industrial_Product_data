from download_official import *
import sys, csv, io, fitz, zipfile
from PIL import Image
import openpyxl,pandas as pd
sys.stdout.reconfigure(encoding='utf-8')
ROOT=BASE/'_provenance'
# Correct publication-directory date versus report-year mismatch for the 2012 bulletin.
p=folder('D14')/'2017年云南省水资源公报_P020260828725401175431.pdf'
if p.exists():p.rename(p.with_name(p.name.replace('2017年','2012年',1)))
rows=json.loads((ROOT/'water_downloads.json').read_text(encoding='utf-8'))
for x in rows:
 if '725401175431' in x.get('file',''):x['file']=x['file'].replace('2017年','2012年',1)
(ROOT/'water_downloads.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8')
# Keep raw original tables and create convenient CSV copies without changing values.
for i in ['D17','D18']:
 for p in folder(i).glob('*全部历史数据表.html'):
  pd.read_html(str(p))[0].to_csv(p.with_suffix('.csv'),index=False,encoding='utf-8-sig')
for i in ['D20','D21']:
 for p in folder(i).glob('*.json'):
  try:
   j=json.loads(p.read_text(encoding='utf-8-sig'));data=j.get('o_cursor',[])
   if data and isinstance(data,list) and isinstance(data[0],dict):
    al=[x for x in data if any(str(x.get(k,'')).lower().startswith('al') for k in ['PRODUCT','PRODUCTID','INSTRUMENTID']) or any('铝' in str(x.get(k,'')) for k in ['VARNAME','VARNAMEEN','PRODUCTNAME'])]
    if al:
     pd.DataFrame(al).to_csv(p.with_name(p.stem+'_铝筛选.csv'),index=False,encoding='utf-8-sig')
  except Exception:pass
# Rename extensionless official attachments according to their magic bytes.
for i in ['D16','D22']:
 for p in folder(i).iterdir():
  if p.is_file() and not p.suffix:
   b=p.read_bytes()
   if b[:4]==b'%PDF':p.rename(p.with_suffix('.pdf'))
   elif zipfile.is_zipfile(p):
    with zipfile.ZipFile(p) as z:isdocx=any(n.startswith('word/') for n in z.namelist())
    if isdocx:p.rename(p.with_suffix('.docx'))
   elif b.startswith(bytes.fromhex('D0CF11E0A1B11AE1')):p.rename(p.with_suffix('.doc'))
sources={
'D14':'https://wcb.yn.gov.cn/szygb_0/','D15':'https://data.stats.gov.cn/','D16':'https://stats.yn.gov.cn/','D17':'https://international-aluminium.org/statistics/primary-aluminium-smelting-energy-intensity/','D18':'https://international-aluminium.org/statistics-overview/','D19':'https://www.cninfo.com.cn/','D20':'https://www.shfe.com.cn/reports/tradedata/dailyandweeklydata/','D21':'https://www.shfe.com.cn/services/delivery/warehousewarrant1/','D22':'https://ynb.nea.gov.cn/','D23':'https://www.95598.csg.cn/','D29':'https://big5.sse.com.cn/site/cht/www.sse.com.cn/disclosure/fund/announcement/c/new/2026-07-06/508096_20260706_GW8D.pdf'}
scope={
'D14':'已下载官网列示2000—2025年公报正文，2000—2020年PDF及527个在线正文图表图片。保存原始HTML和改写图片路径的离线版。部分源页面含失效file:///本地图片引用，原样记录；各年公报可与所附PDF交叉核验。',
'D15':'从已迁移的新国家数据门户公开API真实取得云南1991—2025年度发电量、水力/火力发电量，以及请求1998-01—2026-09范围的月度发电、水电、氧化铝和铝材产量原始JSON与展开CSV；包含当期/累计/同比等独立指标。缺失值保留为空，各指标实际非空起止期不同，不补造。未在所查分省年度/月度目录取得电解铝产量；氧化铝与铝材不能代替电解铝。另存2025全国统计公报。旧easyquery 403仅为旧接口失败，不再表示整个国家数据不可得。',
'D16':'2025云南统计年鉴完整ZIP及全部70个压缩成员已CRC检查并解压；含工业与能源XLSX。另下载官网可得2019—2023、2025年统计公报正文。2024年目录跳转微信，未计为取得正文。',
'D17':'取得IAI当前官网ALVIS API完整响应以及Export All Data的CSV/XLSX，覆盖1980—2025、各区域AC和DC能耗强度；同时保留官方archive历史数据表HTML/CSV与IEA转载2000—2020能耗CSV。归档与当前数据分别保存，不拼接。官方CSV使用分号分隔。',
'D18':'取得IAI原铝产量当前官网ALVIS API完整响应以及Export All Data的CSV/XLSX，覆盖1973-01—2026-09各区域；保留官方archive历史数据表HTML/CSV。统计总入口包含其他行业序列，本次下载与研究有关的原铝产量，不代表全站全部统计。官方CSV使用分号分隔。',
'D19':'云铝股份000807的2025年完整年度报告，巨潮官方披露1225043142，188页。完整报告已经标题和页数核验。',
'D20':'2015—2025年度期货统计、2022—2025年48个月期货行情和2026-10-26日行情原始JSON，以及可识别铝合约的CSV副本；此为明确范围的公开数据，非无限历史全库。',
'D21':'2022—2025年每月末周五库存周报样本（节假日缺失保留404记录）；2026-10-23铝库存周报和2026-10-26铝仓单日报。历史JSON含全品种，另存可识别铝品种CSV。月末样本不冒充连续周度序列。',
'D22':'南方区域电力市场运行规则（试行，2025年V1.0版）54页PDF及云南监管办公开政策页面/附件。其他征求意见稿按原题名保存，不视为正式实施规则；未取得主体逐时报价和完整成交数据。',
'D23':'实际企业电费账单、计量点与电量记录需要主体账户或授权；本次没有该授权，未读取私人账户、未取得账单/计量数据。',
'D29':'清单指定公开PDF：中航京能国际能源封闭式基础设施证券投资基金更新的招募说明书（2026年第5号），2026年7月，859页。'}
status={i:'partial_downloaded' for i in NAMES};status.update(D19='downloaded',D29='downloaded',D17='downloaded',D23='requires_authorization')
urlmap={x['file'].replace('\\','/'):x['url'] for x in rows if 'file' in x}
for l in (ROOT/'official_requests.jsonl').read_text(encoding='utf-8').splitlines():
 try:
  x=json.loads(l)
  if 'file' in x:urlmap[x['file'].replace('\\','/')]=x.get('url')
 except Exception:pass
urlmap.update({str(next(folder('D19').glob('*.pdf')).relative_to(BASE)).replace('\\','/'):'https://static.cninfo.com.cn/finalpage/2026-03-28/1225043142.PDF',str(next(folder('D16').glob('*.zip')).relative_to(BASE)).replace('\\','/'):'https://www.yn.gov.cn/sjfb/tjnj_2/202606/P020260626373849283283.zip'})
urlmap[(folder('D22')/'南方区域电力市场运行规则_试行_2025年V1.0版.pdf').relative_to(BASE).as_posix()]='https://nfj.nea.gov.cn/hdhy/zlxz/202506/P020250625360641274024.pdf'
urlmap[(folder('D29')/'中航京能REIT_2026年更新招募说明书_508096_20260706.pdf').relative_to(BASE).as_posix()]=sources['D29']
urlmap[(folder('D15')/'中华人民共和国2025年国民经济和社会发展统计公报.html').relative_to(BASE).as_posix()]='https://www.stats.gov.cn/sj/zxfbhjd/202602/t20260228_1962662.html'
def fileinfo(p):
 b=p.read_bytes();rel=p.relative_to(BASE).as_posix();f={'path':rel,'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest(),'source_url':urlmap.get(rel),'file_type':p.suffix.lower().lstrip('.') or 'unknown'}
 if not f['source_url']:
  if '2025云南统计年鉴_解压/' in rel:
   f['source_url']='https://www.yn.gov.cn/sjfb/tjnj_2/202606/P020260626373849283283.zip';f['archive_member']=rel.split('2025云南统计年鉴_解压/',1)[1]
  elif 'IEA转载IAI' in p.name:f['source_url']='https://www.iea.org/data-and-statistics/charts/energy-intensity-of-primary-aluminium-smelting-by-region-2000-2020'
  else:
   candidates=[rel.replace('_离线版.html','.html'),rel.replace('_铝筛选.csv','.json'),rel.replace('_原表展开.csv','_官方原始数据.json'),rel.removesuffix(p.suffix),str(p.with_suffix('.html').relative_to(BASE)).replace('\\','/')]
   for c in candidates:
    if urlmap.get(c):f['source_url']=urlmap[c];f['derived_from']=c;break
 if not f['source_url']:f['source_url']=sources[rel[:3]]
 try:
  ext=p.suffix.lower()
  if b.startswith(b'%PDF'):
   d=fitz.open(p);f.update(file_type='pdf',page_count=d.page_count,validation='PDF parsed',title_excerpt=d[0].get_text()[:220])
  elif ext=='.zip':
   z=zipfile.ZipFile(p);bad=z.testzip();f.update(member_count=len(z.infolist()),zip_crc_ok=bad is None,validation='ZIP CRC checked')
  elif ext=='.xlsx':
   w=openpyxl.load_workbook(p,read_only=True,data_only=False);f.update(sheet_count=len(w.sheetnames),validation='XLSX opened');w.close()
  elif ext in ['.png','.jpg','.jpeg','.gif','.webp','.bmp']:
   im=Image.open(p);f.update(image_format=im.format,width=im.width,height=im.height);im.verify();f['validation']='image decoded'
  elif ext=='.json':
   j=json.loads(b.decode('utf-8-sig'));f.update(validation='JSON parsed',top_keys=list(j)[:12] if isinstance(j,dict) else None)
   if isinstance(j,dict) and 'report_date' in j:f['report_date']=j['report_date']
  elif ext=='.csv':
   t=b.decode('utf-8-sig');delim=';' if ';' in t.splitlines()[0] else ',';rr=list(csv.reader(io.StringIO(t),delimiter=delim));f.update(validation='CSV parsed',delimiter=delim,row_count=max(0,len(rr)-1),column_count=len(rr[0]) if rr else 0)
  elif ext=='.html':
   s=BeautifulSoup(b,'html.parser');f.update(validation='HTML parsed',table_count=len(s.select('table')),text_chars=len(s.get_text(' ',strip=True)))
  else:f['validation']='file preserved'
 except Exception as e:f['validation_error']=str(e)
 return f
manifest=[]
for i in NAMES:
 folder(i)
 doc={'id':i,'title':NAMES[i],'directory':folder(i).name,'status':status[i],'source_url':sources[i],'scope':scope[i],'reason':scope[i],'retrieved_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'files':[]}
 for p in sorted(folder(i).rglob('*')):
  if p.is_file() and p.name not in ['README_下载范围与限制.md','_provenance.json']:doc['files'].append(fileinfo(p))
 doc['file_count']=len(doc['files']);doc['total_bytes']=sum(x['bytes'] for x in doc['files'])
 (folder(i)/'README_下载范围与限制.md').write_text(f"# {i} {NAMES[i]}\n\n状态：{status[i]}\n\n{scope[i]}\n\n原始入口：{sources[i]}\n\n文件尺寸、SHA-256和类型核验见本目录`_provenance.json`。门户和资料是有范围的下载，不代表完整全站镜像。公开资料仍按发布方条款引用与使用。\n",encoding='utf-8')
 (folder(i)/'_provenance.json').write_text(json.dumps(doc,ensure_ascii=False,indent=2),encoding='utf-8')
 manifest.append(doc)
(ROOT/'manifest_official.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps([{'id':x['id'],'status':x['status'],'files':x['file_count'],'bytes':x['total_bytes'],'errors':[z['path'] for z in x['files'] if 'validation_error' in z]} for x in manifest],ensure_ascii=False,indent=2))
