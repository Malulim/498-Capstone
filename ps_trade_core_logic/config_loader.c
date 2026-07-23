#include "config_loader.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <ctype.h>

#ifndef CONFIG_PATH
#define CONFIG_PATH "config.json"
#endif

/* FS3 hard ceilings. A config may tighten these, never exceed them. */
#define FS3_MAX_NOTIONAL_CAD    50000u
#define FS3_MAX_POSITION_SHARES 1000u
#define FS3_MAX_ORDER_RATE      1000u
#define FS3_MAX_IN_FLIGHT       100u

static StrategyParams g_strategy;
static RiskParams     g_risk;
static int            g_strategy_id;
static int            g_loaded = 0;

/* ---- FS4 abort ---------------------------------------------------------- */
static void reject(const char *msg) {
    fprintf(stderr, "[-] FS4 REJECT: %s\n", msg);
    exit(1);
}

/* ---- minimal JSON scan (flat keys, unique across the doc) --------------- */
/* Returns a pointer just past "key" : , or NULL if the key is absent. */
static const char *find_value(const char *text, const char *key) {
    char pat[64];
    snprintf(pat, sizeof(pat), "\"%s\"", key);
    const char *p = strstr(text, pat);
    if (!p) return NULL;
    p += strlen(pat);
    while (*p && *p != ':') p++;
    if (*p != ':') return NULL;
    p++;
    while (*p && isspace((unsigned char)*p)) p++;
    return p;
}

static double require_number(const char *text, const char *key) {
    const char *v = find_value(text, key);
    if (!v || *v == '"') {
        char buf[96];
        snprintf(buf, sizeof(buf), "missing or non-numeric field '%s'", key);
        reject(buf);
    }
    char *end;
    double d = strtod(v, &end);
    if (end == v) {
        char buf[96];
        snprintf(buf, sizeof(buf), "field '%s' is not a number", key);
        reject(buf);
    }
    return d;
}

static long require_int(const char *text, const char *key) {
    double d = require_number(text, key);
    if (d != (double)(long)d) {
        char buf[96];
        snprintf(buf, sizeof(buf), "field '%s' must be an integer", key);
        reject(buf);
    }
    return (long)d;
}

/* Optional integer: returns 1 and sets *out if present, 0 if absent. */
static int opt_int(const char *text, const char *key, long *out) {
    const char *v = find_value(text, key);
    if (!v || *v == '"') return 0;
    *out = (long)strtod(v, NULL);
    return 1;
}

static void require_string(const char *text, const char *key, char *out, size_t n) {
    const char *v = find_value(text, key);
    if (!v || *v != '"') {
        char buf[96];
        snprintf(buf, sizeof(buf), "missing or non-string field '%s'", key);
        reject(buf);
    }
    v++;
    size_t i = 0;
    while (*v && *v != '"' && i + 1 < n) out[i++] = *v++;
    out[i] = '\0';
}

/* ---- range checks ------------------------------------------------------- */
static long checked_positive(long v, const char *key) {
    if (v <= 0) {
        char buf[96];
        snprintf(buf, sizeof(buf), "field '%s' must be positive (got %ld)", key, v);
        reject(buf);
    }
    return v;
}

static unsigned int checked_limit(const char *text, const char *key, unsigned int ceiling) {
    long v = require_int(text, key);
    checked_positive(v, key);
    if ((unsigned long)v > ceiling) {
        char buf[128];
        snprintf(buf, sizeof(buf), "field '%s'=%ld exceeds FS3 ceiling %u", key, v, ceiling);
        reject(buf);
    }
    return (unsigned int)v;
}

static int strategy_id_to_index(const char *id) {
    if (strcmp(id, "momentum") == 0)       return 0;
    if (strcmp(id, "mean_reversion") == 0) return 1;
    if (strcmp(id, "defensive") == 0)      return 2;
    return -1;
}

/* ---- load + validate (once) --------------------------------------------- */
static char *read_file(const char *path) {
    FILE *f = fopen(path, "rb");
    if (!f) reject("config file not found: " CONFIG_PATH);
    fseek(f, 0, SEEK_END);
    long len = ftell(f);
    fseek(f, 0, SEEK_SET);
    if (len <= 0) { fclose(f); reject("config file is empty"); }
    char *buf = (char *)malloc((size_t)len + 1);
    if (!buf) { fclose(f); reject("out of memory reading config"); }
    size_t got = fread(buf, 1, (size_t)len, f);
    fclose(f);
    buf[got] = '\0';
    return buf;
}

static void load_config(void) {
    char *text = read_file(CONFIG_PATH);

    char strategy_id[32];
    require_string(text, "strategy_id", strategy_id, sizeof(strategy_id));
    g_strategy_id = strategy_id_to_index(strategy_id);
    if (g_strategy_id < 0) reject("unknown strategy_id (expect momentum/mean_reversion/defensive)");

    /* Strategy parameters. @cye's StrategyParams keeps all levers in one
     * struct, so we require them all; per-strategy subsetting is her concern. */
    g_strategy.lookback_ticks = (int)checked_positive(require_int(text, "lookback"), "lookback");
    g_strategy.window         = (int)checked_positive(require_int(text, "window"), "window");
    g_strategy.entry_thresh   = (float)require_number(text, "entry_thresh");
    g_strategy.dev_thresh     = (float)require_number(text, "dev_thresh");
    g_strategy.spread_floor   = (int)require_int(text, "spread_floor");
    g_strategy.base_lot       = (int)checked_positive(require_int(text, "base_lot"), "base_lot");
    g_strategy.pos_scalar     = (float)require_number(text, "pos_scalar");

    if (g_strategy.lookback_ticks >= RING_SIZE || g_strategy.window >= RING_SIZE)
        reject("lookback/window must be < RING_SIZE (64)");
    if (g_strategy.entry_thresh <= 0.0f || g_strategy.dev_thresh <= 0.0f)
        reject("entry_thresh/dev_thresh must be positive");
    if (g_strategy.pos_scalar <= 0.0f)
        reject("pos_scalar must be positive");

    /* Risk limits, each capped at its FS3 ceiling. */
    g_risk.max_notional_cad    = checked_limit(text, "max_notional_cad", FS3_MAX_NOTIONAL_CAD);
    g_risk.max_position_shares = checked_limit(text, "max_position_shares", FS3_MAX_POSITION_SHARES);
    g_risk.max_order_rate      = checked_limit(text, "max_order_rate", FS3_MAX_ORDER_RATE);

    /* max_in_flight is not in the design's risk_limits schema yet (see the
     * @cye note in types.h). Read it if present, else default to the FS3
     * ceiling; either way it may not exceed 100. */
    long in_flight;
    if (opt_int(text, "max_in_flight", &in_flight)) {
        checked_positive(in_flight, "max_in_flight");
        if ((unsigned long)in_flight > FS3_MAX_IN_FLIGHT)
            reject("max_in_flight exceeds FS3 ceiling 100");
        g_risk.max_in_flight_orders = (unsigned int)in_flight;
    } else {
        g_risk.max_in_flight_orders = FS3_MAX_IN_FLIGHT;
    }

    free(text);
    g_loaded = 1;
    printf("[+] FS4 config committed: strategy=%s id=%d notional<=%u position<=%u rate<=%u in_flight<=%u\n",
           strategy_id, g_strategy_id, g_risk.max_notional_cad,
           g_risk.max_position_shares, g_risk.max_order_rate, g_risk.max_in_flight_orders);
}

static void ensure_loaded(void) {
    if (!g_loaded) load_config();
}

StrategyParams get_strategy_params_from_config(void)    { ensure_loaded(); return g_strategy; }
RiskParams     get_risk_params_from_config(void)        { ensure_loaded(); return g_risk; }
int            get_active_strategy_id_from_config(void) { ensure_loaded(); return g_strategy_id; }
