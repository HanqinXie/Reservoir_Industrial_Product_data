# 水库—工业产品数据与研究资料

> 完整快照已上传并通过服务端大小与SHA-256核验。详见 `UPLOAD_RECEIPT.json`。

## 2026-10-27 本机资料与运行记录更新

[本次增量 Release](https://github.com/HanqinXie/Reservoir_Industrial_Product_data/releases/tag/local-update-20261027-run01) 保存原快照之后的新增/修改文件，原 `snapshot-20261027`、原始来源清单和50个分卷保持不变。最新下载清单为 **21项已取得指定范围资料、8项目标数据尚未取得**，不表示21个数据库已经全量下载。

- D02 已取得2015年请求的 GloFAS v4.0 全球日均流量，以及[云南附近矩形子集](dataset/D02_Copernicus%20GloFAS历史流量再分析/yunnan_bbox_2015_glofas_v4.nc)（21—29°N、97—107°E，17,113,700字节）；365个原时间标签及全部子集值保持不变，尚未按省界或完整上游流域裁剪。
- D01 恢复60个中文GIS文件名，并从解压工作目录移除301个macOS元数据；252个科研文件内容与保留的原ZIP一致。[修复说明](dataset/D01_Nature_Energy_Industrial_Overcapacity/ENCODING_REPAIR.md)
- D24 保存只读核验记录：文件可读，但完整/区间集水区分别有36/97个环自交要素；没有擅自修复边界。[检查记录](dataset/D24_CLEAR/_provenance/readability_check_20261027.json)
- 模型随附[本机Run01报告](models/reservoir_inventory/RUN_REPORT.md)、[结果包](models/reservoir_inventory/Reservoir_Inventory_Run01.zip)、实际输入/输出与日志；原模型源码和默认参数未修改。

本次按用户选择仅发布云南子集和检查/复现记录，全球NetCDF与原下载ZIP保留本机。增量包含220个新增、12个修改、361个旧D01文件删除操作，232个payload文件共82,769,865字节，压缩为1个34,584,723字节附件。详细文件哈希与操作见 [updates/local-data-20261027](updates/local-data-20261027/)。完整恢复需先还原原快照，再按[增量恢复说明](tools/RESTORE_DELTA_使用说明.md)应用本次更新；工具会拒绝覆盖未知用户修改。

本仓库保存用户指定的五个本地目录。完整快照包含全部原始文件、已下载的压缩包、解压数据、溯源记录与未完成下载分片，保持原目录名和文件字节。

| 原目录 | 文件数 | 字节数 |
|---|---:|---:|
| `水库_工业库存_研究计划与文献数据标准包_20261026` | 13 | 245,800 |
| `dataset` | 22,050 | 65,548,316,969 |
| `PyPSA` | 1 | 10,313,256 |
| `refrences` | 45 | 342,473,854 |
| `standards` | 483 | 79,984,640 |

原始文件合计 **22,592 个，65,981,334,519 字节**。本次快照日期为 **2026-10-27（Asia/Shanghai）**。

## 仓库内容与完整数据

- `main` 保存研究计划标准包、`PyPSA`、`refrences`、`standards` 的全部文件，以及 `dataset` 的文本说明、脚本和机器清单。
- 五目录的全部文件同时保存在[完整快照 Release](https://github.com/HanqinXie/Reservoir_Industrial_Product_data/releases/tag/snapshot-20261027)的 `tar.zst` 分卷附件中，每卷不超过640,000,000字节。
- `SOURCE_FILES_SHA256.json` 列出每个原文件的路径、字节数与SHA-256；`archive_manifest.json` 列出全部分卷及SHA-256。
- 原始快照的 `dataset` 有20项来源的可用数据或资料、9项未取得；最新本机更新为21项有范围资料、8项未取得，见[下载清单](dataset/下载清单.md)。GRADES `.part` / `.segments` 是原样保留的未完成分片，不能作为完整NetCDF使用；新增单站CSV不等于原始GRADES亚洲全域数据已完成。
- 标准共18项，包含官方在线阅览分页保存版和公开PDF副本；S17原始Word存在兼容性限制并附参考TXT，见[标准获取说明](standards/获取说明.md)。

## 初步水库—工业库存模型

[models/reservoir_inventory](models/reservoir_inventory/README.md) 提供独立的日尺度 M0/M1/M2 线性规划、已提取的小湾日入流 CSV、五张可编辑输入表的生成器，以及丰平枯年对比和四类单因素敏感性分析。

```bash
cd models/reservoir_inventory
python -m pip install -e .
python -m reservoir_inventory verify-toy --out outputs/toy
python -m reservoir_inventory demo --out outputs/demo
```

运行示例无需恢复完整原始快照。水文与水库参数来自已有资料，工厂、交易和初末状态假设逐项登记；本模型尚非具体电站—工厂的工程验证。[已运行示例与核验记录](models/reservoir_inventory/examples/README.md) 说明了当前结果及其适用范围。

该模型目录是原始资料快照之后新增的代码和派生数据，原有五目录快照与校验清单仍描述原始归档。

## 下载并还原全部五目录

需要Python及`zstandard`：

```powershell
python -m pip install zstandard
python tools/restore_snapshot.py --destination . --cache-dir .snapshot-cache
```

恢复脚本会下载清单与分卷、校验每卷SHA-256，再流式解压并逐文件核对。已有相同文件会跳过；不同文件默认拒绝覆盖。原始压缩包和已解压数据都会恢复。

## 来源与版本

各文件保留原始发布方的许可、引用与使用边界，不将第三方数据或标准重新声明为本仓库自有成果。原始出处、下载记录、版本和校验结果保留在各目录的`_provenance`及清单中。
