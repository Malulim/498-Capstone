#include "order_execution.h"
#include <stdio.h>

/* Byte order matches Exchange_simulator/checker.py (little-endian '<'), the
 * FS11 offline oracle. If the PL lands big-endian, change this and the checker
 * together. */
static void put_u16_le(unsigned char *p, unsigned int v) {
    p[0] = v & 0xFF; p[1] = (v >> 8) & 0xFF;
}
static void put_u32_le(unsigned char *p, unsigned int v) {
    p[0] = v & 0xFF; p[1] = (v >> 8) & 0xFF;
    p[2] = (v >> 16) & 0xFF; p[3] = (v >> 24) & 0xFF;
}

/* Table 7 side encoding: Decision Side BUY(1)/SELL(2) maps to 0x01/0x02. */
static int table7_side(Side side, unsigned char *out) {
    if (side == BUY)  { *out = 0x01; return 0; }
    if (side == SELL) { *out = 0x02; return 0; }
    return 1;  /* HOLD must never reach egress */
}

int encode_order(const Decision *decision, unsigned int order_id, unsigned char *out) {
    unsigned char side_byte;
    if (table7_side(decision->side, &side_byte)) return 1;
    if (decision->qty   > 0xFFFFFFFFu) return 1;
    if (decision->price > 0xFFFFFFFFu) return 1;

    /* order_id@0 symbol@4 side@6 qty@7 price@11 pad@15 */
    put_u32_le(out + 0,  order_id);
    put_u16_le(out + 4,  ORDER_SYMBOL);
    out[6] = side_byte;
    put_u32_le(out + 7,  decision->qty);
    put_u32_le(out + 11, decision->price);
    out[15] = 0x00;  /* pad */
    return 0;
}

void execute_order(Decision decision, unsigned int order_id) {
    unsigned char pkt[ORDER_PACKET_BYTES];
    if (encode_order(&decision, order_id, pkt) != 0) {
        printf("[-] TX skip: order %u has invalid fields\n", order_id);
        return;
    }

    printf("[+] TX id=%u sym=%d %s qty=%u px=%.2f  [",
           order_id, ORDER_SYMBOL,
           decision.side == BUY ? "BUY " : "SELL",
           decision.qty, decision.price / 100.0);
    for (int i = 0; i < ORDER_PACKET_BYTES; i++) printf("%02x", pkt[i]);
    printf("]\n");
}
