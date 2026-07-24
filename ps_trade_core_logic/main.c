#include "strategy_engine.h"
#include "risk_guard.h"
#include "config_loader.h" // @cye: from @lucy  => Config Loader: get risk params from config (from EOD)
#include "market_data.h"   // @cye: from @lucy  => Snapshot Poller: get snapshot/market data (from PL)
#include "order_execution.h" // @cye: from @lucy => Order writer(partial): provide execution order (to PL)
#include "order_table.h"

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
                ++order_id; // README 3.1.3.4: increment before assign, counter starts at 0
                insert_order_into_table(&order_table, order_id, decision);
                execute_order(decision, order_id);
            }
        }
        clean_order_in_table(&order_table, &position); // updates position once T elapses (README 3.2.3.3)
    }
    return 0;
}