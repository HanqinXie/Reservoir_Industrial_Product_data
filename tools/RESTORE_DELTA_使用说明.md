# 本地新增数据与 Run01 增量恢复

增量 Release 为 [`local-update-20261027-run01`](https://github.com/HanqinXie/Reservoir_Industrial_Product_data/releases/tag/local-update-20261027-run01)。它只保存新增及修改文件；完整恢复顺序是先还原 [`snapshot-20261027`](https://github.com/HanqinXie/Reservoir_Industrial_Product_data/releases/tag/snapshot-20261027)，再应用本增量。原始快照、原 `SOURCE_FILES_SHA256.json` 和原分卷保持不变。

Python 3.10 及以上版本，需要 `zstandard`。恢复工具与原工具共用下载和安全路径辅助函数，因此 `restore_delta.py` 与 `restore_snapshot.py` 应保留在同一 `tools` 目录。

## 操作步骤

先从包含本次增量元数据的仓库版本取得工具。以下命令在仓库根目录执行。完整快照和增量都使用同一个 `--destination`；下载缓存必须位于恢复目录以外，并且不能与恢复目录互相包含。

```powershell
python .\tools\restore_snapshot.py --destination "D:\Reservoir_restored" --cache-dir "D:\Reservoir_base_cache"
python .\tools\restore_delta.py --destination "D:\Reservoir_restored" --cache-dir "D:\Reservoir_update_cache" --dry-run
python .\tools\restore_delta.py --destination "D:\Reservoir_restored" --cache-dir "D:\Reservoir_update_cache"
```

`--dry-run` 仍会下载清单、分卷，并完整解压到缓存内的临时 staging 目录进行验证；它不写入或删除恢复目录中的内容。缓存齐全后可以增加 `--offline`，禁止任何下载。

本增量的路径以恢复目录为根：例如 `dataset/D02_...`、`models/reservoir_inventory/...`。分卷不包含本机的绝对路径或 `code/Reservoir_Industrial_Product_data` 本地父目录。单卷上限为 **350,000,000 字节**，按清单顺序连接后组成单个 zstd frame 内的 tar 流；不能分别解压每个分卷。

## 校验与覆盖规则

工具默认以仓库中 `updates/local-data-20261027/update_archive_manifest.json` 为可信副本，对下载的同名清单核对 SHA256，再按其中记录核对 `UPDATE_FILES_SHA256.json`、`UPDATE_CHANGES.json` 的原始字节 SHA256。原始基准清单 SHA256 固定为：

```text
e28bf34756a0785712ddbe432c20e9c374b482eaa23fbf012b1170a5c9a1b7fe
```

生产命令不能通过参数替换该固定值。`--archive-manifest` 可以指定从可信仓库取得的增量清单；`--base-source-manifest` 只能改变原基准清单的读取位置，内容仍须匹配上述固定 SHA256。在线模式下这两个可信清单均须放在下载缓存目录之外，防止下载覆盖信任依据；离线模式只读取已有缓存。

- **added**：目标不存在才写入；已有内容与新增 SHA256 相同则跳过；其他内容拒绝覆盖。
- **changed**：目标须匹配固定基准中的旧大小及 SHA256，才允许替换；已匹配新 SHA256 则跳过；目标缺失或出现其他内容均拒绝操作。
- **deleted**：目标须匹配固定基准中的旧大小及 SHA256，才允许删除；已不存在则跳过。删除只允许 `D01_Nature_Energy_Industrial_Overcapacity/extracted/` 内的已知 Apple 元数据，或可从 CP437 严格逆转为 UTF-8 中文名、并具有相同大小及 SHA256 的更名 GIS 副本。正确文件必须存在于新增或修改 payload 中。

所有目标冲突会先统一检查；之后完整验证每卷 SHA256、tar 成员名称/类型/大小/内容 SHA256、成员集合、zstd 校验和及完整 EOF。重复、缺失、额外、链接、稀疏文件、危险路径及尾随压缩数据会导致失败。完整 staging 验证通过后，再次检查目标冲突，逐文件落地；所有 payload 落地并复验后，才逐项复核旧 SHA256 并删除。不会递归删除目录，也不会清理用户额外文件。

目标及缓存路径的已有祖先、目标成员和缓存文件均拒绝 symlink、Windows junction 及其他 reparse point。恢复时请关闭会同时编辑同一批文件的其他程序；该工具没有提供跨进程文件锁。

## 完成、失败与重新执行

只有退出码为 0 且输出 `UPDATE_APPLIED` 才表示增量应用通过；`DRY_RUN_VERIFIED` 表示预演完整校验通过，尚未应用。摘要记录所用增量清单及基准清单 SHA256。

应用阶段是逐文件替换，并非整个目录的一次事务。磁盘或权限错误可能留下已经验证的新文件；删除安排在全部新文件验证完成之后。修复环境问题后，重复同一命令会重新核对旧/新 SHA256，已完成文件会跳过。未知用户修改会被保留并导致失败，需要先在恢复目录外保留和处理这些改动。

增量工具核验所有受影响文件，不会重新读取未变的约 65 GB 基准数据来宣称完整科学数据正确。完整基准恢复应以原恢复器成功结束为前提。增量应用后，不要对同一目录使用原恢复器的 `--overwrite`，否则会把增量修改文件恢复成旧快照版本。

本工具未对任何流域边界进行修复；D24 的源几何自交等检查结果属于数据质量记录，原数据按清单原样保存。

## 小型离线测试

测试仅使用系统临时目录内的小型自建文件及分卷，不下载真实 Release，不改研究数据。Python API 的基准 SHA 参数只供这些 fixture 使用，生产 CLI 不提供该覆盖选项。

```powershell
python -m unittest discover -s tools/tests -p test_restore_delta.py -v
```
