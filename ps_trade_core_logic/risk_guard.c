#include "risk_guard.h"
#include <stdlib.h>

RiskReject risk_guard_check(const RiskParams *risk_params,
                     int          position,
                     const Decision    *decision,
                    unsigned int in_flight_count) {
    // @lucy: notional unit fix. qty*price is in cents (price is integer cents),
    // but max_notional_cad is in dollars, so this was rejecting every order.
    // Divide by 100 to compare dollars-to-dollars. Please double-check.
    // check notional value
    if ((unsigned long long)decision->qty*decision->price / 100 > risk_params->max_notional_cad)
        return RISK_NOTIONAL;
    // check position value
    long long next_position = position;
    if (decision->side == BUY)
        next_position += decision->qty;
    else
        next_position -= decision->qty;
    if (llabs(next_position) > risk_params->max_position_shares)
        return RISK_POSITION;
    // @cye: rate 和 in-flight 两条先不做，reason code 已留 stub（RISK_RATE /
    // RISK_IN_FLIGHT）。启用 in-flight 时 position 检查要一并把在途敞口算进去
    (void)in_flight_count;
    return RISK_OK;
}
