# Progress Report — Report Content
### Group 2026.36 · ECE498A · 本文件只含正文，无任何注释
### 需要替换的地方一律标为 `[[FILL-n]]`，共 8 处，清单见 notes 文件

---

# Title Page

University of Waterloo
Faculty of Engineering
Department of Electrical and Computer Engineering

**Adaptive Quantitative Trading Accelerator**

Group 2026.36

| Name | Student Number |
|:---|:---|
| Hanyu Yao | [[FILL-1]] |
| Catherine Ye | [[FILL-2]] |
| Ashley Wu | 20901849 |
| Panzy Pan | [[FILL-4]] |
| Lucy Sun | [[FILL-5]] |

Consultant: William Bishop

Submitted: August 2, 2026

---

# 1. Overview of Project

## 1.1 Revised Project Abstract

Algorithmic trading systems are limited by the time between a price change reaching a machine and an order leaving it. A software-only system spends much of that time inside the operating system, while published hardware-accelerated systems complete the same path in hundreds of nanoseconds. The objective of this project is to design a trading platform that splits this path between reconfigurable logic and an embedded processor, so that timing-critical stages run as dedicated hardware while strategy logic stays changeable in software. The logic takes market data directly off the network, decodes a fixed-width binary protocol, maintains a ten-level record of pending orders, and publishes the best prices through a shared register interface. The processor evaluates a configurable strategy, filters every proposed order through a risk check, and returns approved orders to the hardware. An overnight pipeline classifies the next day's market conditions, searches a bounded parameter space against recorded sessions, and proposes a configuration that only a human operator can approve. The design draws on digital hardware design and verification, network protocol design, and embedded software scheduling and hardware-software interfacing. Its main advantage is that critical-path latency is bounded by hardware rather than by an operating system.

## 1.2 Original Project Timeline

[[FILL-6]]

*Figure 1: Original project timeline, reproduced without modification from the Detailed Design and Project Timeline Document, Section 4.6.*

The timeline above is the original plan and is reproduced unchanged. The order in which the hardware tasks were actually completed differs from it; the reason and its consequences are discussed in Section 3.1.

---

# 2. Current Status of Project

## 2.1 Prototype Completion

The prototype is estimated at 76.5% complete. This section derives that figure rather than asserting it.

Completion is assessed against the five-subsystem decomposition of the Detailed Design, weighted by estimated total implementation effort. Within each subsystem, progress is scored against four verification gates treated as independent: lint-clean, unit-simulated, integration-simulated, and hardware-verified. Passing simulation does not imply that synthesis or timing closure will pass, so the gates are not collapsed, and the outstanding hardware gate is charged against each subsystem that has not yet cleared it rather than accounted for separately.

*Table 1: Weighted prototype completion by subsystem.*

| Subsystem | Weight | State | Completion | Contribution |
|:---|---:|:---|---:|---:|
| Market-data ingest and book builder | 15% | Design frozen; register window reserved; implementation deferred by a now-resolved hardware constraint (Section 3.1); no register-transfer code written | 15% | 2.3% |
| Order egress and processor interface | 20% | Register-transfer code complete; unit and integration testbenches pass; mutation-tested; synthesis, timing closure, and board bring-up outstanding | 80% | 16.0% |
| Strategy and risk software | 25% | Full decision loop compiles and runs end to end on a synthetic feed; deployment to the target processor and core isolation outstanding | 88% | 22.0% |
| Overnight optimization pipeline | 25% | Ingestion, classification, parameter sweep, and approval workflow implemented with automated tests | 92% | 23.0% |
| Exchange simulator | 15% | Preprocessor, replayer, receiver, and offline checker implemented | 88% | 13.2% |
| **Total** | **100%** | | | **76.5%** |

No separate weight is assigned to system integration. Integration is a verification gate rather than a designed subsystem, and the cost of clearing it is already charged against the two subsystems that have not cleared it. No part of the system has yet run on the board: the hardware gate is open for the two hardware-dependent subsystems, and the figures above reflect that.

The verification evidence supporting each figure is as follows.

**Order egress path.** All four modules pass lint with all warnings enabled, and pass their testbenches with non-zero exit on failure. The register bank testbench observes doorbell pulse width with an independent monitor process rather than inside the driving task, so a wrong timing assumption in the driver cannot mask a wrong pulse. Mutation testing was applied to both the register bank and the top-level wiring: fifteen deliberately corrupted variants of the register bank and six of the top level were all detected. The remaining work is synthesis, timing closure at 125 MHz, vendor Ethernet controller configuration, and board bring-up — three gates that simulation cannot substitute for.

**Strategy and risk software.** The complete hot path compiles and executes on a development host: configuration load and validation, snapshot acquisition, strategy dispatch, risk filtering, in-flight order tracking, and order encoding. The market feed is currently synthesized locally rather than received from hardware, using a self-contained linear congruential generator so that a given seed reproduces the same tick sequence on any machine, and integer cent arithmetic throughout so results are bit-reproducible. The interface that the synthetic feed implements is the same one the hardware path supplies, so substituting the real feed replaces one file without changing its callers.

**Overnight pipeline.** Data ingestion with schema, monotonicity, and minimum-history validation; the percentile-threshold regime classifier; the deterministic parameter sweep; and the operator approval workflow are all implemented, each with an automated test. A data health check tool reports whether the configured parameter grids are appropriate for the available replay data.

**Exchange simulator.** The dataset preprocessor, paced replayer, order receiver, and offline packet checker are implemented. The preprocessor's three structural invariants were exercised across a full recorded trading day with zero violations, and its output is byte-identical across repeated runs.

This estimate is consistent with the consultant's assessment recorded in Appendix B, which places prototype construction in the 75% to 90% band. No reconciliation is therefore required.

## 2.2 Student Hours

*Table 2: Student hours contributed to date.*

| Team member | Hours as of Detailed Design (July 12) | Hours since | Total |
|:---|---:|---:|---:|
| Hanyu Yao | 72 | [[FILL-7]] | [[FILL-7]] |
| Catherine Ye | 74 | [[FILL-7]] | [[FILL-7]] |
| Ashley Wu | 64.5 | 57 | 121.5 |
| Panzy Pan | 71 | [[FILL-7]] | [[FILL-7]] |
| Lucy Sun | 73 | [[FILL-7]] | [[FILL-7]] |
| **Total** | **362** | [[FILL-7]] | [[FILL-7]] |

Every group member has met the expected commitment of approximately 120 hours, and the distribution across members is even. The consultant's assessment in Appendix B records very high confidence that the group has invested appropriate effort and time. The hours in Table 2 correspond entry by entry to the individual logs in Appendix A.

---

# 3. Discussion

## 3.1 Confidence in Completion

The group has very high confidence that the prototype will be fully constructed and will satisfy every essential specification by the design symposium in March. This confidence rests on three observations.

First, no essential specification currently identifies a design gap. Every essential specification closes analytically with margin, as summarized in the compliance tables of the Detailed Design: the market-data path closes its 1.5 microsecond snapshot budget in 77 clock cycles with a 32% worst-case margin; the software decision path closes its 30 microsecond budget with roughly five times margin; and projected resource use is approximately 11% of logic elements and 3% of block memory on the target device, well inside the 75% and 85% ceilings. What remains is empirical confirmation on hardware, not design work.

Second, the largest remaining item is bounded and specified. The market-data ingest and book-builder path has no register-transfer code written, but its design is frozen, its input packet layout and register contract are fixed, and the register bank it writes into is already implemented with its address window reserved. The work is therefore implementation against a settled interface rather than open design.

Third, the consultant records very high confidence on the same question in Appendix B, and identifies the remaining work as integration and thorough testing rather than unresolved design.

The order in which the hardware work was completed departs from the original timeline of Section 1.2, and the reason is a resolved external constraint rather than slippage. The first stage of the market-data ingest path terminates the physical Ethernet link, so that path could neither be written against real interface constraints nor meaningfully verified on the development board initially available, whose Ethernet interface is wired to the processing system rather than to the reconfigurable logic. The order-egress path carries no such dependency: its downstream interface is a streaming bus, which a testbench can drive directly, so it was the one hardware lane that could be advanced and verified while the constraint held. The group therefore reordered the two lanes rather than idling on the blocked one.

That reordering carries forward rather than being written off. Building the egress lane first established the shared register bank, the golden-frame oracle that serves as the sole authority for the packet layout, and the mutation-testing method by which both were checked. The ingest path reuses all three: the register bank already reserves its address window and requires only new entries in the read multiplexer and write decoder, with no change to the bus protocol logic. A development board carrying an Ethernet interface on the reconfigurable-logic side is now in hand, so the constraint is lifted and ingest-path implementation is unblocked.

The principal risk is that hardware bring-up exposes problems that simulation cannot: vendor Ethernet controller misconfiguration producing frames that are illegal on the wire while every simulation stays green, timing closure at 125 MHz, and metastability on asynchronous reset release, for which no synchronizer is currently present. These are enumerated explicitly in the module specification rather than discovered late. The winter allocations for refinement, timing closure, and end-to-end integration in Section 1.2 are unchanged; the ingest-path implementation displaced by the constraint above is absorbed into the fall term ahead of them.

## 3.2 Level of Challenge

The consultant assessed the project at level three, indicating that it arguably requires substantial upper-year engineering knowledge, and noted in the written feedback that the remaining work consists of integrating the components into the final design and testing it thoroughly. The group accepts this assessment and reads it as identifying where the project's difficulty has yet to be demonstrated rather than where it is absent.

The demonstration presented four subsystems verified in isolation, three of them in software and one in simulation. The engineering content that distinguishes this project — that the timing-critical path is dedicated digital hardware rather than software — was therefore visible as design and simulation, but not as a working hardware path. The group intends to close this gap directly, and the work is already scheduled in the timeline of Section 1.2 rather than added in response to the feedback.

Four specific items move the project from a set of verified components to a demonstrated hardware system.

1. **Completing the market-data ingest and book-builder logic.** This is the subsystem where the hardware argument lives: cut-through parsing that decodes fields while the frame is still arriving, a frame-check-gated commit so that no corrupted frame reaches the book, and a combinational reduction network that extracts the best bid and ask within a single clock edge. None of this exists in an off-the-shelf component.

2. **Synthesis and timing closure at 125 MHz.** Simulation, synthesis, and timing closure are three independent gates. Meeting a positive worst negative slack at 125 MHz with the parsing, book, and reduction logic in place is the quantitative claim that the design is genuinely hardware, and it is verified by tool report rather than by assertion.

3. **Board bring-up and end-to-end integration.** The vendor Ethernet controller configuration contract, the reset synchronizer, and the physical link between the host and the board are all items that no simulation can confirm. Bringing the full loop up — market data entering the reconfigurable logic, a decision made on the processor, and an order leaving on the wire — is the demonstration that the March symposium shows.

4. **Measurement against the specifications.** The latency figures currently supporting the design are derived analytically. Replacing them with instrumented measurements on hardware converts the central claim of the project from an argument into a result.

---

# Appendix A: Student Logs

[[FILL-8]]

---

# Appendix B: Initial Prototype Demonstration Feedback Sheet

[[FILL-8]]