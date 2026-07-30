# PS trade core: @cye's engine/risk + @lucy's config/market/order
CC     = gcc
CFLAGS = -Wall -Wextra -O2 -std=c11
SRC    = main.c strategy_engine.c risk_guard.c config_loader.c market_data.c order_execution.c order_table.c
HDR    = safety_limits.h
BIN    = ps_core
LOG    = session.log

# Cross-platform clean/run: Windows (cmd from mingw32-make) vs Unix (board).
ifeq ($(OS),Windows_NT)
    RM  = cmd /c del /q
    EXE = $(BIN).exe
    RUN = $(BIN).exe
else
    RM  = rm -f
    EXE = $(BIN)
    RUN = ./$(BIN)
endif

$(EXE): $(SRC) $(HDR)
	$(CC) $(CFLAGS) -o $(EXE) $(SRC) -lm

run: $(EXE)
	$(RUN)

# Session log instead of console. *.log is gitignored.
log: $(EXE)
	$(RUN) > $(LOG) 2>&1
	@echo "session written to $(LOG)"

clean:
	-$(RM) $(BIN) $(BIN).exe $(LOG)

.PHONY: run log clean
