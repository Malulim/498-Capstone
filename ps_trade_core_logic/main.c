#include "strategy_engine.h"
#include "config_loader.h" // @cye: from @lucy
#include "market_data.h"   // @cye: from @lucy
#include "order_execution.h" // @cye: from @lucy

static RollingState rolling_state;
static OrderTable order_table;
// @cye: symbol这件事被我忘了 不过这个项目也只有一个

int main() {
    RiskParams risk_params = get_risk_params_from_config();
    StrategyParams strategy_params = get_strategy_params_from_config();
    int active_strategy_id = get_active_strategy_id_from_config();

    int position = 0;
    unsigned int order_id = 0;
    while (1) {
        Snapshot snap = get_snapshot_from_market_data();
        Decision decision = strategy_engine_tick(&snap, &rolling_state, position, active_strategy_id, &strategy_params);
        if (decision.side != HOLD) {
            int risk_check = risk_guard_check(&risk_params, position, &decision, order_table.in_flight_count);
            if (risk_check == 0) {
                // TODO: insert_order_into_table(&order_table, order_id, decision);
                execute_order(decision, order_id); // @cye: reach maximum?
                //position += (decision.side == BUY ? decision.qty : -decision.qty); @cye: move to clean order
            }
        }
        // TODO: clean_order_in_table(&order_table); // @cye: clean filled orders
    }
    return 0;
}