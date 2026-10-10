package state

import "testing"

func TestAccountCounterTransitions(t *testing.T) {
	acc := Account{ID: "AC-0001", Name: "A", Balance: -50}
	for range 3 {
		acc.RecordTransferFailure()
	}
	if acc.TransferFailures != 3 || acc.BlockedAttempts != 0 {
		t.Fatalf("fallos: %+v", acc)
	}
	if n := acc.RecordBlockedAttempt(); n != 1 {
		t.Fatalf("primer intento: %d", n)
	}
	if n := acc.RecordBlockedAttempt(); n != 2 {
		t.Fatalf("segundo intento: %d", n)
	}
	acc.ClearTransferFailures()
	if acc.TransferFailures != 0 || acc.BlockedAttempts != 2 {
		t.Fatalf("reiniciar racha alteró intentos: %+v", acc)
	}
	acc.RecordTransferFailure()
	acc.ClearBlock()
	if acc.TransferFailures != 0 || acc.BlockedAttempts != 0 {
		t.Fatalf("desbloqueo: %+v", acc)
	}
	if acc.ID != "AC-0001" || acc.Name != "A" || acc.Balance != -50 {
		t.Fatalf("transición alteró datos/saldo: %+v", acc)
	}
}
