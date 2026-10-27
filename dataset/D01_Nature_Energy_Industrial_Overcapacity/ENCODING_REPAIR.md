# D01 Windows乱码及苹果元数据修复记录

修复日期：2026-10-27。

## 原因与已完成处理

1. 原ZIP中的60个GIS配套文件名使用UTF-8字节却未设置ZIP UTF-8标记，原解压程序按CP437读取，形成σ、τ等乱码。现已严格逆转换恢复10组中文名称，.shp/.shx/.dbf/.prj/.sbn/.sbx同步改名。
2. 原包附带286个__MACOSX/._*资源元数据和15个.DS_Store文件，共301个。已从解压目录移除；它们仍完整保存在原data.zip中，并有成员SHA-256记录。._README.md等是二进制AppleDouble，不是真正的README。
3. 真正的252个科研文件全部逐字节匹配原ZIP，101个文本严格UTF-8检查通过。未转换GIS DBF的内部编码，保留原.cpg声明；正常的pickle/HDF5/NetCDF/SHP等二进制不可按文本阅读。
4. 数据获取解压脚本已限定对D01恢复名称并跳过苹果元数据；审计脚本可核验保留科研文件与原包内跳过元数据的完整分区。其他数据源解压策略保持原样。

## 恢复的中文文件组

- 中国地州界
- 全国县级统计数据
- 县城驻地
- 国界线
- 地级城市驻地
- 省会城市
- 省级行政区
- 线状县界
- 线状省界
- 经纬网

## 原始数据已有的内容缺陷

costs/costs_2020.csv至costs_2060.csv（每5年一份，共9份）的第588行，solar/investment的source字段均含`Carbon Neutralization�� (in Chinese)`，共18个替换字符。原ZIP已含完全相同的字符，属于上游来源说明缺字；数值字段未涉及。没有足够证据恢复原字，因此保留原文并明确标注，未猜测改写科研源文件。

## 完整性与使用位置

- 原ZIP SHA-256：`18a4b3861a5efd0cf2e4be619b28a6af8317b9fea7d971731a2aff12c87adf3f`，与取得时记录一致；CRC复核通过。
- 保留科研文件：252个，147,414,509字节；全部与原包内容一致。
- 正常数据入口：`extracted/data/data/`。中文地图：`extracted/data/data/province_shapes/CHN_adm/`。
- 当前路径及排除记录：`manifest.json`与`_provenance/data.zip.manifest.json`。完整文件名映射：`_provenance/data.zip.filename_mapping.json`。
- 修改前9份脚本/清单/来源说明已逐文件SHA验证备份于`_provenance/windows_repair_20261027/before/`；旧的下载修复批次记录作为历史保留。
- 逐文件核验和已知问题：`_provenance/windows_repair_20261027/verification.json`。
- 重跑本项核验：模型虚拟环境Python调用`_provenance/repair_windows.py --verify`。
- 本次不涉及Reservoir_Industrial_Product_data模型的源码、轻量输入或此前Run01 ZIP。

## 修复后原流程复核

- 离线回归5项通过；用备份旧脚本重现2项原缺陷，当前脚本均通过。
- 对原始data.zip在限定临时目录实际重新解压：252个科研文件、301个明确跳过的苹果元数据，62项映射（60个中文名+2个冒号映射）；新解压科研文件路径及SHA-256与修复目录完全一致。
- 原audit_scientific审计函数对D01的隔离复核通过，原包文件由252个保留成员与301个有哈希的元数据成员完整分区；临时解压目录已清理。
- 模型原有19项检查再次全部通过；此前Run01 ZIP的SHA-256保持一致。
- 完整日志与状态见`_provenance/windows_repair_20261027/workflow_verification.json`及同目录日志。
