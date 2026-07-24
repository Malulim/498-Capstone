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

## 说明
- **config.json**:程序读运行目录下的 `config.json`(相对路径)。放别处用
  `-DCONFIG_PATH=\"/path/to/config.json\"` 编译指定。非法配置会 FS4 REJECT 并退出。
- **只依赖标准库**(stdio/stdlib/string/ctype/math),无第三方依赖。
- **上板对接(未做)**:`market_data` 现在是合成行情、`order_execution` 现在是打印;
  真正接 PL 时换成 AXI-Lite 寄存器 busy-poll 读 / doorbell 写,接口不变,需等 bitstream。
