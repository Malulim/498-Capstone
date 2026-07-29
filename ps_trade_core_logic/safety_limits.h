#ifndef SAFETY_LIMITS_H
#define SAFETY_LIMITS_H

/*
 * FS3 hard ceilings. Session configuration may tighten these values but must
 * never exceed them. Keep these compile-time constants independent of JSON.
 */
#define FS3_MAX_NOTIONAL_CAD     50000u
#define FS3_MAX_POSITION_SHARES   1000u
#define FS3_MAX_ORDER_RATE        1000u
#define FS3_MAX_IN_FLIGHT          100u

#endif
