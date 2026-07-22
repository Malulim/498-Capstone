#include "risk_guard.h"
#include <stdlib.h>

int risk_guard_check(const RiskParams *risk_params,
                     int          position,
                     const Decision    *decision,
                    unsigned int in_flight_count) {
    int ret_val = 0;
    if ((unsigned long long)decision->qty*decision->price > risk_params->max_notional_cad) ret_val = 1;
    if (decision->side == BUY) {
        if (abs(position+decision->qty) > risk_params->max_position_shares) ret_val = 1;
    }
    else if (decision->side == SELL) {
        if (abs(position-decision->qty) > risk_params->max_position_shares) ret_val = 1;
    }
    else {}
    // @cye: dont check order rate for now
    if (in_flight_count+1>risk_params->max_in_flight_orders) ret_val = 1;
    return ret_val;
}
