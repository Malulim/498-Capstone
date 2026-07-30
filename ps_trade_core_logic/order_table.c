#include "order_table.h"
#include <time.h>

/* 带方向股数：BUY 为正，SELL 为负。 */
static int signed_shares(Side side, unsigned int qty) {
    return (side == BUY) ? (int)qty : -(int)qty;
}

static double elapsed_seconds(struct timespec start, struct timespec now) {
    return (double)(now.tv_sec - start.tv_sec) + (double)(now.tv_nsec - start.tv_nsec) / 1e9;
}

int insert_order_into_table(OrderTable *table, unsigned int order_id, Decision decision) {
    for (int i = 0; i < ORDER_TABLE_SIZE; i++) {
        OrderEntry *entry = &table->orders[i];
        if (entry->state == EMPTY) {
            entry->order_id = order_id;
            entry->side     = decision.side;
            entry->qty      = decision.qty;
            entry->price    = decision.price;
            clock_gettime(CLOCK_MONOTONIC, &entry->submit_timestamp);
            entry->state    = IN_FLIGHT;
            table->in_flight_order_count++;
            table->in_flight_net_shares += signed_shares(decision.side, decision.qty);
            return 0;
        }
    }
    return 1;
}

int clean_order_in_table(OrderTable *table, int *settled_position_shares) {
    struct timespec now;
    clock_gettime(CLOCK_MONOTONIC, &now);
    int filled_order_count = 0;

    for (int i = 0; i < ORDER_TABLE_SIZE; i++) {
        OrderEntry *entry = &table->orders[i];
        if (entry->state != IN_FLIGHT) continue;
        if (elapsed_seconds(entry->submit_timestamp, now) < FILL_DELAY_SEC) continue;

        /* Fill: free the slot straight back to EMPTY. No logger exists yet in
         * this prototype (README 3.2.3.5), so there is no terminal state to
         * park a filled order in.
         * 敞口从"在途"转到"已成交"，两边同时动，总敞口不变 */
        *settled_position_shares    += signed_shares(entry->side, entry->qty);
        table->in_flight_net_shares -= signed_shares(entry->side, entry->qty);
        entry->state = EMPTY;
        table->in_flight_order_count--;
        filled_order_count++;
    }
    return filled_order_count;
}
