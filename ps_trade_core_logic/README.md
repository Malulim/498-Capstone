# PS Trade Core (Subsystem 3.2)

PS 侧 intraday 交易循环。`main.c` 是 Core 1 热路径主循环:
取快照 → 策略 → 风控 → 发单。

## 模块与分工
| 文件 | 作用 | Spec | 负责人 |
|---|---|---|---|
| `config_loader.c/.h` | 读校验 config.json | FS4 | @lucy |
| `market_data.c/.h` | 提供快照(现为合成流) | 3.2.3.1 | @lucy |
| `order_execution.c/.h` | Table 7 订单编码 | FS11 | @lucy |
| `strategy_engine.c/.h` | 策略引擎 | FS2 | @cye |
| `risk_guard.c/.h` | 风控 | FS3 | @cye |
| `order_table.c/.h` | in-flight 订单表 insert/clean | FS12 | @cye |
| `main.c` / `types.h` | 主循环 + 数据结构 | — | @cye |

## Demo on Windows (PowerShell)
```powershell
cd ps_trade_core_logic
mingw32-make          # 或见下方 gcc 全命令
.\ps_core.exe
```

## Demo on ARM (PetaLinux, ssh 到板子)
```bash
cd ps_trade_core_logic
make                  # PetaLinux rootfs 需装 gcc/make,或用交叉编译
./ps_core
```

## 不用 make 时的完整 gcc 命令
```bash
gcc -Wall -Wextra -O2 -std=c11 -o ps_core \
    main.c strategy_engine.c risk_guard.c \
    config_loader.c market_data.c order_execution.c order_table.c -lm
```

## 合成行情流 (market_data.c)

上板前的行情由本文件合成,**不是真实数据**。目的不是像真实市场,而是在 0.4s 内
把交易循环的各条分支都走一遍。接真实 feed 时整个文件替换,
`get_snapshot_from_market_data()` 接口不变。

三个设计选择:
- **自带 LCG**(种子 20260729),不用 `rand()`。`rand()` 各 libc 实现不同,同一种子
  换机器不能复现。自己实现 → 任何机器上逐 tick 一致,可当 golden reference。
- **全程整数 cents**,不用浮点,避免误差和不可复现。
- **1ms/tick 节流**。不节流则 400 tick 在 1ms 内跑完,`FILL_DELAY_SEC` 永不到期,
  一单都不会成交。

### 每次调用的七步(顺序敏感)
| # | 动作 | 位置约束 |
|---|---|---|
| 1 | 耗尽检查 `emitted >= MAX_TICKS` → `exit(0)` | 在取数前;第 401 次调用直接退进程 |
| 2 | `nanosleep(TICK_MS)` | 见上方节流说明 |
| 3 | `i = emitted++` | 取 tick 号并推进 |
| 4 | `log_phase(i)` 打 `=====` banner | 在快照生成前,banner 下第一行即该 phase 首 tick |
| 5 | `mid_at(i)` | **有状态**:累加 static `mid`。每 tick 必须且只能调一次 |
| 6 | `spread_at(i)` | 无状态,独立于 mid → spread 可为奇数、可为 1 |
| 7 | 组装 `bid = mid - spread/2`, `ask = bid + spread`, 两个 qty | |

**每 tick 固定消耗 4 次 RNG draw**(mid 1 + spread 1 + qty 2),顺序固定,序列才可
复现。调换 5/6/7 的顺序或多调一次 `rand_range` 会改变整个 session 的输出。

两个细节:
- `spread / 2` 是整数除法,spread 为奇数时 bid 偏低半分。`ask - bid` 仍严格等于
  spread,但 `bid + ask != 2 * mid`(差 1 分)。strategy 用的正是 `bid + ask`。
- `if (mid < 100) mid = 100` 是 $1 下限钳位。phase 2 长期下跌可能把价格打到 0 以下,
  而 Snapshot 价格字段是 `unsigned int`,负数会绕成天文数字。

### Phase 时间线
边界按**百分比**算,改 `MARKET_DATA_MAX_TICKS` 时五段比例不变。
feed 只声明行情形态,不声明策略应该做什么 —— 那是 strategy 的事。

| Phase | tick (共 400) | mid drift | spread | mid 轨迹 |
|---|---|---|---|---|
| 0 warmup ranging | 0–59 | ±6c/tick | 1–3c | ~$100 横盘 |
| 1 uptrend | 60–159 | +10..45c | 2–5c | $100 → ~$127 |
| 2 downtrend | 160–239 | −45..−10c | 2–5c | ~$127 → ~$105 |
| 3 choppy ranging | 240–299 | ±8c | 1–2c | ~$105 横盘 |
| 4 parabolic rally | 300–399 | +200..600c | 4–12c | $105 → ~$505 |

spread 在 phase 3 收到 1c(低于默认 `spread_floor`=2)、phase 4 张到 12c,
让 spread 门槛的两侧在同一 session 内都能被观察到。

## 每 tick 管线 (main.c)
```
取快照 → 策略(用不含本 tick 的历史) → 写入 ring → 风控 → 插表 → 发单 → 扫成交
```
两处顺序是刻意的:
- 策略在 ring 更新**之前**跑,否则 lookback 会把当前 tick 算进历史。
- 扫成交在 tick **末尾**,所以本 tick 的成交对本 tick 的风控不可见 —— 一个 tick 的滞后。

## 关键变量与口径

命名规则:**名字带"是什么"+"什么单位"**。符号规则只有一条:
**BUY = 正, SELL = 负**,且只对 shares 类生效;`price` / `notional` / `*_count` 恒非负。

### ① Session 参数(config.json 加载,全程不变)
`StrategyParams`

| 变量 | 单位 | 现值 | 用于 |
|---|---|---|---|
| `lookback_ticks` | ticks | 5 | momentum (config 里叫 `lookback`,名字待统一) |
| `window` | ticks | 20 | mean_reversion,必须 ≤ `RING_SIZE`(64) |
| `entry_thresh` | 比率 float | 0.01 = 1% | momentum |
| `dev_thresh` | 比率 float | 0.02 = 2% | mean_reversion |
| `spread_floor` | cents | 2 | defensive |
| `base_lot` | shares | 100 | 三策略共用,`qty = base_lot × pos_scalar` |
| `pos_scalar` | 倍数 float | 1.0 | 同上 |

`RiskParams` —— 四条都顶在 FS3 硬顶,一条没收紧

| 变量 | 单位 | 现值 | FS3 硬顶 | 实现 |
|---|---|---|---|---|
| `max_notional_cad` | 加元 | 50000 | 50000 | 是 |
| `max_position_shares` | shares | 1000 | 1000 | 是 |
| `max_order_rate` | orders/s | 1000 | 1000 | 否, stub |
| `max_in_flight_orders` | orders | 100 | 100 | 否, stub |

### ② 行情(每 tick 变)
`Snapshot`:`best_bid_price` / `best_ask_price` 为**整数 cents**($100 存成 10000),
恒正;`best_bid_qty` / `best_ask_qty` 为 shares,恒正。四字段永远一起传。

> **单位陷阱:两个东西都叫 mid,差 2 倍。** market_data 内部 `mid` 是 cents(≈10000);
> strategy 的 `mid_now = best_ask + best_bid` **没除以 2**,是半分(≈20000),为保持
> 整数运算。不除也对,因为 momentum 算的是比率 `delta / mid_now`,2 倍在分子分母
> 抵消。但读代码时别把两个 mid 当同一个数。

### ③ 策略状态与输出
`RollingState`:`mid_ring[64]`(单位**半分**)、`write_idx`(0..63)、`count`
(累计 tick 数,到 64 封顶,用于判 cold start)。

`Decision`:`side`(HOLD/BUY/SELL,**方向只存在这里**)、`qty`(shares,**恒正**)、
`price`(整数 cents,BUY 取 ask / SELL 取 bid)。

### ④ 风控:三个敞口量,量纲不同,不能互相替代
| 变量 | 单位 | 符号 | 维护点 | 对应限额 |
|---|---|---|---|---|
| `settled_position_shares` | shares | ± (+long/−short) | 成交时 | —— |
| `in_flight_net_shares` | shares | ± 同上 | 下单 +, 成交 − | 与上一个**相加**后比 `max_position_shares` |
| `in_flight_order_count` | orders | 恒正 0..100 | 下单 +1, 成交 −1 | `max_in_flight`(未启用) |

会互相抵消:10 单 BUY + 10 单 SELL 时 `net_shares = 0` 但 `order_count = 20`。
所以敞口看 net_shares,表满不满看 order_count。

派生量(不存字段,用时算):
```
exposure_shares      = settled_position_shares + in_flight_net_shares   ← 风控查这个
next_exposure_shares = exposure_shares ± 本单 qty
order_notional_cad() = qty × price / 100        ← cents 除 100 换成加元
```

`RiskReject`:`RISK_OK`=0 / `RISK_NOTIONAL` 已实现 / `RISK_POSITION` 已实现 /
`RISK_RATE` stub / `RISK_IN_FLIGHT` stub。检查顺序是 notional 先于 position,
所以两条同时超限时 reason 显示 notional。

### ⑤ 订单表与编译期常量
`OrderEntry`:`order_id`(**序号**,只增不重用)、`side`、`qty`、`price`、
`submit_timestamp`、`state`(EMPTY/IN_FLIGHT)。

| 常量 | 值 | 来历 |
|---|---|---|
| `ORDER_TABLE_SIZE` | 100 | FS12 追踪上限 |
| `FILL_DELAY_SEC` | 0.1s | README 3.2.3.3:1000 orders/s × 0.1s = 100,**推出**表容量 |
| `RING_SIZE` | 64 | 必须 ≥ `window`(20) |
| `MARKET_DATA_MAX_TICKS` | 400 | 只影响 demo 长度 |
| `MARKET_DATA_TICK_MS` | 1 | 决定在途窗口 ≈ 100 tick |

### 三个"数量"最容易混
| 变量 | 单位 | 日志样例 | 是什么 |
|---|---|---|---|
| `order_id` | —— | `id=00009` | 身份证号,第 9 单 |
| `in_flight_order_count` | orders | `( 9 orders)` | 现在有 9 张在飞 |
| `qty` | shares | `qty=100` | 每张 100 股 |

## 日志格式
```
===== PHASE 1  UPTREND  mid +10..45c/tick  spread 2-5c =====   行情形态切换
[=] HOLD  bid=  100.17 ask=  100.20                            无动作
[+] TX id=00001 sym=AAPL(1) BUY  qty=  100 px=  101.19         发单
[*] FILL x1   settled=  +100  pending=  +900 (  9 orders)  ->  exposure= +1000 / 1000
[-] REJECT   BUY  qty=  100 px=  103.99  reason=position  exposure=+1000 +100 -> +1100 /1000
[-] REJECT   BUY  qty=  100 px=  500.60  reason=notional  notional=50060 /50000
```
- FILL 行:`settled + pending = exposure / 上限`,三个数都是 shares。连续几行
  `exposure` 不变而 settled/pending 互换,即敞口从在途转为已成交,总量守恒。
- REJECT 行按 reason 打出触发它的那个数:position 摊开加法,notional 打本单金额。
  两者与风控用同一个公式(`order_notional_cad()` 在 risk_guard.h 共用)。

## 已知缺口
- `RISK_RATE` / `RISK_IN_FLIGHT` 未实现。**表满不是拒单,是崩** ——
  `insert_order_into_table` 返回非 0 后 main 打 FATAL 并 `exit(1)`,
  而 README 3.2.3.3 要求插入前就拒掉。当前配置在途峰值 10 单(容量 100),
  但撑住它的是仓位上限在节流,不是这条检查。
- FS3 验收要四条限制各一个违规测试,现在只能产出两条(notional / position)。
  顶层 README 已标 "Pending four-violation injection test"。
- momentum 不做仓位管理(`position` 参数在函数体内未使用),趋势里无脑同向加仓,
  唯一的刹车是风控。风控本该是兜底,不该是唯一刹车。
- `position` 是按"0.1s 后必定全额按报价成交"模拟出来的,没有部分成交 / 交易所
  拒单 / 撤单。基于它的仓位风控,可信度上限就是这个假设。
- 所有金额标 CAD 但标的写 AAPL(美股, USD 计价),单币种建模,未做汇率换算。

## 说明
- **config.json**:程序读运行目录下的 `config.json`(相对路径)。放别处用
  `-DCONFIG_PATH=\"/path/to/config.json\"` 编译指定。非法配置会 FS4 REJECT 并退出。
- **只依赖标准库**(stdio/stdlib/string/ctype/math),无第三方依赖。
- **上板对接(未做)**:`market_data` 现在是合成行情、`order_execution` 现在是打印;
  真正接 PL 时换成 AXI-Lite 寄存器 busy-poll 读 / doorbell 写,接口不变,需等 bitstream。
