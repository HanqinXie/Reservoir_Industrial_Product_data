from pathlib import Path
import json,hashlib,fitz,olefile,re,datetime,sys,collections
from PIL import Image,ImageOps,ImageDraw,ImageFont
sys.stdout.reconfigure(encoding='utf-8');p=Path('standards/_provenance');items=json.loads((p/'manifest_standards.json').read_text(encoding='utf-8'));capture=json.loads((p/'mwr_pages_manifest.json').read_text(encoding='utf-8'));verification=[];panels=[]
for a in items:
 id=a['id'];a['verified_at']='2026-10-27';a['code_version']=a['code'];a.setdefault('fulltext_source_type','public_pdf_copy' if 'public_mirror' in a['status'] else 'official_pdf_original');a['verification']={}
 if id=='S17':
  a['fulltext_source_type']='official_word_original';a['download_url']='https://yyglxxbs.ndrc.gov.cn/file-submission/20261019114817661002.doc';a['alternate_identical_url']='https://picpolicy.mofcom.gov.cn/file/20261020/20261020163423512.doc';a['status']='original_fulltext_downloaded_word_compatibility_issue';a['pages']=None;a['pages_metadata_only']=23;a['reason']='发改委原始Word附件与商务部转载附件SHA256一致，OLE全部流解析无异常，可提取10707个主文档字符。本机Microsoft Word因文件验证问题拒绝打开；原件未改，另提供不保留自动编号/格式的参考TXT。仅为2026年10月公开征求意见稿。';a['reference_files']=[json.loads((p/'S17_extraction_verification.json').read_text(encoding='utf-8'))['reference_text_file']];a['verification']=dict(ole_parse='pass',ole_text_characters=10707,word_open='failed; Office detected a problem with the file',source_identical_sha256=True,page_count_rendered=None,page_count_document_metadata=23);continue
 file=Path('standards')/a['files'][0];b=file.read_bytes();assert b.startswith(b'%PDF');assert hashlib.sha256(b).hexdigest()==a['sha256'];d=fitz.open(file);assert len(d)==a['pages'];rendered=0
 for pg in d:
  pix=pg.get_pixmap(matrix=fitz.Matrix(.5,.5));assert pix.width>0 and pix.height>0 and len(pix.samples)>0;rendered+=1
 entry=dict(id=id,file=file.name,pdf_magic=True,sha256_match=True,pages=len(d),pages_rendered=rendered,render_all_pages='pass');verification.append(entry);a['verification']=entry
 samples=[0,len(d)//2,len(d)-1];row=Image.new('RGB',(900,440),'#e8e8e8');draw=ImageDraw.Draw(row);draw.text((8,5),id+' | '+a['code'].replace('—','-')+' | '+str(len(d))+' pages',fill='black')
 for col,k in enumerate(samples):
  pix=d[k].get_pixmap(matrix=fitz.Matrix(.5,.5));im=Image.frombytes('RGB',[pix.width,pix.height],pix.samples);im.thumbnail((290,400));row.paste(im,(col*300+(300-im.width)//2,28));draw.text((col*300+10,423),'PDF page '+str(k+1),fill='black')
 panels.append(row)
for k in range(0,len(panels),4):
 sheet=Image.new('RGB',(900,440*len(panels[k:k+4])),'white')
 for j,row in enumerate(panels[k:k+4]):sheet.paste(row,(0,j*440))
 sheet.save(p/('pdf_contact_'+str(k//4+1)+'.jpg'),quality=88)
for id in ['S02','S18']:
 records=[x for x in capture['pages'] if x['id']==id];a=next(x for x in items if x['id']==id);a['verification']['page_images_count']=len(records);a['verification']['unique_page_image_sha256']=len(set(x['sha256'] for x in records));assert len(records)==a['pages']
(p/'manifest_standards.json').write_text(json.dumps(items,ensure_ascii=False,indent=2),encoding='utf-8');(p/'final_pdf_verification.json').write_text(json.dumps(dict(pdf_count=len(verification),pdf_pages=sum(x['pages'] for x in verification),results=verification),ensure_ascii=False,indent=2),encoding='utf-8')
rows=['# 标准与规则获取说明','', '核验日期：2026-10-27。清单18项均已保存正文文件：17份PDF、1份原始Word；另有1份明确标注的参考TXT。','', '- S02与S18为水利部官方公开阅览全部页图的顺序保存版，分别52页、269页，源图分辨率530×768；文件名已标注“官方在线阅览分页保存”，并非原始矢量PDF附件。','- S01、S03、S06、S07、S08、S10为公开PDF副本，来源已逐项记录；其余9份PDF来自政府/官方平台公开原始附件。','- S17是2026年10月公开征求意见稿，原件来自国家发展改革委，不能视为现行正式规则。原始.doc通过OLE结构解析，但本机Microsoft Word因文件验证问题拒绝打开。另附参考TXT便于阅读，不保留自动条号、原格式、域值和表格布局；原件未更改。','- S03下载源带33字节非PDF前缀。原始字节保存在`_provenance/S03_mirror_response.bin`；交付PDF仅移除该前缀，页面图像未修改。','- 17份PDF均通过PDF魔数、SHA256、页数校验和全部723页的渲染检查。首、中、尾页联系表在`_provenance/pdf_contact_*.jpg`。','', '|编号|名称与编号|获取类型|PDF页数|状态|','|---|---|---|---:|---|']
for a in items:
 kind={'official_pdf_original':'官方PDF原始附件','public_pdf_copy':'公开PDF副本','official_public_reader_page_images':'官方阅览分页保存','official_word_original':'官方Word原始附件'}[a['fulltext_source_type']];rows.append('|'+a['id']+'|'+a['title']+' '+a['code']+'|'+kind+'|'+(str(a['pages']) if a['pages'] is not None else '未渲染；元数据23')+'|'+('Word兼容性限制，附参考TXT' if a['id']=='S17' else '已获取并校验')+'|')
rows+=['','逐项来源、SHA256、页数、版本、获取类型和验证结果见`_provenance/manifest_standards.json`；所有失败尝试与来源网页保留在`_provenance`。',''];(Path('standards')/'获取说明.md').write_text('\n'.join(rows),encoding='utf-8');print('PDF count',len(verification),'pages',sum(x['pages'] for x in verification));print(collections.Counter(a['fulltext_source_type'] for a in items));print('rows',len(items))
