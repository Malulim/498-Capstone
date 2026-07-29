#ifndef RISK_GUARD_H
#define RISK_GUARD_H

#include "types.h"

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