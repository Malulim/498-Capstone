#include "order_execution.h"
#include "risk_guard.h"   /* order_notional_cad: 拒单行和风控用同一个公式 */
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
    put_u16_le(out + 4,  AAPL_SYMBOL_ID);
    out[6] = side_byte;
    put_u32_le(out + 7,  decision->qty);
    put_u32_le(out + 11, decision->price);
    out[15] = 0x00;  /* pad */
    return 0;
}

void execute_order(Decision decision, unsigned int order_id) {
    /* pkt = the 16-byte Table 7 packet. Nothing transmits it yet. */
    unsigned char pkt[ORDER_PACKET_BYTES];
    if (encode_order(&decision, order_id, pkt) != 0) {
        printf("[-] TX skip: order %u has invalid fields\n", order_id);
        return;
    }

    // @cye: 定宽格式符让小数点和 ID 对齐（7月24日 practice demo 上 Bill 的建议）
    printf("[+] TX id=%05u sym=%s(%d) %s qty=%5u px=%8.2f\n",
           order_id, AAPL_SYMBOL_NAME, AAPL_SYMBOL_ID,
           decision.side == BUY ? "BUY " : "SELL",
           decision.qty, decision.price / 100.0);

    /* Raw Table 7 hex dump -- too noisy for the demo, re-enable to check byte layout.
    printf("  [");
    for (int i = 0; i < ORDER_PACKET_BYTES; i++) printf("%02x", pkt[i]);
    printf("]\n");
    */
}

void report_hold(const Snapshot *snap) {
    printf("[=] HOLD  bid=%8.2f ask=%8.2f\n",
           snap->best_bid_price / 100.0, snap->best_ask_price / 100.0);
}

static const char *reject_reason_text(RiskReject reason) {
    switch (reason) {
        case RISK_NOTIONAL:  return "notional";
        case RISK_POSITION:  return "position";
        case RISK_RATE:      return "rate";
        case RISK_IN_FLIGHT: return "in-flight";
        default:             return "unknown";
    }
}

void report_reject(const Decision *decision, RiskReject reason,
                   int exposure, const RiskParams *risk_params) {
    printf("[-] REJECT   %s qty=%5u px=%8.2f  reason=%-8s",
           decision->side == BUY ? "BUY " : "SELL",
           decision->qty, decision->price / 100.0,
           reject_reason_text(reason));

    /* 打出触发这条限制的那个数，免得还要翻上一行 FILL 才知道为什么被拒 */
    switch (reason) {
        case RISK_POSITION: {
            int delta = (decision->side == BUY) ? (int)decision->qty : -(int)decision->qty;
            printf("  exposure=%+d %+d -> %+d /%u",
                   exposure, delta, exposure + delta,
                   risk_params->max_position_shares);
            break;
        }
        case RISK_NOTIONAL:
            printf("  notional=%llu /%u",
                   order_notional_cad(decision), risk_params->max_notional_cad);
            break;
        default:
            break;
    }
    printf("\n");
}
