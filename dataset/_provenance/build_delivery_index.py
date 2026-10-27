"""Build a reproducible delivery index without changing acquisition manifests.

Rerun with: python dataset/_provenance/build_delivery_index.py
Only completed files in the canonical task directory count as available.
The scientific acquisition/audit programs remain responsible for full hashing.
"""
from __future__ import annotations
import datetime as dt
import json
import pathlib
import re
import sys
from urllib.parse import quote
from zoneinfo import ZoneInfo

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
BASE = pathlib.Path(__file__).resolve().parents[1]
PROV = BASE / '_provenance'
WORKSPACE = BASE.parent
CATALOG = WORKSPACE / '水库_工业库存_研究计划与文献数据标准包_20261026' / '03_data_catalog.md'
UNAVAILABLE = {'D02', 'D03', 'D04', 'D09', 'D10', 'D11', 'D12', 'D13', 'D23'}
SCIENCE_IDS = {'D01', 'D05', 'D06', 'D07', 'D08', 'D24', 'D25'}
WARNINGS: list[str] = []
READ_INPUTS: list[str] = []
SCIENCE_SCOPES = {
 'D01': 'Nature Energy工业过剩产能研究的Zenodo配套数据原始ZIP及解压文件；属于论文模型输入，不能视为具体电站或铝厂实测。',
 'D05': 'Res-CN原始发布记录所列的水库/集水区属性、完整与中间集水区、水库状态、地理表及验证资料。',
 'D06': 'Global Dam Watch v1.0全球坝库File Geodatabase原始ZIP、解压目录和技术说明。',
 'D07': 'HydroLAKES v1.0全球湖库多边形、点Shapefile原始ZIP、解压目录与技术说明。',
 'D08': 'HydroATLAS的BasinATLAS、RiverATLAS、LakeATLAS v1.0全球Shapefile原始ZIP、解压目录、技术文档和目录说明。',
 'D24': 'CLEAR发布记录中的Appendix1.xlsx、Appendix2.xlsx、Appendix3.zip及CLEAR v1.2更新说明；压缩包保留并解压。',
 'D25': 'ScienceDB中国水库数据库CRD v1.1原始ZIP及解压资料。',
}

def read_json(path: pathlib.Path, default=None):
 if not path.is_file():
  return default
 try:
  data = json.loads(path.read_text(encoding='utf-8-sig'))
  READ_INPUTS.append(path.relative_to(BASE).as_posix())
  return data
 except (OSError, ValueError) as e:
  WARNINGS.append(f'{path.name}: {type(e).__name__}: {e}')
  return default

def norm(path) -> str:
 return str(path or '').replace('\\', '/').lstrip('./')

def local_path(path: str) -> pathlib.Path | None:
 try:
  p = (BASE / norm(path)).resolve()
  return p if p.is_relative_to(BASE.resolve()) else None
 except (OSError, ValueError):
  return None

def incomplete_path(path) -> bool:
 p = norm(path).lower()
 return p.endswith(('.part', '.tmp', '.crdownload')) or '.segments/' in p or p.endswith('.segments')

def canonical_file(item: dict, fallback_source=None) -> dict:
 p = norm(item.get('path') or item.get('file'))
 size = item.get('bytes', item.get('byte_size'))
 x = {'path': p, 'bytes': size, 'sha256': item.get('sha256'),
      'source_url': item.get('source_url') or item.get('url') or fallback_source}
 for k in ['name', 'file_type', 'content_type', 'page_count', 'row_count', 'column_count',
           'delimiter', 'validation', 'validation_error', 'md5', 'official_md5_verified',
           'finished_utc', 'audit_status', 'extraction', 'derived_from', 'archive_member']:
  if k in item:
   x[k] = item[k]
 target = local_path(p)
 x['exists'] = bool(target and target.is_file())
 x['size_matches_manifest'] = bool(x['exists'] and (size is None or target.stat().st_size == size))
 return x

def catalog_rows() -> dict:
 rows = {}
 for line in CATALOG.read_text(encoding='utf-8-sig').splitlines():
  if not re.match(r'^\|\s*D\d\d\s*\|', line):
   continue
  cells = [x.strip() for x in line.strip().strip('|').split('|')]
  match = re.search(r'\[([^\]]+)\]\((https?://[^\s]+)\)', cells[-1])
  if match:
   rows[cells[0]] = {'id': cells[0], 'title': match[1], 'source_url': match[2],
                    'priority': cells[1], 'source_type': cells[2]}
 if len(rows) != 29:
  raise ValueError(f'Expected 29 catalog entries, found {len(rows)}')
 return rows

def source_rows(name: str) -> dict:
 data = read_json(PROV / name, [])
 if isinstance(data, dict):
  data = data.get('sources') or data.get('groups') or []
 return {x['id']: x for x in data if isinstance(x, dict) and x.get('id')}

def scientific_records(tasks: list[dict]):
 # Only records matching the current canonical task are candidates. A stale
 # failure for a renamed directory must never override a valid current file.
 expected = {(x['id'], x['name']): x for x in tasks}
 candidates: dict[tuple[str, str], list[dict]] = {}
 def add(record, manifest_name):
  if not isinstance(record, dict):
   return
  key = (record.get('id'), record.get('name'))
  task = expected.get(key)
  if not task or record.get('directory') != task['directory']:
   return
  r = dict(record)
  r['_input_manifest'] = manifest_name
  candidates.setdefault(key, []).append(r)
 for path in sorted(PROV.glob('manifest_scientific*.json')):
  doc = read_json(path, {})
  records = doc.get('files', []) if isinstance(doc, dict) else doc
  for r in records:
   add(r, path.relative_to(BASE).as_posix())
 for task in tasks:
  path = BASE / task['directory'] / '_provenance' / (task['name'] + '.manifest.json')
  record = read_json(path)
  if record:
   add(record, path.relative_to(BASE).as_posix())
 selected = {}
 for key, records in candidates.items():
  selected[key] = max(records, key=lambda r: (r.get('finished_utc') or '',
                  r.get('audit_utc') or '', r.get('started_utc') or ''))
 return selected

def assess_science(task: dict, record: dict | None) -> dict:
 expected_rel = norm(task['directory'] + '/' + task['name'])
 result = {'id': task['id'], 'name': task['name'], 'path': expected_rel,
           'source_url': task['source_url'], 'expected_bytes': task.get('expected_bytes'),
           'status': 'in_progress', 'usable': False, 'issues': []}
 target = local_path(expected_rel)
 if not record:
  result['issues'].append('尚无当前任务的完成记录；文件或分片存在不代表可用。')
  return result
 result['acquisition_status'] = record.get('status')
 result['finished_utc'] = record.get('finished_utc')
 result['input_manifest'] = record.get('_input_manifest')
 if norm(record.get('path')) != expected_rel:
  result['issues'].append('完成记录路径与当前任务规范路径不符。')
 if record.get('status') not in {'downloaded', 'downloaded_and_extracted'} or not record.get('finished_utc'):
  result['issues'].append('下载尚无成功终态。')
 if incomplete_path(expected_rel) or not target or not target.is_file():
  result['issues'].append('完整原始文件缺失。')
 elif task.get('expected_bytes') is not None and target.stat().st_size != task['expected_bytes']:
  result['issues'].append('原始文件大小不符合当前任务元数据。')
 elif record.get('byte_size') is not None and target.stat().st_size != record['byte_size']:
  result['issues'].append('原始文件大小不符合完成记录。')
 if not record.get('sha256'):
  result['issues'].append('未记录SHA-256。')
 if task.get('expected_md5') and not record.get('official_md5_verified'):
  result['issues'].append('尚未确认官方MD5。')
 if task['name'].lower().endswith('.zip'):
  ex = record.get('extraction', {})
  xp = local_path(ex.get('path', ''))
  if record.get('status') != 'downloaded_and_extracted' or ex.get('status') != 'extracted_verified_crc' or not xp or not xp.is_dir():
   result['issues'].append('ZIP尚未完成解压及CRC核验。')
 if record.get('audit_status') == 'failed':
  result['issues'].append('科学数据独立审计未通过。')
 result['usable'] = not result['issues']
 result['status'] = 'available' if result['usable'] else 'in_progress'
 result['file'] = canonical_file(record, task['source_url'])
 return result

def friendly_size(value: int) -> str:
 return f'{value / 1_000_000_000:.2f} GB' if value >= 1_000_000_000 else f'{value / 1_000_000:.1f} MB'

def safe_cell(text):
 return str(text or '').replace('|', '&#124;').replace('\n', ' ').replace('\r', ' ')

def main():
 catalog = catalog_rows()
 root = source_rows('manifest_root.json')
 official = source_rows('manifest_official.json')
 tasks = read_json(PROV / 'scientific_tasks_final.json', [])
 selected = scientific_records(tasks)
 science_summary = read_json(PROV / 'manifest_scientific_sources.json', {}) or read_json(PROV / 'scientific_source_summary.json', {}) or {}
 if isinstance(science_summary, list):
  science_summary = {x['id']: x for x in science_summary}
 elif 'sources' in science_summary or 'groups' in science_summary:
  science_summary = {x['id']: x for x in (science_summary.get('sources') or science_summary.get('groups'))}
 sources = []
 for sid, cat in sorted(catalog.items()):
  doc = dict(cat)
  directories = sorted(p.name for p in BASE.glob(sid + '_*') if p.is_dir())
  doc['directory'] = directories[0] if len(directories) == 1 else None
  doc['files'] = []
  doc['evidence_files'] = []
  if sid in SCIENCE_IDS:
   planned = [x for x in tasks if x['id'] == sid]
   checks = [assess_science(t, selected.get((sid, t['name']))) for t in planned]
   completed = [x for x in checks if x['usable']]
   doc.update(directory=planned[0]['directory'] if planned else doc['directory'],
              category='available' if planned and len(completed) == len(planned) else 'in_progress',
              status='downloaded_and_extracted' if planned and len(completed) == len(planned) else 'in_progress',
              task_count=len(planned), completed_task_count=len(completed), task_checks=checks,
              files=[x['file'] for x in completed],
              scope=SCIENCE_SCOPES[sid],
              acquisition_manifests=sorted(set(x.get('input_manifest') for x in checks if x.get('input_manifest'))))
   summary = science_summary.get(sid)
   if summary:
    doc['scientific_source_summary'] = summary
    doc['scope'] = summary.get('scope') or summary.get('actual_scope') or doc['scope']
   if doc['category'] == 'in_progress':
    done_names = '、'.join(x['name'] for x in completed) or '暂无核验完成文件'
    doc['scope'] = f"计划{len(planned)}个原始文件，已下载并完成所需核验{len(completed)}个。已可用：{done_names}。其余下载/解压/审计进行中。" + doc['scope']
  else:
   src = official.get(sid) or root.get(sid)
   if not src:
    doc.update(category='in_progress', status='no_group_manifest_yet', scope='尚未收到该组的取得范围清单。')
   else:
    doc.update(status=src.get('status'), scope=src.get('scope') or src.get('reason') or '',
               reason=src.get('reason'), directory=src.get('directory') or doc['directory'])
    doc['acquisition_manifests'] = ['_provenance/manifest_official.json' if sid in official else '_provenance/manifest_root.json']
    record_files = list(src.get('files', [])) + list(src.get('assets', []))
    for item in record_files:
     f = canonical_file(item, cat['source_url'])
     is_evidence = '/_provenance/' in f['path'] or incomplete_path(f['path'])
     if is_evidence or sid in UNAVAILABLE:
      doc['evidence_files'].append(f)
     elif f['exists'] and f['size_matches_manifest'] and not item.get('validation_error'):
      doc['files'].append(f)
     else:
      doc['evidence_files'].append(f)
      WARNINGS.append(f"{sid}: 文件缺失/大小不符/格式错误：{f['path']}")
    if sid in UNAVAILABLE:
     doc['category'] = 'unavailable'
    else:
     doc['category'] = 'available' if doc['files'] else 'in_progress'
    if src.get('extraction'):
     doc['extraction'] = src['extraction']
    for key in ['commit', 'version', 'expected_bytes', 'partial_bytes']:
     if key in src:
      doc[key] = src[key]
  # Never promote fragments or a metadata-only entry into an acquired source.
  if sid in UNAVAILABLE:
   doc['category'] = 'unavailable'
   doc['files'] = []
  doc['available_original_file_count'] = len(doc['files'])
  doc['available_original_bytes'] = sum(x.get('bytes') or 0 for x in doc['files'])
  sources.append(doc)
 counts = {cat: sum(x['category'] == cat for x in sources) for cat in ['available', 'in_progress', 'unavailable']}
 generated = dt.datetime.now(dt.timezone.utc).isoformat()
 result = {'schema_version': 1, 'generated_utc': generated,
           'study_region': '用户已选择云南及相关上游流域；全球/全国原始数据保留原覆盖范围，尚未冒充已裁剪的当地实测。',
           'catalog': CATALOG.relative_to(WORKSPACE).as_posix(),
           'coverage_note': '清单含数据库、门户、正式报告与方法文件。有文件取得不等于29个数据库全量下载；未取得私有账单。',
           'selection_policy': '科学组按(id,name)和当前规范目录筛选，finished_utc最新记录优先；与25文件任务逐项核对。仅完整文件且满足尺寸/MD5记录/ZIP解压CRC条件计为可用。分片与元数据不计数据取得。',
           'summary': {**counts, 'source_count': len(sources),
                       'scientific_planned_files': len(tasks),
                       'scientific_completed_files': sum(x.get('completed_task_count', 0) for x in sources),
                       'available_original_file_count': sum(x['available_original_file_count'] for x in sources),
                       'available_original_bytes': sum(x['available_original_bytes'] for x in sources)},
           'input_manifests': sorted(set(READ_INPUTS)), 'warnings': WARNINGS,
           'sources': sources}
 # These assertions test delivery semantics, not acquisition implementation.
 assert len(sources) == len({x['id'] for x in sources}) == 29
 assert sum(counts.values()) == 29
 assert {x['id'] for x in sources if x['category'] == 'unavailable'} == UNAVAILABLE
 assert all(not incomplete_path(f['path']) for s in sources for f in s['files'])
 assert all(f['exists'] and f['size_matches_manifest'] for s in sources for f in s['files'])
 write_json = PROV / 'manifest_all_sources.json'
 temp = write_json.with_suffix('.json.tmp')
 temp.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
 temp.replace(write_json)
 visible_time = dt.datetime.fromisoformat(generated).astimezone(ZoneInfo('Asia/Shanghai')).strftime('%Y-%m-%d %H:%M:%S')
 lines = ['# 数据源下载清单', '',
          f'更新时间：{visible_time}（北京时间，Asia/Shanghai）。已取得资料{counts["available"]}项；进行中{counts["in_progress"]}项；尚未取得所需数据{counts["unavailable"]}项。', '',
          '**研究范围：用户已选择云南及相关上游流域。** 全球/全国原始文件保留发布方覆盖范围，当前没有将其冒充具体电站/企业实测，也未声称已经全部裁剪。', '',
          '29项包含数据库、动态门户、年度报告和方法文档。本清单按实际下载文件区分，门户通常仅部分覆盖；许可、元数据、申请指南和下载分片不计为取得目标数据。', '',
          '原始压缩包保留；已完成的ZIP按各组记录解压并核验。以下文件数为组清单中可用原始/报告文件，不包含所有解压成员；SHA-256和逐文件记录见[统一机器清单](_provenance/manifest_all_sources.json)及各组清单。', '']
 for category, heading in [('available', '已取得数据、报告或方法文件'), ('in_progress', '进行中'), ('unavailable', '尚未取得所需数据')]:
  lines += ['## ' + heading, '', '| ID | 数据源名称 | 状态 | 实际取得范围 | 本地目录 | 官方/原始来源 |', '|---|---|---|---|---|---|']
  for doc in sources:
   if doc['category'] != category:
    continue
   status = '已取得（有范围）' if category == 'available' else '进行中' if category == 'in_progress' else '尚未取得目标数据'
   if category == 'available' and doc.get('status') == 'downloaded':
    status = '已取得指定文件/序列'
   if category == 'in_progress' and doc.get('task_count'):
    status += f"（{doc['completed_task_count']}/{doc['task_count']}文件）"
   link = f"[打开目录]({quote(doc['directory'], safe='')}/)" if doc.get('directory') else '待定位'
   lines.append('| ' + ' | '.join([doc['id'], safe_cell(doc['title']), status,
                  safe_cell(doc['scope']), link, f"[来源]({doc['source_url']})"]) + ' |')
  if not any(x['category'] == category for x in sources):
   lines += ['', '无。']
  lines += ['']
 lines += ['## 后续取得条件', '',
 '- **D02、D09—D13：** 需CDS/EWDS账户、接受相应数据许可并配置本人API访问后，再按云南及相关上游流域、变量和时段提交任务；目前仅元数据和许可。',
 '- **D03：** 官方Google Drive亚洲pfaf04文件明确返回“Quota exceeded”。需发布方配额恢复或官方提供可用镜像；`.part`和`.segments`仅供合法续传，尚不构成完整NetCDF。',
 '- **D04：** 需按GRDC要求选择测站/区域并用真实申请人资料提交申请、接受用途条件；下载链接由其通过邮件提供。',
 '- **D23：** 实际企业账单、计量点和电量资料需要对应主体账户或正式授权；本次没有取得私人账单。',
 ('- **进行中的科学数据：** 待当前下载、解压和独立审计完成后重跑`python dataset/_provenance/build_delivery_index.py`，自动刷新本清单；不会把旧目录失败记录或残片计为成功。' if counts['in_progress'] else '- **公开科学数据：** 25个原文件、15个ZIP的下载、解压和审计已完成；原始压缩包全部保留。'), '',
 '标准文件另见其独立交付目录与18项清单，不在本29项合并统计内。', '']
 out = BASE / '下载清单.md'
 out.write_text('\n'.join(lines), encoding='utf-8')
 audit = {'generated_utc': generated, 'status': 'passed', 'unique_source_ids': 29,
          'unavailable_ids': sorted(UNAVAILABLE), 'fragment_files_counted_as_data': 0,
          'sources_with_missing_counted_files': 0, 'summary': result['summary'],
          'warnings': WARNINGS}
 (PROV / 'build_delivery_index_audit.json').write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding='utf-8')
 print(json.dumps({'markdown': out.as_posix(), 'manifest': write_json.as_posix(),
                   'summary': result['summary'], 'warnings': WARNINGS}, ensure_ascii=False, indent=2))

if __name__ == '__main__':
 main()
