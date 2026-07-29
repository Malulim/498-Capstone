#include "market_data.h"
#include <stdio.h>
#include <stdlib.h>
#include <time.h>

/* Tick budget for the synthetic stream. Override at build time with
 * -DMARKET_DATA_MAX_TICKS=N. On-board this whole file is replaced. */
#ifndef MARKET_DATA_MAX_TICKS
#define MARKET_DATA_MAX_TICKS 400
#endif

/* Feed pacing, ms per tick. Real market data arrives paced, and without it the
 * session ends in under a millisecond so FILL_DELAY_SEC never elapses and no
 * order ever fills. 400 ticks x 1ms ~= 0.4s. Set 0 to disable. */
#ifndef MARKET_DATA_TICK_MS
#define MARKET_DATA_TICK_MS 1
#endif

#define START_MID_CENTS 10000
#define BASE_QTY        300

static unsigned int emitted = 0;

/* Own LCG, not rand(): rand() differs across libc, so the same seed would not
 * replay identically on another machine. */
static unsigned int rng_state = 20260729u;
static unsigned int next_rand(void) {
    rng_state = rng_state * 1103515245u + 12345u;
    return (rng_state >> 16) & 0x7FFF;
}
/* Uniform integer in [lo, hi]. */
static int rand_range(int lo, int hi) {
    return lo + (int)(next_rand() % (unsigned)(hi - lo + 1));
}

/* Five market regimes. The feed states the regime; what the strategy does with
 * it is the strategy's business, not something this file asserts. */
static int phase_of(unsigned int i) {
    unsigned int pct = (i * 100u) / MARKET_DATA_MAX_TICKS;
    if (pct < 15) return 0;   /* warmup ranging */
    if (pct < 40) return 1;   /* uptrend */
    if (pct < 60) return 2;   /* downtrend */
    if (pct < 75) return 3;   /* choppy ranging */
    return 4;                 /* parabolic rally */
}

static const char *PHASE_BANNER[5] = {
    "PHASE 0  WARMUP RANGING   mid +-6c/tick        spread 1-3c",
    "PHASE 1  UPTREND          mid +10..45c/tick    spread 2-5c",
    "PHASE 2  DOWNTREND        mid -45..-10c/tick   spread 2-5c",
    "PHASE 3  CHOPPY RANGING   mid +-8c/tick        spread 1-2c",
    "PHASE 4  PARABOLIC RALLY  mid +200..600c/tick  spread 4-12c",
};

/* Banner on phase change so the log says what regime the feed is now in. */
static void log_phase(unsigned int i) {
    static int last = -1;
    int p = phase_of(i);
    if (p == last) return;
    last = p;
    printf("\n===== %s =====\n", PHASE_BANNER[p]);
}

/* Mid price in integer cents: per-phase trend plus bounded noise. */
static int mid_at(unsigned int i) {
    static int mid = START_MID_CENTS;
    int drift;
    switch (phase_of(i)) {
        case 0:  drift = rand_range(-6, 6);      break;  /* flat, sub-threshold */
        case 1:  drift = rand_range(10, 45);     break;  /* up, > 1% per 5 ticks */
        case 2:  drift = rand_range(-45, -10);   break;  /* down */
        case 3:  drift = rand_range(-8, 8);      break;  /* flat again */
        default: drift = rand_range(200, 600);   break;  /* stress: run past $500 */
    }
    mid += drift;
    if (mid < 100) mid = 100;  /* never let the synthetic book go non-positive */
    return mid;
}

/* Spread widens when volatile, tightens when calm. Ranges from 1 to 12 cents,
 * i.e. both sides of the default spread_floor of 2. */
static int spread_at(unsigned int i) {
    switch (phase_of(i)) {
        case 0:  return rand_range(1, 3);
        case 1:
        case 2:  return rand_range(2, 5);
        case 3:  return rand_range(1, 2);
        default: return rand_range(4, 12);
    }
}

Snapshot get_snapshot_from_market_data(void) {
    if (emitted >= MARKET_DATA_MAX_TICKS) {
        printf("\n[+] market data stream exhausted after %u ticks\n", emitted);
        exit(0);
    }

    if (MARKET_DATA_TICK_MS > 0) {
        struct timespec gap = { .tv_sec = 0,
                                .tv_nsec = (long)MARKET_DATA_TICK_MS * 1000000L };
        nanosleep(&gap, NULL);
    }

    unsigned int i = emitted++;
    log_phase(i);
    int mid    = mid_at(i);
    int spread = spread_at(i);

    /* spread generated independently of mid, so it can be odd or 1 */
    Snapshot snap;
    snap.best_bid_price = (unsigned int)(mid - spread / 2);
    snap.best_ask_price = snap.best_bid_price + (unsigned int)spread;
    snap.best_bid_qty   = (unsigned int)rand_range(BASE_QTY / 2, BASE_QTY * 2);
    snap.best_ask_qty   = (unsigned int)rand_range(BASE_QTY / 2, BASE_QTY * 2);
    return snap;
}
