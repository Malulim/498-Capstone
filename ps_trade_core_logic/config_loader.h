#ifndef CONFIG_LOADER_H
#define CONFIG_LOADER_H

#include "types.h"

/* C.2 Config Loader (FS4, Section 3.2.3.4)
 * Loads + validates config.json once, on the first getter call. Any schema,
 * type, range, or FS3-ceiling violation prints a reason and exit(1)s, so the
 * trading loop is unreachable without a valid config. */

StrategyParams get_strategy_params_from_config(void);
RiskParams     get_risk_params_from_config(void);
int            get_active_strategy_id_from_config(void);  /* 0=momentum 1=mean_reversion 2=defensive */

#endif
