#ifndef ORDER_TABLE_H
#define ORDER_TABLE_H

#include "types.h"

/* C.5 In-Flight Order Table (FS3 in-flight check, FS12 tracking, README 3.2.3.3)
 * Fixed 100-slot table for the traded symbol. An order enters IN_FLIGHT on
 * submission; after the modeled fill delay FILL_DELAY_SEC it is treated as
 * filled: position updates and the slot frees back to EMPTY. */

#define ORDER_TABLE_SIZE 100
#define FILL_DELAY_SEC   0.1  /* README 3.2.3.3: T = 0.1s modeled fill delay */

/* Insert a risk-approved decision as a new in-flight order (first EMPTY slot).
 * Returns 0 on success, non-zero if no EMPTY slot exists. Should not happen
 * in practice: risk_guard_check already rejects the order once
 * in_flight_count would exceed max_in_flight_orders <= ORDER_TABLE_SIZE. */
int insert_order_into_table(OrderTable *table, unsigned int order_id, Decision decision);

/* Sweep the table for IN_FLIGHT orders older than FILL_DELAY_SEC, apply their
 * fill to *position, and free their slot back to EMPTY. */
void clean_order_in_table(OrderTable *table, int *position);

#endif
