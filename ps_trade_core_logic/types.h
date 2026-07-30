#ifndef TYPES_H
#define TYPES_H

#include <time.h>

/* 一个 tick 的行情快照——四个字段永远一起出现，捆成一个整体传递 */
typedef struct {
    unsigned int best_bid_price;
    unsigned int best_bid_qty;
    unsigned int best_ask_price;
    unsigned int best_ask_qty;
} Snapshot;

/* 策略输出的判定结果 */
typedef enum { HOLD, BUY, SELL } Side;

typedef struct {
    Side         side;
    unsigned int qty;
    unsigned int price;  // @cye: BUY 用 snapshot 的 best_ask_price，SELL 用 best_bid_price，谁来算这个值待定
} Decision;

/* 从 FS4 JSON config 加载进来的 session 级参数（第二层输入，不是逐 tick 变化的） */
typedef struct {
    // lookback_ticks: momentum
    int    lookback_ticks;  // @cye: config schema (3.3.3.5 / Table 21) 里这个字段叫 "lookback"，不带 _ticks 后缀，跟队友对 config schema 时确认要不要统一
    // window: mean_reversion
    int    window;
    // entry_thresh: momentum
    float entry_thresh;
    // dev_thresh: mean_reversion
    float dev_thresh;
    // defensive usage
    int    spread_floor;
    // flowing 2 to determine qty
    int    base_lot;        // @cye: README 447 行原文把它当固定常量（100 shares）描述，没出现在 Table 21/624 的 config schema key 列表里；这里决定让它可配置，需要跟队友同步这个改动
    float pos_scalar;
} StrategyParams;
/* rolling state：固定大小的 mid price 历史环形缓冲区 */
#define RING_SIZE 64

typedef struct {
    int mid_ring[RING_SIZE];
    int write_idx;
    int count;
} RollingState;

typedef struct {
    unsigned int max_notional_cad;
    unsigned int max_position_shares;
    unsigned int max_order_rate;        // @cye: skip for now
    unsigned int max_in_flight_orders;  // @cye: 不在 config schema(625 行)的 risk_limits 列表里——FS3 说 in-flight 上限是硬顶(100)，但文档没写这个数字本身能不能被 config 收紧，需要跟队友确认这个字段到底该不该从 JSON 读
} RiskParams;

typedef enum { EMPTY, IN_FLIGHT } OrderState;

/* FS3 要求拒单带 reason code。RISK_OK = 0，调用点 `== 0 放行` 的判断不变 */
/* 顺序同 FS3 列出的四条限制 */
typedef enum {
    RISK_OK = 0,
    RISK_NOTIONAL,
    RISK_POSITION,
    RISK_RATE,       // @cye: stub，检查尚未启用，见 risk_guard.c
    RISK_IN_FLIGHT   // @cye: stub，检查尚未启用，见 risk_guard.c
} RiskReject;

typedef struct {
    unsigned int    order_id;
    Side            side;
    unsigned int    qty;
    unsigned int    price;
    struct timespec submit_timestamp;
    OrderState      state;
} OrderEntry;

typedef struct {
    OrderEntry   orders[100];
    /* 两个"在途"量，量纲不同，别混：
     *   in_flight_order_count = 在途订单条数（单）→ max_in_flight，管表深度
     *   in_flight_net_shares  = 在途带方向股数之和（股，BUY 加 SELL 减）
     *                           → max_position_shares，管仓位敞口
     * 会互相抵消：10 单 BUY + 10 单 SELL 时 net_shares=0 但 order_count=20。 */
    unsigned int in_flight_order_count;
    int          in_flight_net_shares;
} OrderTable;

typedef Decision (*StrategyFunc)(const Snapshot *snap, RollingState *state, int position, const StrategyParams *params);

#endif
