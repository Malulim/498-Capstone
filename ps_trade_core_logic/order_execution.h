#ifndef ORDER_EXECUTION_H
#define ORDER_EXECUTION_H

#include "types.h"

/* C.6 Order Egress (FS11, Table 7)
 * Encodes a risk-approved Decision into the fixed 16-byte order packet and
 * emits it. Console/hex now; on-board this becomes AXI-Lite writes to
 * 0x40-0x4C then DOORBELL at 0x50 (payload first, doorbell last). */

#define ORDER_PACKET_BYTES 16
#define AAPL_SYMBOL_ID     1
#define AAPL_SYMBOL_NAME   "AAPL"

/* Pack a Decision into out[16] per Table 7 (little-endian). Returns 0 on
 * success, non-zero if a field does not fit its width. */
int encode_order(const Decision *decision, unsigned int order_id, unsigned char *out);

/* Encode + emit. Signature matches Catherine's main.c call. */
void execute_order(Decision decision, unsigned int order_id);

/* HOLD ticks and rejections consume no order_id, so without these they leave
 * no trace in the console output at all. */
void report_hold(const Snapshot *snap);
void report_reject(const Decision *decision, RiskReject reason);

#endif
