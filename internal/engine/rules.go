package engine

import (
	"fmt"
	"strconv"

	"github.com/game013/frontier-hackaton-10102026/internal/state"
)

const (
	// ERR-506 (v1) y CAM-V2-2: límite por operación, no por cuenta/día.
	transferLimitV1 int64 = 100000
	transferLimitV2 int64 = 50000
	// CAM-V2-3: el tercer fallo aún responde E506/E507; se bloquea el siguiente.
	blockingFailures int64 = 3
)

// rules se selecciona una sola vez. v2 reutiliza v1 y sobrescribe únicamente
// sus deltas; apply no conoce nombres de versiones ni elige políticas.
type rules struct {
	transferLimit   int64
	saldoJSON       func(int64) string
	blockedAttempt  func(*state.Account) (int64, bool)
	transferFailure func(*state.Account)
	transferSuccess func(*state.Account)
	depositSuccess  func(*state.Account)
}

func rulesFor(version string) (rules, error) {
	r := rules{
		transferLimit:   transferLimitV1,
		saldoJSON:       func(balance int64) string { return strconv.FormatInt(balance, 10) },
		blockedAttempt:  func(*state.Account) (int64, bool) { return 0, false },
		transferFailure: keepCounters,
		transferSuccess: keepCounters,
		depositSuccess:  keepCounters,
	}
	switch version {
	case "v1":
	case "v2":
		r.transferLimit = transferLimitV2
		r.saldoJSON = func(balance int64) string { return `"` + formatBalance(balance) + `"` }
		r.blockedAttempt = recordBlockedTransfer
		r.transferFailure = (*state.Account).RecordTransferFailure
		r.transferSuccess = (*state.Account).ClearTransferFailures
		r.depositSuccess = (*state.Account).ClearBlock
	default:
		return rules{}, fmt.Errorf("engine: versión desconocida: %q", version)
	}
	return r, nil
}

// La política v1 no interpreta ni modifica contadores propios de v2.
func keepCounters(*state.Account) {}

func recordBlockedTransfer(acc *state.Account) (int64, bool) {
	if acc.TransferFailures < blockingFailures {
		return 0, false
	}
	return acc.RecordBlockedAttempt(), true
}
