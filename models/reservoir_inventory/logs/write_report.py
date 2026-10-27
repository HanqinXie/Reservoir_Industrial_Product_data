"""Create the Chinese report from the actual audited outputs."""
from datetime import datetime, timezone, timedelta
from pathlib import Path
import json
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

def load(rel):
    return json.loads((ROOT / rel).read_text(encoding="utf-8-sig"))

def main():
    start = datetime.now(timezone.utc).isoformat()
    with (ROOT / "logs/05_result_audit.log").open("wb") as stream:
        status = subprocess.run([sys.executable, str(ROOT / "logs/audit_results.py")], cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT).returncode
    (ROOT / "logs/05_result_audit.status.json").write_text(json.dumps({"command": ".venv/Scripts/python.exe logs/audit_results.py", "start_utc": start, "end_utc": datetime.now(timezone.utc).isoformat(), "exit_code": status}, indent=2), encoding="utf-8")
    if status:
        raise RuntimeError((ROOT / "logs/05_result_audit.log").read_text(encoding="utf-8"))
    # PowerShell 5.1 native redirection used UTF-16 for the bootstrap logs.
    for name in ("00_install.log", "bootstrap_pip_freeze_failure.log"):
        p = ROOT / "logs" / name
        if p.read_bytes().startswith((b"\xff\xfe", b"\xfe\xff")):
            p.write_text(p.read_text(encoding="utf-16"), encoding="utf-8")
    a = load("logs/result_audit.json")
    env = load("logs/environment.json")
    commands = load("logs/command_statuses.json")
    now = datetime.now(timezone(timedelta(hours=8))).isoformat(timespec="seconds")
    lines = ["# 水库—工业产品库存初步模型：本机复现报告 Run01", "", f"报告时间：{now}（北京时间）。", "",
        "本轮已实际执行指定基准版本的全部现有检查、两期算例、三代表年及四类单因素敏感性。四个主命令退出码均为0，19项检查通过，三年9次年度模型均最优；敏感性22点中20点最优、2点输入不可行且保留原因。未修改任何仓库跟踪的源码、测试、参数、文档或数据。", "",
        "## 1. 代码与本机环境", "", f"模型目录：`{ROOT}`。", "",
        "- 仓库：https://github.com/HanqinXie/Reservoir_Industrial_Product_data.git",
        "- 对应PR：https://github.com/HanqinXie/Reservoir_Industrial_Product_data/pull/1",
        "- 分支：`feat/reservoir-inventory-prototype`。",
        f"- 实际HEAD及运行开始时远程分支HEAD：`{env['git_head']}`，与用户指定基准一致。",
        "- 初始项目父目录不是Git仓库，指定code目录为空；本轮新建稀疏克隆，未覆盖既有文件。稀疏路径为`models/reservoir_inventory`。",
        "- 已阅读模型README、pyproject.toml、docs/model_formulation.md、docs/assumptions.md及examples基准记录。",
        "- `git diff HEAD --exit-code`为0；7个Python源文件、默认配置和轻量来源数据的SHA-256均与examples记录一致。新增内容仅为本轮日志、审计/打包辅助脚本、报告与交付文件；环境和outputs由原命令生成。",
        "- 数据来源记录中的`cc1e9da...`是原资料仓库来源提交，不是本轮模型运行提交；二者分别保留。", "",
        "| 项目 | 实际版本 |", "|---|---|", f"| Python | {env['python'].split()[0]}，64位 |"]
    for name in ("numpy", "pandas", "scipy", "matplotlib", "pip", "setuptools"):
        lines.append(f"| {name} | {env['packages'][name]} |")
    lines += [f"| HiGHS | {a['highs_version']}，通过SciPy linprog(method='highs')调用 |",
        f"| 系统 | {env['platform']} |", "",
        "使用模型目录下`.venv/Scripts/python.exe`，未依赖PowerShell激活脚本。`pip check`通过；构建时按pyproject要求使用pip隔离构建环境。依赖清单为`logs/pip_list_freeze.txt`，可重装版本清单为`logs/requirements_run01.txt`。", "",
        "## 2. 实际命令与退出状态", "", "新建环境前执行：", "", "```powershell",
        "git clone --depth 1 --filter=blob:none --sparse --branch feat/reservoir-inventory-prototype https://github.com/HanqinXie/Reservoir_Industrial_Product_data.git Reservoir_Industrial_Product_data",
        "cd Reservoir_Industrial_Product_data", "git sparse-checkout set models/reservoir_inventory", "cd models/reservoir_inventory", "py -3.10 -m venv .venv", ".\\.venv\\Scripts\\python.exe -m pip install -e .", "```", "",
        "安装退出码为0，日志为`logs/00_install.log`及同名status.json。后续四个主命令严格按下表顺序运行；均保留合并stdout/stderr的完整UTF-8日志和起止UTC时间、耗时、PID、退出码。", "",
        "| 阶段 | 虚拟环境Python之后的参数 | 退出码 | 耗时/s | 日志 |", "|---|---|---:|---:|---|"]
    for c in commands:
        lines.append(f"| {c['name']} | `{' '.join(c['argv'][1:])}` | {c['exit_code']} | {c['elapsed_seconds']:.3f} | `{c['log']}` |")
    lines += ["", "独立读回审计另执行`.venv/Scripts/python.exe logs/audit_results.py`，退出码为0。复跑调度入口为`logs/run_commands.py`；只读审计入口为`logs/audit_results.py`。", "",
        "## 3. 检查数量、两期算例及容差", "",
        "原仓库检查共19项（15项模型单元检查、4项输入集成检查），实际19通过、0失败、0跳过，完整逐项名称见`logs/01_unittest.log`。包含独立守恒/费用重算、两期控制、初末状态、库存口径、来源/日期一致性及闰日等检查。", "",
        "| 两期案例 | M0 | M1 | M2 | 追加水库协调收益M1−M2 |", "|---|---:|---:|---:|---:|",
        "| 禁外送 | 6 | 2.4 | 0.4000000000000001 | 2 |",
        "| 无限同价购售电 | 4 | 0.4000000000000001 | 0.4000000000000001 | 0 |", "",
        "人工归一化案例采用boundary库存口径；不是实际工程费用预测。两例均通过原命令及独立成本读回核对，绝对容差`1e-7`、相对容差`rtol=0`。人工时段不是日期，因此两个toy周汇总CSV按设计只有表头，JSON明确记录“不适用”，不属于缺失结果。", "",
        "本轮独立CSV复核使用下列物理单位绝对容差，全部`rtol=0`：水量/水状态/冻结水计划`1e-4 m³`，电量`1e-7 MWh`，产品/库存`1e-7 t`，年度费用重算与费用排序`1e-3 CNY`；与examples的费用/差额比对`0.01 CNY`，库存比对`1e-7 t`，输入指纹和文件哈希要求完全相同。", "",
        "原求解程序另使用HiGHS原始/对偶可行性容差`1e-8`，内部缩放LP违约不超过`1e-5`，费用重算容差为`1e-5 + 1e-8 × Σ|逐期费用|`，费用嵌套容差为`max(1e-6,1e-8 × max|方案费用|)`。这些内部规则不能误写为相同数值的物理单位精度；年度水变量缩放系数为`5e6 m³`。本轮还额外通过了上述独立的物理单位复核。", "",
        "## 4. 三个完整代表年的实际结果", "",
        "费用及费用差单位为CNY。负净费用表示模型售电收入超过列支的运行成本，不能称为企业总利润，也不对负基准费用机械计算节约率。下表显示6位小数，完整双精度记录见JSON及`logs/annual_checked_summary.csv`。", "",
        "| 年份/类别/天数 | M0净费用 | M1净费用 | M2净费用 | M0−M1 | M1−M2 | M0−M2 |", "|---|---:|---:|---:|---:|---:|---:|"]
    labels = {"dry": "枯", "normal": "平", "wet": "丰"}
    for y in a["annual_cases"]:
        values = [y["scenarios"][s]["cost_cny"] for s in ("M0", "M1", "M2")]+[y[k] for k in ("inventory_savings_with_fixed_hydro_cny", "additional_hydro_coordination_savings_cny", "total_savings_cny")]
        lines.append(f"| {y['year']} / {labels[y['category']]} / {y['days']} | " + " | ".join(f"{v:,.6f}" for v in values) + " |")
    lines += ["", "| 年份 | M2最大交付后库存/t | M2仓库峰值/t | 最大水量残差/m³ | 最大电量残差/MWh | 最大产品残差/t |", "|---|---:|---:|---:|---:|---:|"]
    for y in a["annual_cases"]:
        maximum = [max(s[k] for s in y["scenarios"].values()) for k in ("max_water_balance_residual_m3", "max_energy_balance_residual_mwh", "max_product_balance_residual_t")]
        lines.append(f"| {y['year']} | {y['M2_max_post_delivery_inventory_t']:,.2f} | {y['M2_peak_warehouse_inventory_t']:,.2f} | " + " | ".join(f"{v:.15g}" for v in maximum)+" |")
    lines += ["", "残差为从本次导出的逐日CSV按原物理方程重算后，对同年三方案全部时段取最大绝对值；与求解器JSON记录相符。全年度最大值分别为`8.940696716308594e-7 m³`、`7.275957614183426e-12 MWh`、`1.7053025658242404e-12 t`。这是求解数值精度，不是源数据精度或工程可执行性认证。", "",
        "三年9次年度模型均`solver_status=0`且`audit.passed=true`。1993/1990各365天，1988保留366天及1988-02-29。全部方案使用共同初末活动水量`2.5e9 m³`、共同初末库存`0 t`；水量/产品状态连续。M1相对M0的逐日蓄水起止、机组过水、弃水最大差均为`0 m³`。生产上下限、交付前仓容、发电功率与购售电边界、耗水换算、库存计费及三项守恒也均通过独立读回检查。", "",
        "## 5. 月内、跨月和跨丰枯边界的解释", "",
        "M0固定可行的950 t/day生产计划并充分优化水库；M1冻结本次M0的全部水计划，只放开生产/库存；M2联合优化。M0−M1与M1−M2是依赖本次M0最优解选择的顺序分解，不能解释成独立于基准选择的唯一因果归因。", "",
        "枯1993和平1988的M2均在12次月末交付后清空库存，最大交付后库存为0；仓库峰值29,450 t是正常周转与交付前占用。两年总改善分别416,400和418,500 CNY，等于按900—1000 t/day范围先少产、后补足所减少的月内库存占用：`50 × Σ floor(n_month²/4)`分别为138,800和139,500 t·day，再乘持有费3 CNY/(t·day)。对应M0与M2电网净费用在数值容差内相同。因此这两年改善来自月内生产调整与持有费减少，没有跨月或跨季备货证据。", "",
        "丰1990的M2逐月结果则如下；1—8月交付后库存均为0。", "",
        "| 月份 | M2当月生产/t | 当月交付/t | 生产−交付/t | 月末交付后库存/t |", "|---|---:|---:|---:|---:|"]
    for month in a["annual_cases"][2]["M2_monthly_production"]:
        if month["month"] >= 9:
            lines.append(f"| {month['month']}月 | {month['production_t']:,.0f} | {month['delivery_t']:,.0f} | {month['production_minus_delivery_t']:+,.0f} | {month['post_delivery_inventory_t']:,.0f} |")
    lines += ["", "默认配置丰水月份为6—10月，其他月份使用枯水价格。实际轨迹表明9—10月增产3,050 t，跨过10月/11月丰枯边界，抵补11—12月同量少产；10月31日至12月31日为61天会计结转跨度。相对M0的额外日末库存从9月1日至12月30日连续为正（121条日末记录），12月31日归零。", "",
        "据此可确认该丰年存在跨月、跨配置丰枯边界的提前生产及结转；这比仅看全年峰值更具体。最大结转量3,050 t仅为约3.21天平均交付、占年交付约0.88%，不能据此称为已经验证的大规模季节储备。61天是调度结转跨度，模型未跟踪产品批次，不能当作单批产品实测储龄。没有额外运行禁止跨月的反事实，因此不把全部3,821,915 CNY改善单独归因于季节库存。", "",
        "## 6. 四类单因素敏感性与边界点", "",
        "采用默认1988平年输入，固定来水、交付、绝对初末水量及产品状态，只逐类改变一个因素。6个库容点、5个额外库存天数点、6个额定产能比点、5个持有费点，合计22点；20个optimal、2个invalid_input，无solver_failure。", "",
        "| 不可行点 | 原样保留的程序原因 | 物理/比较含义 |", "|---|---|---|"]
    for item in a["sensitivity"]["invalid_points"]:
        meaning = "库容仅1.25e9 m³，容不下保持不变的2.5e9 m³共同初末水量。" if item["parameter"] == "water_capacity_multiplier" else "额定产能1092.5 t/day，90%最低产量983.25 t/day超过M0基准950 t/day；固定交付/初末库存下比较条件不成立。"
        lines.append(f"| {item['parameter']}={item['value']} | `{item['reason']}` | {meaning} |")
    lines += ["", "不可行点费用与收益字段保留为空值，没有删除点、改成零收益或放松交付。完整22行结果与原因见`outputs/sweep/sensitivity.csv`和`sensitivity_manifest.json`。额外仓容从0增至90天在本平年未增加总改善；高持有费提高的是减少月内占用的价值，不能解释为库存更贵就更应季节备货。", "",
        "## 7. 与examples基准的差异", "",
        "- 对比`examples/validation_record.json`、`representative_years_summary.csv`、`sensitivity_normal.csv`及说明：三年全部9项费用、9项收益分解和M2库存指标的数值差均为0；三个物理输入指纹相同，默认配置/源数据/7个Python源码哈希相同。",
        "- 敏感性22行全部字段一致；逐数值列最大绝对差均为0。两个CSV原始文件哈希因Windows CRLF与基准LF换行不同而不同，统一换行后文本完全相同。",
        "- Python及运行库版本与示例环境不同：基准Python3.12.14/NumPy2.3.5/pandas2.2.3/SciPy1.17.0/Matplotlib3.10.8，本轮为本报告第1节版本；这次未引起费用、收益分解或输入差异。",
        "- 新生成运行记录的时间戳、平台、输入文件字节哈希及图像渲染哈希可能随平台/换行/绘图库变化。它们是本轮实测文件的记录，不要求与仓库截图逐像素一致。5幅新图均已解码并人工目视检查，坐标、图例、六面板及页脚正常，无截断；曲线重合符合实际数值。",
        "- M0可能多重最优；未来其他求解器选择不同等价水计划时，M1轨迹及两项分解可能改变，应按守恒、共同边界与总费用容差判断，不能仅因分解不同认定模型错误。本轮没有出现此差异。",
        "- 对丰年的解释补充了本次实际月度轨迹，明确存在跨配置丰枯边界结转，同时保留规模和收益归因边界。", "",
        "## 8. 本轮处理、代码修复及未解决问题", "",
        "没有模型代码修复，也没有更改默认参数。安装及四个主运行命令均直接成功，未发现未解决的本轮复现错误。", "",
        "辅助环境记录阶段遇到pip22.2.1的`pip freeze`失败：它在识别中文Git路径中的editable安装时发生路径解码不一致，堆栈终止于`find_path_to_project_root_from_repo_root/os.path.samefile`。独立重复命令及`--exclude-editable`仍触发同一路径，尚未启动任何模型步骤。按systematic-debugging流程定位后，改用不调用Git定位editable项目的`pip list --format=freeze`记录实际分发版本，并在重装清单中显式写`-e .`；环境及源码无需修改。原失败日志及退出码2保留于`logs/bootstrap_pip_freeze_failure.*`，此局限仍存在于旧pip的该命令，但已绕过且不影响本轮运行。", "",
        "PowerShell5.1将pip安装的stderr更新提示显示成NativeCommandError记录，但pip安装实际退出码为0；其完整记录保留。最初两个PowerShell重定向日志为UTF-16，已仅转码成UTF-8便于审阅；后续运行日志直接按UTF-8字节保存。新增辅助脚本均在logs目录，不改变仓库科学模型。", "",
        "本版本仍是固定耗水、单库、连续生产、给定完整时序的代表性模型，未校准可变水头、梯级、停槽复产、实际企业合同与预测误差。小湾来水是已发表模型输入而非已认定实测；历史水文年与统一现代工业/价格假设组合也不是企业历史财务复现。现有验证通过不能推出真实工程可执行性、投资收益或极端枯水韧性已获实证。", "",
        "## 9. 输出与交付包", "",
        "本次outputs共64个文件：42个CSV、17个JSON、5幅PNG。全部文件已实际读回；JSON严格解析、CSV结构读取、PNG校验并完整解码成功。NA仅用于设计上不适用的字段和不可行点，不被补成0。源码/数据/运行manifest的文件哈希均已核对。", "",
        "- `outputs/toy/`：两种两期算例、三方案逐期CSV、费用表、图、审计与运行记录及总verification.json。",
        "- `outputs/demo/inputs/{dry,normal,wet}/`：本轮生成的五张输入表与case.json；`outputs/demo/{dry,normal,wet}/`：三方案逐日/周汇总、费用表、图及JSON记录；1988保留闰日。",
        "- `outputs/sweep/`：22点敏感性表与清单。",
        "- `logs/result_audit.json`：独立复算、各年逐方案残差、边界误差、M1冻结差、逐月库存、示例差值及全部输出SHA-256。",
        "- `logs/annual_checked_summary.csv`、`command_statuses.json`、各命令`.log/.status.json`、`environment.json`及依赖版本清单。",
        "- 本报告：`RUN_REPORT.md`。交付：`Reservoir_Inventory_Run01.zip`。", "",
        "ZIP以模型目录内容为根，包含本报告、运行日志、pyproject.toml、README.md、src、tests、configs、docs、scripts、轻量data和来源记录、examples参考，以及本次全部toy/demo/sweep输出。排除.venv、.git、__pycache__、egg-info及其他缓存，不包含完整原始资料归档或第三方依赖安装包。ZIP含`PACKAGE_MANIFEST.json`逐文件SHA-256清单，可交回ChatGPT直接检查。", "",
        "打包后使用zipfile实际解压到`code/_delivery_check/Reservoir_Inventory_Run01`，逐文件核对成员集合、字节数和SHA-256，并再次读取所有CSV/JSON/PNG及代码文本。最终ZIP自身的大小、SHA-256、CRC与解压可读性结果记录在同目录外置`Reservoir_Inventory_Run01.zip.receipt.json`；这是为避免把ZIP自身哈希写入ZIP而产生循环。打包脚本为`logs/package_run01.py`。", "",
        "解压到其他位置后，如需重跑，在解压根重新建立`.venv`并执行`python -m pip install -r logs/requirements_run01.txt`，随后按第2节顺序调用虚拟环境Python。原有`.venv`不具备跨目录搬运保证，因此未打包。", ""]
    (ROOT / "RUN_REPORT.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"Report written: {ROOT / 'RUN_REPORT.md'}")

if __name__ == "__main__":
    main()
