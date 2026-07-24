#include "order_table.h"
#include <time.h>

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
            table->in_flight_count++;
            return 0;
        }
    }
    return 1;
}

void clean_order_in_table(OrderTable *table, int *position) {
    struct timespec now;
    clock_gettime(CLOCK_MONOTONIC, &now);

    for (int i = 0; i < ORDER_TABLE_SIZE; i++) {
        OrderEntry *entry = &table->orders[i];
        if (entry->state != IN_FLIGHT) continue;
        if (elapsed_seconds(entry->submit_timestamp, now) < FILL_DELAY_SEC) continue;

        /* Fill: apply to position and free the slot straight back to EMPTY.
         * No logger exists yet in this prototype (README 3.2.3.5), so there
         * is no terminal state to park a filled order in. */
        *position += (entry->side == BUY) ? (int)entry->qty : -(int)entry->qty;
        entry->state = EMPTY;
        table->in_flight_count--;
    }
}
