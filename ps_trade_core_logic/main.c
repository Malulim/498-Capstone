#include "strategy_engine.h"
#include "risk_guard.h"
#include "config_loader.h" // @cye: from @lucy  => Config Loader: get risk params from config (from EOD)
#include "market_data.h"   // @cye: from @lucy  => Snapshot Poller: get snapshot/market data (from PL)
#include "order_execution.h" // @cye: from @lucy => Order writer(partial): provide execution order (to PL)
#include "order_table.h"
#include <stdio.h>
#include <stdlib.h>

static RollingState rolling_state;
static OrderTable order_table;
// Single-symbol prototype: symbol ID 1 is fixed to Apple Inc. (AAPL).

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
            RiskReject risk_check = risk_guard_check(&risk_params, position, &decision, order_table.in_flight_count);
            if (risk_check != RISK_OK) {
                report_reject(&decision, risk_check);
            } else {
                // begin of the lifetime of an order
                ++order_id; // README 3.1.3.4: increment before assign, counter starts at 0
                if (insert_order_into_table(&order_table, order_id, decision) != 0) {
                    fprintf(stderr,
                            "[-] FATAL: in-flight table full after RiskGuard approved order %u\n",
                            order_id);
                    exit(EXIT_FAILURE);
                }
                execute_order(decision, order_id);
            }
        } else {
            report_hold(&snap);
        }
        // end of the lifetime of an order
        int filled = clean_order_in_table(&order_table, &position); // updates position once T elapses (README 3.2.3.3)
        if (filled > 0) {
            printf("[*] FILL  x%-2d in_flight=%3u position=%5d\n",
                   filled, order_table.in_flight_count, position);
        }
    }
    return 0;
}
