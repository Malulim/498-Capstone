#include "risk_guard.h"
#include <stdlib.h>

RiskReject risk_guard_check(const RiskParams *risk_params,
                     int          position,
                     const Decision    *decision,
                     int          in_flight_net_qty,
                    unsigned int in_flight_orders) {
    // @lucy: notional unit fix. qty*price is in cents (price is integer cents),
    // but max_notional_cad is in dollars, so this was rejecting every order.
    // Divide by 100 to compare dollars-to-dollars. Please double-check.
    // check notional value
    if ((unsigned long long)decision->qty*decision->price / 100 > risk_params->max_notional_cad)
        return RISK_NOTIONAL;
    // check position value
    // 敞口 = 已成交仓位 + 在途净股数。只看已成交会漏掉在途的那一批：一个成交周期
    // 内能发出上百单，每单都以为仓位还停在上次结算的值，上限会被穿透。
    long long exposure = (long long)position + in_flight_net_qty;
    long long next_exposure = exposure +
        (decision->side == BUY ? (long long)decision->qty : -(long long)decision->qty);
    // 只拦让敞口变大的单。减仓单必须放行，否则一旦超限就再也降不回来。
    if (llabs(next_exposure) > risk_params->max_position_shares &&
        llabs(next_exposure) > llabs(exposure))
        return RISK_POSITION;
    // @cye: rate 和 in-flight 条数两条先不做，reason code 已留 stub（RISK_RATE /
    // RISK_IN_FLIGHT）。in_flight_net_qty 已在上面的 position 检查里用上了。
    (void)in_flight_orders;
    return RISK_OK;
}
