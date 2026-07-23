#ifndef RISK_GUARD_H
#define RISK_GUARD_H

#include "types.h"

int risk_guard_check(const RiskParams *risk_params,
                     int          position,
                     const Decision    *decision,
                    unsigned int in_flight_count);

#endif