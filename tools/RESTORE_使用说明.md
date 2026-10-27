# 完整数据恢复

五个原目录的完整文件快照存放在本仓库的 [GitHub Releases：snapshot-20261027](https://github.com/HanqinXie/Reservoir_Industrial_Product_data/releases/tag/snapshot-20261027)。Git 仓库本身保留说明及小文件；克隆仓库不会下载完整数据。分卷是同一个 `tar.zst` 压缩流，每卷不超过 640,000,000 字节。

需要 Python 3.10 或更高版本。在本脚本所在目录执行：

```powershell
python -m pip install zstandard==0.25.0
python .\restore_snapshot.py --destination "D:\Reservoir_restored" --cache-dir "D:\Reservoir_download_cache"
```

`--destination` 指定恢复五个原目录的共同父目录；`--cache-dir` 保存清单、已下载分卷和未完成的 `.download` 文件。这两个目录必须分开且互不包含。请为缓存和恢复数据同时预留空间；不会生成未压缩的中间 `.tar` 文件。

脚本自动从公开 Release 下载 `archive_manifest.json`、`SOURCE_FILES_SHA256.json` 和全部分卷。网络中断后重新执行同一命令即可续传，支持 HTTP Range；服务器不支持 Range 时会重新下载该卷。每卷均核验大小和 SHA256，全部通过后才开始还原；每个恢复文件再对照源文件清单核验字节数和 SHA256。已有内容相同的文件跳过写入；已有内容不同的文件默认拒绝覆盖。确认允许替换时，在同一命令末尾增加 `--overwrite`。

只有出现 `SUCCESS` 且退出码为 0 才表示该次恢复完整通过。出现损坏分卷时，错误会指出文件名；从缓存目录移走该卷或对应 `.download` 后重试。恢复中断可能留下已验证的文件，重试会重新核验并跳过；不会把失败当作完成。

恢复器拒绝路径逃逸、绝对路径、Windows 驱动器/备用数据流、符号链接、硬链接、设备成员，以及清单之外、重复或缺失的文件。源文件清单保留原相对路径与修改时间；所有文件保留原文件夹层级。

完整性核验依赖同一 Release 中的清单。SHA256 用于发现损坏与不一致，不等同于独立的发布者签名。
