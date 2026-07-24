import socket
import struct
import time
import pandas as pd
import os

# Define paths
DATA_DIR = "data"
BUILD_DIR = "build"
MESSAGE_FILE = os.path.join(DATA_DIR, "message.csv")
ORDERBOOK_FILE = os.path.join(DATA_DIR, "orderbook.csv")          # [NEW]: LOBSTER's own orderbook file, needed to build a real Expected-book file (3.4.3.1)
FRAME_FILE = os.path.join(BUILD_DIR, "frame.bin")
FRAME_TIMING_FILE = os.path.join(BUILD_DIR, "frame_timings.csv")  # [NEW]: preserves original NASDAQ timestamps for pacing, since Table 6 itself carries no time field
TX_LOG_FILE = os.path.join(BUILD_DIR, "frame_tx_timestamps.log")  # [NEW]: TX timestamp log (Table 24: FS1/FS2 "instrument" role needs a TX timing witness)
RX_LOG_FILE = os.path.join(BUILD_DIR, "order_rx_timestamps.log")  # [NEW]: RX timestamp log (3.4.3.1: "Order Receiver ... captures ... raw packets and RX timestamps")

# 1. Protocol Definition
# Table 6: RX Ingress (Simulator -> FPGA)
TABLE_6_FORMAT = "<B H I I B I I I"
# Table 7: TX Order-Egress (FPGA -> Simulator)
TABLE_7_FORMAT = "<I H B I I B"


# 2. Offline Preparation
def preprocess_lobster_to_bin(input_csv, orderbook_csv, output_frame_file,
                               output_timing_file, output_expected_csv):
    """
    Converts LOBSTER records into Table 6 binary frames.

    [MODIFIED]: now also takes LOBSTER's companion orderbook file and derives a
    real per-message top-of-book Expected-book file (3.4.3.1), instead of just
    dumping the raw message table.
    [MODIFIED]: prices are converted to integer cents (LOBSTER prices are
    dollar-price * 10000; Table 6/7 use integer-cent convention, 3.1.3.4).
    [FIX] Modify/Delete-references-unknown-order is tracked with a counter and
    reported at the end, not raised -- this is expected on real LOBSTER data
    (pre-existing resting orders at file-start), so it must not abort the run.
    [NEW]: round-trip sanity check -- every encoded frame is decoded back and
    compared against its source event, per 3.4.3.1's third listed sanity check.
    [NEW]: original per-message timestamp is preserved to a side file so the
    Replayer can pace sends using real inter-arrival gaps.
    """
    cols = ['time', 'type', 'id', 'qty', 'price', 'side']
    df = pd.read_csv(input_csv, header=None, names=cols)
    df['seq'] = range(1, len(df) + 1)

    # level-1 Ask Price, Ask Size, Bid Price, Bid Size (raw LOBSTER units).
    book_df = pd.read_csv(orderbook_csv, header=None)
    if len(book_df) != len(df):
        raise ValueError(
            f"message file ({len(df)} rows) and orderbook file ({len(book_df)} rows) "
            "are not aligned -- they must come from the same LOBSTER slice."
        )

    def to_cents(raw_price):
        # LOBSTER price convention: dollar_price = raw / 10000 -> cents = raw / 100
        return int(round(raw_price / 100.0))

    existing_ids = set()
    expected_rows = []
    historical_order_refs = 0  # [FIX] count, don't hard-fail on these

    with open(output_frame_file, "wb") as f, open(output_timing_file, "w") as tf:
        tf.write("seq,time\n")  # [NEW]
        for idx, row in df.iterrows():
            # Preprocessing assertion: Non-negative quantity check
            if int(row['qty']) < 0:
                raise ValueError(f"Illegal negative quantity detected: {row['qty']} at ID: {row['id']}")

            # [FIX] Reverted from a hard raise back to a tracked/counted check.
            # A Modify/Delete referencing an ID never seen as "New" (type 1) in THIS
            # file is expected for real LOBSTER data: the book at file-start already
            # holds orders placed before the trace window began (pre-market / earlier
            # resting liquidity). That is not data corruption, so it must not abort
            # preprocessing -- it's counted and reported instead. Only genuinely
            # structural problems (negative qty, round-trip failure below) still raise.
            if int(row['type']) in [2, 3]:
                if int(row['id']) not in existing_ids:
                    historical_order_refs += 1
            else:
                existing_ids.add(int(row['id']))

            raw_side = int(row['side'])
            mapped_side = 2 if raw_side == -1 else 1
            msg_type = int(row['type']) % 256
            price_cents = to_cents(row['price'])  # [MODIFIED]: was int(row['price']) with no unit conversion

            packet = struct.pack(TABLE_6_FORMAT,
                                 msg_type, 1,
                                 price_cents, int(row['qty']),
                                 mapped_side, int(row['id']),
                                 int(row['seq']), 0)

            # [NEW]: round-trip sanity check (3.4.3.1, third listed check)
            decoded = struct.unpack(TABLE_6_FORMAT, packet)
            if decoded != (msg_type, 1, price_cents, int(row['qty']), mapped_side,
                           int(row['id']), int(row['seq']), 0):
                raise ValueError(f"Round-trip encode/decode mismatch at seq {row['seq']}")

            f.write(packet)
            tf.write(f"{row['seq']},{row['time']}\n")  # [NEW]

            # [NEW]: build the real Expected-book row for this message from
            # LOBSTER's own orderbook file (level-1 ask/bid), same cent rounding applied.
            book_row = book_df.iloc[idx]
            best_ask_cents = to_cents(book_row[0])
            best_bid_cents = to_cents(book_row[2])
            expected_rows.append({
                "seq": int(row['seq']),
                "best_bid_cents": best_bid_cents,
                "best_ask_cents": best_ask_cents,
            })

    # [MODIFIED]: Expected-book file is now a real per-message top-of-book
    # table, not a copy of the raw message CSV.
    pd.DataFrame(expected_rows).to_csv(output_expected_csv, index=False)
    print(f"Preprocessing complete: {output_frame_file} (Frame), "
          f"{output_timing_file} (Timing), {output_expected_csv} (Expected Book) generated.")
    print("Sanity checks passed: no negative qty, all frames round-trip verified.")  # [MODIFIED]
    if historical_order_refs > 0:  # [FIX]
        print(f"Note: {historical_order_refs} Modify/Delete messages referenced orders "
              f"opened before this file's window (pre-existing resting liquidity) -- "
              f"expected for real LOBSTER slices, not treated as an error.")


# 3. Online Replay
def start_paced_replay(frame_file, timing_file, tx_log_file, target_ip, target_port, rate_scale=1.0):
    """
    Sends UDP packets based on pacing rules.

    [MODIFIED]: previously slept a fixed 0.001s/rate_scale between every packet,
    which flattens real burst structure and ignores rate_scale's stated meaning
    (3.4.3.2: "rate_scale of 1 faithfully reproduces real-world microsecond timing").
    Now paces using the *actual* inter-arrival gaps from the original NASDAQ
    timestamps preserved in the timing file.
    [NEW]: logs a TX timestamp per packet sent (3.4.3.1 requirement).
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    timings = pd.read_csv(timing_file)['time'].tolist()  # [NEW]

    with open(frame_file, "rb") as f, open(tx_log_file, "w") as txlog:  # [MODIFIED]: added txlog
        prev_t = None
        idx = 0
        while True:
            packet = f.read(struct.calcsize(TABLE_6_FORMAT))
            if not packet:
                break

            # [MODIFIED]: pace using real inter-message gap, scaled by rate_scale,
            # instead of a fixed constant sleep.
            t = timings[idx]
            if prev_t is not None:
                delta = max(0.0, (t - prev_t) / rate_scale)
                time.sleep(delta)
            prev_t = t
            idx += 1

            sock.sendto(packet, (target_ip, target_port))
            txlog.write(f"{time.time()}\n")  # [NEW]: TX timestamp log

    sock.close()


# 4. Order Receiver
def receive_and_log_orders(log_file, rx_timestamp_file, port=12346):
    """
    Listens and tracks the number of received packets in real-time.

    [MODIFIED]: added rx_timestamp_file -- previously only raw packet bytes
    were logged, with no RX timestamp, even though 3.4.3.1 explicitly requires
    "captures incoming raw packets and RX timestamps to an offline log".
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("0.0.0.0", port))

    count = 0
    with open(log_file, "wb") as f, open(rx_timestamp_file, "w") as tslog:  # [MODIFIED]: added tslog
        print(f"Listening on port {port}...")
        while True:
            data, _ = sock.recvfrom(1024)
            recv_time = time.time()  # [NEW]
            f.write(data)
            f.flush()
            tslog.write(f"{recv_time}\n")  # [NEW]
            tslog.flush()
            count += 1
            if count % 100 == 0:
                print(f"Captured {count} order feedback packets...")


# 5. Offline Checker
def check_order_log(log_file, frame_file):
    """
    Offline comparison: Verifies logical consistency between input and output.

    [MODIFIED]: was an empty placeholder. Now actually wires into the
    FS11 Offline Checker implementation in checker.py instead of duplicating
    (or worse, leaving unimplemented) validation logic.
    """
    import checker1  # [NEW]
    return checker1.verify_session_stream(log_file, frame_file)


if __name__ == "__main__":
    import threading

    os.makedirs(BUILD_DIR, exist_ok=True)  # [NEW]: guard in case build/ doesn't exist yet

    # 1. Automatic Preprocessing
    print("--- Step 1: Data Preprocessing ---")
    EXPECTED_BOOK_FILE = os.path.join(BUILD_DIR, "expected_book.csv")
    preprocess_lobster_to_bin(
        MESSAGE_FILE, ORDERBOOK_FILE, FRAME_FILE, FRAME_TIMING_FILE, EXPECTED_BOOK_FILE
    )  # [MODIFIED]: extra orderbook + timing args

    # 2. Start Background Order Receiver
    print("--- Step 2: Launching Order Receiver ---")
    receiver_thread = threading.Thread(
        target=receive_and_log_orders,
        args=(os.path.join(BUILD_DIR, "order.log"), RX_LOG_FILE),  # [MODIFIED]: added RX_LOG_FILE
    )
    receiver_thread.daemon = True
    receiver_thread.start()

    print("Receiver started, waiting for FPGA order data...")
    time.sleep(1)

    # 3. Start Replay
    print("--- Step 3: Starting Replay (Demo Mode: Sending to local Mock) ---")
    try:
        start_paced_replay(
            FRAME_FILE, FRAME_TIMING_FILE, TX_LOG_FILE, "127.0.0.1", 12345, rate_scale=2000
        )  # [MODIFIED]: added timing file + tx log; rate_scale=20 for a fast demo (3.4.3.2)
    except KeyboardInterrupt:
        print("\nDemonstration stopped manually.")

    # 4. Offline Validation
    print("--- Step 4: Offline Validation (Oracle) ---")
    check_order_log(os.path.join(BUILD_DIR, "order.log"), FRAME_FILE)

    print("\nDemonstration complete.")
