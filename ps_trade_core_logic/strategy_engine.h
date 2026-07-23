#ifndef STRATEGY_ENGINE_H
#define STRATEGY_ENGINE_H

#include "types.h"   /* 因为下面的函数签名用到了 Snapshot / RollingState / Params / Decision，
                         我必须先知道这些类型长什么样，所以先把 types.h 粘贴进来 */

Decision strategy_engine_tick(const Snapshot     *snap,
                               RollingState *state,
                               int           position,
                               int           active_strategy_id,
                               const StrategyParams       *strategy_params);


                               
#endif
