from pathlib import Path
import olefile,struct,json,sys,re
sys.stdout.reconfigure(encoding='utf-8');p=Path('standards/_provenance');o=olefile.OleFileIO(p/'S17_ndrc_original.doc');w=o.openstream('WordDocument').read();flags=struct.unpack_from('<H',w,10)[0];table_name='1Table' if flags&0x0200 else '0Table';table=o.openstream(table_name).read();fc,lcb=struct.unpack_from('<II',w,0x1A2);clx=table[fc:fc+lcb];print('flags',hex(flags),'table',table_name,'fc',fc,'lcb',lcb,'head',clx[:30]);i=0
while clx[i]==1:
 cb=struct.unpack_from('<H',clx,i+1)[0];i+=3+cb
assert clx[i]==2
size=struct.unpack_from('<I',clx,i+1)[0];data=clx[i+5:i+5+size];assert len(data)==size and (size-4)%12==0;n=(size-4)//12;cps=struct.unpack_from('<'+'I'*(n+1),data,0);pieces=[]
for k in range(n):
 cnt=cps[k+1]-cps[k];pcd=data[4*(n+1)+8*k:4*(n+1)+8*(k+1)];v=struct.unpack_from('<I',pcd,2)[0];compressed=bool(v&0x40000000);off=v&0x3fffffff
 if compressed:off//=2;raw=w[off:off+cnt];text=raw.decode('cp1252',errors='replace')
 else:raw=w[off:off+cnt*2];text=raw.decode('utf-16le')
 assert len(raw)==cnt*(1 if compressed else 2);pieces.append(text)
text=''.join(pieces);ccpText=struct.unpack_from('<I',w,0x4c)[0];main=text[:ccpText];print('pieces',n,'cp_end',cps[-1],'ccpText',ccpText,'chars',len(main));print(main[:300]);print(main[-1500:]);(p/'S17_ole_maintext_raw.txt').write_text(main,encoding='utf-8');clean=main.replace('\r','\n').replace('\x0b','\n').replace('\x0c','\n').replace('\x07','\t');name='电力现货市场基本规则（公开征求意见稿）_2026年10月_OLE正文提取_仅供参考.txt';header='【仅供参考的正文提取】\n来源：国家发展改革委官方原始.doc（2026年10月19日公开征求意见稿）。\n本文件依MS-DOC的FIB/CLX/PlcPcd提取主文档字符；不保留原格式、自动条号、表格布局及域值，不能替代原件。\n原件本机Word打开失败，兼容性限制已保留。\nMS-DOC提取依据：https://learn.microsoft.com/en-us/openspecs/office_file_formats/ms-doc/01d5d8c4-cf9c-4ef9-80fd-439e763cfe01\n\n';(Path('standards')/name).write_text(header+clean,encoding='utf-8');info=dict(ole_parsing_issues=[str(x) for x in o.parsing_issues],table_stream=table_name,pieces=n,cp_end=cps[-1],main_character_count=ccpText,extracted_character_count=len(main),title_present='电力现货市场基本规则' in main,ending=main[-1000:],word_open_test='failed: Office 检测到此文件存在一个问题；未改变信任中心、未禁用文件验证。',reference_text_file=name,limitations='参考文本不保留自动编号、页码、格式、域值与表格布局。');(p/'S17_extraction_verification.json').write_text(json.dumps(info,ensure_ascii=False,indent=2),encoding='utf-8')
