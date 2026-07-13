# Cross-Reference Fix Checklist — 498 finalizing.md

Target file: `498 finalizing.md`
Verified against: Section 2 spec tables, Section 3 header structure (3.1–3.4), Table 1–29 captions, Figure 1–6 captions, References [1]–[16].

Checked clean (no action needed): all 16 citations [1]–[16] have a 1:1 match between in-text use and the References list; all 29 Table captions are numbered sequentially with no gaps/duplicates; all 6 Figures are numbered sequentially and consistently per subsystem; all `Decision N` cross-references (within and across 3.1–3.4) point to the correct decision; all FS/NFS spec IDs referenced elsewhere resolve correctly against Section 2 **except** the items below.

---

## 1. Structural: "five subsystems" claim does not match the heading structure

**Location:** Line 65, opening paragraph of Section 3.

**Current text:**
> "This detailed design is organized as **five** open-ended subsystem designs rather than as a single monolithic trading appliance. The **PL RX Market-Data Ingest and Book Builder subsystem** owns deterministic packet reception... The **PL TX Order Egress and PS Interface subsystem** owns the reverse path..."

**Problem:** The paragraph names PL RX and PL TX as if they are two independent top-level subsystems (making 5 total: PL RX, PL TX, PS, EOD, Exchange Simulator). But the actual heading structure only has **4 top-level subsystems**: `## 3.1 PL (FPGA) Market Data Path Subsystem`, `## 3.2 PS...`, `## 3.3 EOD...`, `## 3.4 Exchange Simulator...`. RX and TX only exist as sub-subsections **inside** 3.1 (`#### 3.1.3.1 RX Ingress and Book-Builder Subsystem` and `#### 3.1.3.2 TX Order-Egress and PS Interface Subsystem`), each of which lacks its own Overview / Engineering Design Process / Final Design Details / Compliance Summary — they share 3.1's.

**Why it matters:** If your rubric requires 5 open-ended subsystems (5/6-person team footnote in the official marking rubric), a grader counting from headings will count 4, not 5. The prose claim and the document skeleton disagree.

**Fix options (pick one — this is an architecture decision, not a find-replace):**
- **(A)** Promote PL RX and PL TX to genuine top-level sections: split current `## 3.1` into `## 3.1 PL RX Market-Data Ingest and Book Builder Subsystem` and `## 3.2 PL TX Order Egress and PS Interface Subsystem`, each with its own 3.X.1/3.X.2/3.X.3/3.X.4 structure, and renumber the current 3.2/3.3/3.4 (PS/EOD/Simulator) up to 3.3/3.4/3.5. This is a substantial restructure — all downstream cross-references to `3.2.x`, `3.3.x`, `3.4.x` throughout the document would need renumbering too.
- **(B)** Walk back the "five subsystems" claim to "four subsystems, with the PL subsystem internally organized around two cross-lane sub-designs (RX and TX)" — smaller edit, but does not earn 5-subsystem credit if that's actually required.

**Action:** Decide (A) vs (B) with the team before editing — confirm actual team size against the rubric footnote first if not already settled.

---

## 2. NFS8 is referenced 3× but never defined in Section 2

Section 2.2 (`## 2.2 Non-Functional Specifications`, lines 48–61) only defines NFS1–NFS6. NFS8 does not exist anywhere in Section 2, yet Section 3.2 cites it as a real spec three times:

| # | Line | Current text | Fix |
|---|---|---|---|
| 2.1 | 292 | `\| NFS8 \| Owner of software fault handling: malformed-config rejection at load time, fault-coded logging, continue-without-restart. \|` (row in Table 10, PS spec mapping) | Either (a) add an NFS8 row to the Section 2.2 table with this exact description and an Essential/Non-essential flag, **or** (b) if NFS8 was deliberately dropped from scope (as in an earlier draft of this report), delete this row and fold "software fault handling" into an existing spec's description instead. |
| 2.2 | 378 | `\| 0x20–0x2C \| DIAG_PARSE_ERR, DIAG_FCS_FAIL, DIAG_DROP_OOW, DIAG_TX_BACKPRESSURE \| R \| NFS8/NFS2 counters, read periodically by core 0 \|` | Update to match whatever is decided in 2.1 — either keep `NFS8/NFS2` (if NFS8 is added to Section 2) or drop the `NFS8/` prefix and leave just `NFS2 counters...` (if NFS8 is cut). |
| 2.3 | 482 | `Linux + isolated core, no hot-path allocation; fault paths per NFS8; HOLD Mode as safe state` (Table 18, NFS4 compliance row) | Same decision as above — either keep `per NFS8` (if defined) or replace with prose description of the fault paths without a spec-ID citation. |

**Recommended fix:** Add NFS8 to Section 2.2's table (Table 2) as a real non-functional spec — it's clearly load-bearing content (referenced 3 times, ties to real design work in 3.2.3.1/3.2.3.4/3.2.4), just missing its definition row. Suggested wording, matching the style of NFS1–NFS6:

```
| NFS8 | Software fault handling | Malformed configuration is rejected at load time, all faults are fault-coded and logged, and the session continues without a restart. | [pick a verification method consistent with the other rows] | Y |
```

---

## 3. FS13 does not exist in this document's spec numbering — should be FS11

This document renumbered specs after dropping the earlier text/LLM-sentiment specs (Section 2.1's FS table goes FS1–FS12, with FS11 = "Order packet format"). FS13 is a leftover from the pre-renumbering draft and does not exist here.

| # | Line | Current text | Fix |
|---|---|---|---|
| 3.1 | 208 | `The latched fields are packed into the fixed-format FS13 order payload defined in *Table 7* below.` | Change `FS13` → `FS11` |
| 3.2 | 224 | `...so FS13 verification can parse captured packets independently of PS-side formatting logic.` | Change `FS13` → `FS11` |
| 3.3 | 239 | `*Table 7: TX Order-Egress and PS Interface Subsystem Output Packet Contract (FS13)*` | Change `(FS13)` → `(FS11)` |

---

## 4. "input validation per 3.3.3.6" should be 3.3.3.1

**Location:** Line 504, Table 19 (EOD spec mapping), NFS5 row.

**Current text:**
> `\| NFS5 (non-ess.) \| Sole owner: full pipeline (ingestion → classification → optimization → approval prompt) within 30 minutes; input validation per 3.3.3.6. \|`

**Problem:** Section `3.3.3.6` is titled "FS10 status reporting" (logging), not input validation. The actual input-validation content ("schema check, monotonic-timestamp check, minimum-history check...") lives in **3.3.3.1** ("Data import and Parameter Engineering").

**Fix:** Change `3.3.3.6` → `3.3.3.1` in this line.

---

## 5. "canonical serialization (3.3.3.7)" should be 3.3.3.5

**Location:** Line 630, "FS7 determinism" paragraph in section 3.3.3.3.

**Current text:**
> `...strictly sequential evaluation over ordered-list grids with canonical serialization (3.3.3.7), a single designated verification host...`

**Problem:** Section `3.3.3.7` is "Operator Approval and configuration transmission (FS8)" — unrelated to serialization format. Section **3.3.3.5** ("JSON configuration schema") is where serialization actually lives — its `provenance` field includes a `grid hash`, which is the real evidence for "serialization is canonical."

**Fix:** Change `(3.3.3.7)` → `(3.3.3.5)` in this sentence.

---

## 6. Table 18 (PS Specification Compliance Summary) cites subsection numbers that don't exist

Section `3.2.4` ("Specification Compliance Summary") has **no subsections** — it's a single table with no 3.2.4.1/3.2.4.2 breakdown. Section `3.2.3.3` ("Runtime Risk Guard") has no 3.2.3.3.1 either. All of the following are dangling:

| # | Line | Current text | Correct target | Why |
|---|---|---|---|---|
| 6.1 | 381 | `\| 0x54 \| TX_READY \| R \| Egress flow-control invariant (see 3.2.4.1) \|` (Table 15, register map) | **3.2.2** | 3.2.2 Decision 3 is where TX_READY's role as "a correctness invariant rather than a performance mechanism" and the software timing budget (Table 13) are actually discussed. |
| 6.2 | 446 | `Busy-poll isolated core + register reads; ≤ ~5 μs software path vs. ~29 μs share (3.2.4.1)` (Table 18, FS2 row) | **3.2.2** | Same — the "~5 μs vs ~29 μs" figure is Table 13 in 3.2.2 Decision 3. |
| 6.3 | 476–477 | `FS2 path is the PS contribution; margin table 3.2.4.1` (Table 18, NFS1 row — split awkwardly across a wrapped table cell as "table 3." + "2.4.1") | **3.2.2** | Same table (Table 13) is the actual source of "margin." |
| 6.4 | 461 | `Static allocation, decision-complete + sampled-snapshot ring, async flush (3.2.4.2)` (Table 18, FS5 row) | **3.2.3.5** | 3.2.3.5 "Execution Logger and Console" is where the logging ring, allocation, and flush behavior are described. |
| 6.5 | 466 | `Pre-allocated open-order table sized exactly to the FS3's in-flight ceiling; Risk Guard rejects at limit; modeled terminal transitions (3.2.3.3.1)` (Table 18, FS12 row) | **3.2.3.3** | 3.2.3.3 "Runtime Risk Guard" is where the open-order table and modeled fill delay T are described; there is no `.1` sub-subsection — just drop the trailing `.1`. |

**Fix:** Replace `3.2.4.1` → `3.2.2` (3 places: 6.1, 6.2, 6.3), `3.2.4.2` → `3.2.3.5` (1 place: 6.4), `3.2.3.3.1` → `3.2.3.3` (1 place: 6.5).

---

## 7. "Table 3.1.3" is a leftover old-style table reference — should be "Table 6"

**Location:** Line 740, section 3.4.3.1 ("Components and artifacts").

**Current text:**
> `- **Frame file** — the slice pre-encoded into Table 3.1.3 payloads, each frame keeping its original NASDAQ timestamp for pacing.`

**Problem:** This document uses sequential table numbering throughout (Table 1, 2, 3... 29), not the old dotted `3.1.3`-style numbering. The RX payload contract this sentence is referring to is **Table 6** ("RX Ingress and Book-Builder Subsystem Input Payload Contract") — confirmed by section 3.4.1 (line 679), which correctly calls it "Table 6" for the identical concept.

**Fix:** Change `Table 3.1.3` → `Table 6`.

---

## Summary table for quick execution

| # | Line(s) | Find | Replace with |
|---|---|---|---|
| 3.1 | 208 | `FS13 order payload` | `FS11 order payload` |
| 3.2 | 224 | `so FS13 verification` | `so FS11 verification` |
| 3.3 | 239 | `Contract (FS13)` | `Contract (FS11)` |
| 4 | 504 | `input validation per 3.3.3.6` | `input validation per 3.3.3.1` |
| 5 | 630 | `canonical serialization (3.3.3.7)` | `canonical serialization (3.3.3.5)` |
| 6.1 | 381 | `invariant (see 3.2.4.1)` | `invariant (see 3.2.2)` |
| 6.2 | 446 | `~29 μs share (3.2.4.1)` | `~29 μs share (3.2.2)` |
| 6.3 | 476–477 | `margin table 3.2.4.1` | `margin table 3.2.2` |
| 6.4 | 461 | `async flush (3.2.4.2)` | `async flush (3.2.3.5)` |
| 6.5 | 466 | `transitions (3.2.3.3.1)` | `transitions (3.2.3.3)` |
| 7 | 740 | `Table 3.1.3 payloads` | `Table 6 payloads` |
| 2 | 292, 378, 482 | NFS8 undefined | **Not a find-replace** — needs a team decision: add NFS8 to Section 2.2's table, or cut all 3 references. See item 2 above for suggested wording. |
| 1 | 65 | "five subsystems" vs. 4 headings | **Not a find-replace** — architecture decision. See item 1 above for options (A) restructure to 5 real top-level subsystems, or (B) walk back the prose claim to 4. |

Items 3, 4, 5, 6, 7 are safe, unambiguous mechanical fixes. Items 1 and 2 need a decision before anyone edits — flag those to whoever owns scope/spec decisions before touching the text.
