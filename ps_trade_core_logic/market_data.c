#include "market_data.h"
#include <stdio.h>
#include <stdlib.h>

/* Tick budget for the synthetic stream. Override at build time with
 * -DMARKET_DATA_MAX_TICKS=N. On-board this whole file is replaced. */
#ifndef MARKET_DATA_MAX_TICKS
#define MARKET_DATA_MAX_TICKS 64
#endif

#define START_MID_CENTS 10000
#define HALF_SPREAD     1      /* 2-cent spread */
#define BASE_QTY        300

static unsigned int emitted = 0;

/* Three phases (rising / falling / ranging) so the stream exercises BUY,
 * SELL and HOLD branches. Slope is steep enough to cross a ~0.5%/lookback
 * momentum threshold; the ranging phase stays flat to yield HOLD.
 * Prices are integer cents. */
#define SLOPE_CENTS 30
static int mid_at(unsigned int i) {
    unsigned int third = MARKET_DATA_MAX_TICKS / 3;
    if (third == 0) third = 1;
    int drift;
    if (i < third)              drift = (int)i * SLOPE_CENTS;                                /* rising */
    else if (i < 2 * third)     drift = (int)(third * SLOPE_CENTS) - (int)(i - third) * SLOPE_CENTS;  /* falling */
    else                        drift = ((int)(i % 4) - 2) * 2;                              /* ranging near start */
    return START_MID_CENTS + drift;
}

Snapshot get_snapshot_from_market_data(void) {
    if (emitted >= MARKET_DATA_MAX_TICKS) {
        printf("\n[+] market data stream exhausted after %u ticks\n", emitted);
        exit(0);
    }

    unsigned int i = emitted++;
    int mid = mid_at(i);

    Snapshot snap;
    snap.best_bid_price = (unsigned int)(mid - HALF_SPREAD);
    snap.best_bid_qty   = BASE_QTY + (i % 7) * 25;
    snap.best_ask_price = (unsigned int)(mid + HALF_SPREAD);
    snap.best_ask_qty   = BASE_QTY + (i % 5) * 25;
    return snap;
}
