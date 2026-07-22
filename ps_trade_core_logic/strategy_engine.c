#include "strategy_engine.h"
#include "types.h"
#include <math.h>

#define HOLD_DECISION ((Decision){HOLD, 0, 0})
#define MIN(a, b) ((a) < (b) ? (a) : (b))

static Decision momentum_strategy(const Snapshot *snap, RollingState *state, int position, const StrategyParams *params) {
    // if cold start？
    if (state->count < params->lookback_ticks) return HOLD_DECISION;

    int mid_now = snap->best_ask_price + snap->best_bid_price;  // 半分单位，不除以 2，保持整数运算

    int idx = (state->write_idx - params->lookback_ticks + RING_SIZE) % RING_SIZE;
    int mid_past = state->mid_ring[idx];

    int qty = params->base_lot*params->pos_scalar;

    Side side; int price;
    int delta = mid_now - mid_past;
    if ((float)delta / mid_now >= params->entry_thresh) {
        side = BUY; price = snap->best_ask_price; }
    else if ((float)delta / mid_now <= -params->entry_thresh) {
        side = SELL; price = snap->best_bid_price; }
    else { return HOLD_DECISION; }

    return (Decision){side, qty, price};
}

static Decision mean_reversion_strategy(const Snapshot *snap, RollingState *state, int position, const StrategyParams *params) {
    // if cold start？
    if (state->count < params->window) return HOLD_DECISION;
    int mid_now = snap->best_ask_price + snap->best_bid_price;  // 半分单位，不除以 2，保持整数运算

    int sum = 0;
    for (int i = 1; i <= params->window; i++) {
        int idx = (state->write_idx - i + RING_SIZE) % RING_SIZE;
        sum += state->mid_ring[idx];
    }
    double ma = (double)sum / params->window;

    double dev = (mid_now - ma) / ma;

    Side side; int price;
    int qty = params->base_lot * params->pos_scalar * MIN(1, fabs(dev) / params->dev_thresh);
    if (dev >= params->dev_thresh) {
        side = SELL; price = snap->best_ask_price; }
    else if (dev <= -params->dev_thresh) {
        side = BUY; price = snap->best_bid_price; }
    else { return HOLD_DECISION; }

    return (Decision){side, qty, price};
}

static Decision defensive_strategy(const Snapshot *snap, RollingState *state, int position, const StrategyParams *params) {
    return HOLD_DECISION;
}

static StrategyFunc strategy_table[] = {
    momentum_strategy,
    mean_reversion_strategy,
    defensive_strategy
};

// 三个策略都要用到的公共动作：把这一 tick 的 mid_now 写进 ring buffer，write_idx 前进一格，count 累加封顶
static void update_rolling_state(RollingState *state, int mid_now) {
    state->mid_ring[state->write_idx] = mid_now;
    state->write_idx = (state->write_idx + 1) % RING_SIZE;
    if (state->count < RING_SIZE) {
        state->count++;
    }
}

Decision strategy_engine_tick(const Snapshot     *snap,
                               RollingState *state,
                               int           position,
                               int           active_strategy_id,
                               const StrategyParams       *strategy_params) {
    // 先跑策略：这一步要用 state 里"到目前为止"的历史（还不包含这一 tick），所以必须在更新 rolling state 之前调用
    Decision decision = strategy_table[active_strategy_id](snap, state, position, strategy_params);

    int mid_now = snap->best_ask_price + snap->best_bid_price;
    update_rolling_state(state, mid_now);

    return decision;
}