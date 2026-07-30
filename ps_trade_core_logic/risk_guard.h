#ifndef RISK_GUARD_H
#define RISK_GUARD_H

#include "types.h"

/* 本单名义金额，加元。qty*price 是"分"，除 100 换成"元"再跟 max_notional_cad 比。
 * 拒单日志要打同一个数，所以放在这里共用，避免两处公式跑偏。 */
unsigned long long order_notional_cad(const Decision *decision);

/* Returns RISK_OK (0) if the order passes, else which limit rejected it.
 *   position          = 已成交仓位（股）
 *   in_flight_net_qty = 在途订单净股数（股，BUY 正 SELL 负）→ 用于 max_position_shares
 *   in_flight_orders  = 在途订单条数 → 留给 max_in_flight，尚未启用 */
RiskReject risk_guard_check(const RiskParams *risk_params,
                     int          position,
                     const Decision    *decision,
                     int          in_flight_net_qty,
                    unsigned int in_flight_orders);

#endif