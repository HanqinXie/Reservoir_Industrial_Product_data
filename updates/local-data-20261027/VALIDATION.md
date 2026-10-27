# 发布前核验

- 原模型19项、D01解压回归5项、增量恢复工具19项：共43项通过。
- 全本地dataset按SHA-256扫描约70.35GB，0读取错误、0扫描期间变动；随后对明确更新元数据及全部模型payload补算哈希。
- 236个增量payload文件合计4,845,018,397字节，14卷合计4,603,979,089字节；逐卷SHA与完整解压流/逐文件SHA核验通过。
- 真实分卷使用生产CLI离线预演：23.156秒，目标SHA/mtime/目录不变；实际应用33.219秒，写236/删361；再次运行38.047秒，写0/跳过236/删0，目标不变。额外测试文件保留。
- 完整恢复证据见RESTORE_VERIFICATION.json及同目录三个日志。临时恢复目标仅为本机验证副本，没有修改原研究数据。
- 原SOURCE_FILES_SHA256.json、archive_manifest.json、SHA256SUMS.txt、UPLOAD_RECEIPT.json、snapshot_verification.json与基准HEAD完全相同。
- Git提交文件均低于100,000,000字节；不含新缓存、虚拟环境、Copernicus请求标识或检测到的GitHub令牌/私钥模式。

服务端每个附件的大小和SHA-256校验结果另存发布收据。
