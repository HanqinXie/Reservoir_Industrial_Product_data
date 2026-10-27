# 水库—工业产品库存初步模型

用一个独立、可检查的日尺度线性规划，比较常规生产、固定水库计划下的生产调整，以及水库与工业联合优化。依赖 SciPy/HiGHS，不需要 Gurobi 或整套 PyPSA。

示例使用 D01 中小湾 1979—2016 年模拟入流的代表年份及 D17 的电解冶炼能耗参考。工业生产边界、月末交付、电价、仓容等为明确假设。默认水电参数等比缩放为代表性单元，不是实际电站—铝厂直供案例。

模型直接读取本目录附带的已核验 CSV，不需要先解压完整的大型数据归档，也不会在运行时加载原始 pickle。数据来源、变换和校验值记录在 [data/source_manifest.json](data/source_manifest.json)。

已运行的三年结果、19项检查和22点敏感性记录见 [examples/README.md](examples/README.md)。其中枯年和平年的收益仅体现月内库存占用改善，不能据此宣称季节备货已经得到验证。

## 1. 安装和直接运行

使用 Python 3.10 或以上版本，在本仓库根目录打开终端：

```bash
cd models/reservoir_inventory
python -m pip install -e .
python -m reservoir_inventory verify-toy --out outputs/toy
python -m reservoir_inventory demo --config configs/xiaowan_demo.json --out outputs/demo
```

`verify-toy` 核对两期人工案例；`demo` 生成丰、平、枯三套输入，再分别运行 M0、M1、M2。两期人工案例的数字用于程序核对，不是工程收益预测。

`verify-toy`、`run` 和 `demo` 可加 `--no-plots` 只生成表格与记录；`prepare` 和 `demo` 可加 `--years 1993 1988 1990` 明确选择完整水文年。

如需先查看和修改输入，再计算：

```bash
python -m reservoir_inventory prepare --config configs/xiaowan_demo.json --out outputs/inputs
python -m reservoir_inventory run --inputs outputs/inputs/normal --out outputs/normal
```

小规模单因素敏感性与程序检查：

```bash
python -m reservoir_inventory sweep --inputs outputs/demo/inputs/normal --out outputs/sweep
python -m unittest discover -s tests -v
```

`sweep` 分别改变库容、额外产品库存、按额定产能定义的生产余量和持有费用，不运行所有参数的笛卡尔积。修改后的输入若不可行，应检查约束和边界，不通过删除交付任务来得到结果。

## 2. 三组方案比较什么

| 方案 | 生产与库存 | 水库 |
|---|---|---|
| **M0** | 给定可行的基准生产计划 | 充分优化 |
| **M1** | 允许生产和库存调整 | 固定 M0 的蓄水、机组过水和弃水计划 |
| **M2** | 与 M1 相同的生产和库存能力 | 与生产联合优化 |

三组方案共享来水、交付、初末水量与库存，以及价格和设备能力。

- `C_M0 − C_M1`：固定水库计划时，生产与库存调整的收益。
- `C_M1 − C_M2`：进一步重新安排水库的追加收益。

**追加收益为零也可能是正确结果。** 默认允许购电和售电，不通过禁止所有售电预先制造消纳收益。结果是所给信息和约束下的可变运行费用差额，不能直接称为企业利润或新建仓库的投资收益。

## 3. 默认算例

| 项目 | 设置 |
|---|---|
| 时间 | 日尺度；枯年 1993、平年 1988、丰年 1990，按完整年总入流的 20%/50%/80% 分位附近选择 |
| 水电 | 小湾来源序列；入流、库容和功率同时乘 `hydro_scale=0.5` |
| 额定产能 | `1000 t/day` |
| 最低持续生产 | 额定产能的 90%，即 `900 t/day`，为假设 |
| 基准生产 | 每天 `950 t` |
| 交付 | 月末交付当月基准总产量 |
| 产品电耗 | `13.203+0.25=13.453 MWh/t`，后项为铸造附加假设 |
| 库存口径 | `end_delivery`，检查交付前仓容并按日内平均库存计费 |
| 仓容 | 基准正常周转峰值，加 30 天平均交付量的额外空间 |
| 持有费 | `3 CNY/(t·day)`，为假设 |
| 电价和接口 | 丰枯分价，默认双向不限量；具体值见配置和输入表 |

最低生产比例按额定产能算，不按交付量算。月末交付使基准本身存在正常周转库存，额外库存空间不能与总仓容混为一谈。

1988 年保留 366 天。不同年份的生产和交付总量按真实日历生成，不为了对比删除闰日。丰、平、枯标签仅描述全年总入流，不等同于季节性或连续干旱指标。

## 4. 输入接口

每个案例目录有五张 UTF-8 CSV 和一份 `case.json`。修改案例时，保持各逐日表日期、顺序和长度一致，源数据目录保留原样。

| 文件 | 主要字段与用途 |
|---|---|
| `reservoir.csv` | `name,value,unit,source_id`；水库、装机、固定水耗及共同初末水量/库存等标量 |
| `inflow.csv` | `date,duration_hours,inflow_m3,evaporation_m3,min_release_m3,water_min_m3,water_max_m3,source_id`；另支持 `max_release_m3,hydro_capacity_mw` |
| `industry.csv` | `date,delivery_t,baseline_production_t,production_min_t,production_max_t,electricity_mwh_per_t,inventory_capacity_t,source_id` |
| `economics.csv` | `date,buy_price_cny_per_mwh,sell_price_cny_per_mwh,import_limit_mw,export_limit_mw,other_load_mwh,holding_cost_cny_per_t_day,production_cost_cny_per_t,hydro_cost_cny_per_mwh,source_id` |
| `sources.csv` | `source_id,kind,description,source_url,limitations`；区分资料值、派生值与假设 |
| `case.json` | 库存口径、初始库存容量及案例元数据 |

`inflow_m3` 是该时段总水量；购售电价用 CNY/MWh，接口容量用 MW，产量与交付用吨。不要把流量 m³/s、能量 GWh 或单位产品 DC 电耗直接填入不匹配的列。

逐日表的 `water_min_m3`、`water_max_m3` 和 `inventory_capacity_t` 是时段末端边界；起始边界由 `reservoir.csv` 和 `case.json` 给定。购售电接口及最大下泄的空值表示不限量，其他必要物理数据的缺失不能当作零。

三种库存口径可用于不同问题：`boundary` 对应两期离散人工案例，`uniform` 对应期内连续交付，`end_delivery` 对应期内均匀生产、期末交付。切换口径后，仓容和持有费用的物理含义会改变，不能只换名称而沿用结果。

## 5. 结果怎样看

单个案例运行后，先打开下列文件：

| 文件 | 用途 |
|---|---|
| `comparison_summary.json` | 三组费用差额、求解及检查结果 |
| `cost_summary.csv` | 购售电、库存及可变成本分项 |
| `M0_dispatch.csv`、`M1_dispatch.csv`、`M2_dispatch.csv` | 逐日水量、发电、生产、交付、库存和购售电结果 |
| `weekly_dispatch.csv` | 便于检查丰枯转换的周汇总 |
| `comparison.png` | 三组方案的直观对照 |
| `run_manifest.json` | 本次运行的输入与运行记录 |

阅读顺序是：先确认求解与平衡检查通过，再看 `M1−M2` 是否明显，最后沿逐日结果解释收益来自弃水减少、水库重新蓄放、购售电变化还是生产时移。仅有库存变动，或仅有水库曲线差异，不能自动证明追加水库协同收益。

`peak_inventory_t` 包含正常月内周转库存。判断是否真的跨月留存，还要查看 `max_post_delivery_inventory_t` 和逐日表的 `post_delivery_inventory_t`。当前默认参数初跑中，枯年和平年的交付后库存归零，费用改善来自月内生产安排；这些结果尚不能证明季节库存有价值。丰年若出现跨月剩余，也应沿具体时序区分短期跨月与跨季储存。

若净费用为负，表示模型计入的售电收入超过已列支出，并不表示已计算出企业总利润。此时优先报告以 CNY 表示的费用差额，不对负的基准费用机械计算“节约百分比”。

`weekly_dispatch.csv` 仅对连续日历日生成周汇总，水量、能量、产量和费用求和，水库与库存状态取首尾；人工两期标签不伪装成日期，周表为空且原因记录在汇总 JSON 中。

模型没有停槽复产、变水头、梯级及实际预测误差。详见 [模型方程](docs/model_formulation.md) 和 [来源、假设与边界](docs/assumptions.md)。先通过本版本判断机制，再补齐具体电站和产线的工程参数。
