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

    /* FILL 行的读法，一次性说明，免得三个数看不出关系 */
    // printf("[i] 读法: exposure = settled + pending，与 max_position_shares(%u) 比较\n"
    //        "[i]        settled=已成交仓位  pending=在途未成交净股数  orders=在途单数\n",
    //        risk_params.max_position_shares);

    int settled_position_shares = 0;
    unsigned int order_id = 0;
    while (1) {
        Snapshot snap = get_snapshot_from_market_data();
        Decision decision = strategy_engine_tick(&snap, &rolling_state, settled_position_shares, active_strategy_id, &strategy_params);
        if (decision.side != HOLD) {
            RiskReject risk_check = risk_guard_check(&risk_params, settled_position_shares, &decision,
                                                     order_table.in_flight_net_shares,
                                                     order_table.in_flight_order_count);
            if (risk_check != RISK_OK) {
                report_reject(&decision, risk_check,
                              settled_position_shares + order_table.in_flight_net_shares, &risk_params);
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
        int filled_order_count = clean_order_in_table(&order_table, &settled_position_shares); // updates position once T elapses (README 3.2.3.3)
        if (filled_order_count > 0) {
            /* 加法写在行里：settled + pending = exposure，就是风控查的那个数 */
            printf("[*] FILL x%-2d  settled=%+6d  pending=%+6d (%3u orders)"
                   "  ->  exposure=%+6d /%5u\n",
                   filled_order_count, settled_position_shares, order_table.in_flight_net_shares,
                   order_table.in_flight_order_count,
                   settled_position_shares + order_table.in_flight_net_shares,
                   risk_params.max_position_shares);
        }
    }
    return 0;
}
