# 水库—工业产品库存研究准备包

**版本1.0｜2026-10-26**

研究主线：水库蓄水、发电、工业生产与固态产品库存的协同经济机制及适用边界。**已排除企业行为、博弈、收益分配和合同设计。** 外部电力价格、接入条件与实际交付义务仅作为外生边界。

## 文件说明

| 文件 | 内容 |
|---|---|
| [01_research_plan.md](01_research_plan.md) | 完整研究计划：问题、边界、方程、对照、试验、数据、验收、12周参考研究排期 |
| [02_literature_catalog.md](02_literature_catalog.md) | 40篇期刊论文+8项补充资料/预印本线索；每篇含用途、限制和来源 |
| [03_data_catalog.md](03_data_catalog.md) | 29项数据库、数据源或技术入口；区分实测、再分析、汇总与需授权资料 |
| [04_standards_and_rules.md](04_standards_and_rules.md) | 18项标准/政策/规则记录，另列6类真实案例必需文件 |
| [05_search_and_verification_notes.md](05_search_and_verification_notes.md) | 检索范围、未完成核验、版本修正和精读验收表 |
| [journal_dois_for_zotero.txt](journal_dois_for_zotero.txt) | 40篇期刊论文DOI清单，便于文献管理器导入 |
| [literature_metadata.json](literature_metadata.json) | 文献机器可读元数据 |
| [data_sources_metadata.json](data_sources_metadata.json) | 数据源机器可读元数据 |
| [standards_metadata.json](standards_metadata.json) | 标准/规则机器可读元数据 |
| [parameter_registry_template.json](parameter_registry_template.json) | 38项参数/输入登记骨架；未知数值保持null |
| [toy_case_expected.json](toy_case_expected.json) | 两期人工测试输入与已枚举核对的M0/M1/M2结果 |
| [MANIFEST_SHA256.txt](MANIFEST_SHA256.txt) | 文件校验值 |

## 推荐使用顺序

先读研究计划第1–4、8、13–14节，锁定范围与第一轮任务；再按文献库P0路线精读；随后填参数登记模板并获取最少数据。不要先搬运全国模型，也不要因为目录中出现市场文献就重新加入企业博弈。

核心对照为：M0常规生产+充分优化水电；M1固定M0水电，仅优化生产库存；M2完全联合优化。关注M1到M2的追加经济收益，而不只是M0到M2的总节约。

## 重要说明

文献与规则检索基于公开一手来源；不是正式穷尽查新。不是全部全文已精读，也不是全部数据已下载。“高水平”用于说明核心来源，专业数据/方法/工艺支持文献单独标明，不给未经核验的当年分区和影响因子。

研究“必须具备”的是可信的数据要素和适用边界，不是目录中每个数据库都强制采用。标准的现行状态、适用对象与实际项目批准条件需要对应；征求意见稿不能直接作为运行依据。

包内不含受版权保护的论文或标准全文、不含任何真实企业数据或API密钥、不含完整生产级优化代码。两期数值是人工程序测试，不是实际研究收益。Markdown公式需支持LaTeX的阅读器呈现。

正式投入大规模建模前，先确认原Nature Energy正式补充材料和代码版本，再通过小模型验证真实经济耦合。最终创新性取决于可信的机制发现与验证，而非组件数量。
