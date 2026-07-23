#ifndef MARKET_DATA_H
#define MARKET_DATA_H

#include "types.h"

/* C.3 Market Data Input (Section 3.2.3.1)
 * Returns the next top-of-book snapshot. Deterministic synthetic stream now;
 * on-board this becomes an AXI-Lite seqlock read of the PL register bank.
 * When the synthetic stream is exhausted it prints a summary and exit(0)s,
 * since Catherine's main.c loops with while(1). */
Snapshot get_snapshot_from_market_data(void);

#endif
