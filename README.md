# 水库—工业产品数据与研究资料

> 完整快照已上传并通过服务端大小与SHA-256核验。详见 `UPLOAD_RECEIPT.json`。

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
- `dataset` 目前有20项来源的可用数据或资料；9项目标数据受账户、申请/授权或下载配额限制，见[下载清单](dataset/下载清单.md)。GRADES `.part` / `.segments` 是原样保留的未完成分片，不能作为完整NetCDF使用。
- 标准共18项，包含官方在线阅览分页保存版和公开PDF副本；S17原始Word存在兼容性限制并附参考TXT，见[标准获取说明](standards/获取说明.md)。

## 下载并还原全部五目录

需要Python及`zstandard`：

```powershell
python -m pip install zstandard
python tools/restore_snapshot.py --destination . --cache-dir .snapshot-cache
```

恢复脚本会下载清单与分卷、校验每卷SHA-256，再流式解压并逐文件核对。已有相同文件会跳过；不同文件默认拒绝覆盖。原始压缩包和已解压数据都会恢复。

## 来源与版本

各文件保留原始发布方的许可、引用与使用边界，不将第三方数据或标准重新声明为本仓库自有成果。原始出处、下载记录、版本和校验结果保留在各目录的`_provenance`及清单中。
