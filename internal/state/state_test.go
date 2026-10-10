package state

import (
	"errors"
	"math"
	"testing"
)

func TestCountersAreSeparateAndStartAtOne(t *testing.T) {
	s := New()
	a, b := s.OpenAccount("Lucia"), s.OpenAccount("Mateo")
	if a != "AC-0001" || b != "AC-0002" {
		t.Fatalf("cuentas %s %s", a, b)
	}
	if op, _ := s.Apply(Delta{a, 250000}); op != "OP-0001" {
		t.Fatalf("operación %s", op)
	}
	if s.Accounts[a].Name != "Lucia" || s.Accounts[b].Balance != 0 {
		t.Fatalf("cuentas %+v %+v", s.Accounts[a], s.Accounts[b])
	}
}

func TestAnnulRevertsOnceWithoutBalanceCheck(t *testing.T) {
	s := New()
	a, b := s.OpenAccount("A"), s.OpenAccount("B")
	dep, _ := s.Apply(Delta{a, 1000})
	s.Apply(Delta{a, -800}, Delta{b, 800})
	if found, already, _ := s.Annul(dep); !found || already {
		t.Fatalf("primera anulación found=%v already=%v", found, already)
	}
	// MEM-04: el depósito ya gastado deja el origen en negativo.
	if s.Accounts[a].Balance != -800 || s.Accounts[b].Balance != 800 {
		t.Fatalf("saldos %d %d", s.Accounts[a].Balance, s.Accounts[b].Balance)
	}
	if found, already, _ := s.Annul(dep); !found || !already {
		t.Fatalf("segunda anulación found=%v already=%v", found, already)
	}
	if s.Accounts[a].Balance != -800 {
		t.Fatalf("la segunda anulación movió saldo: %d", s.Accounts[a].Balance)
	}
	if found, _, _ := s.Annul("op-0001"); found {
		t.Fatal("el ID debe coincidir exactamente")
	}
	if s.NextOperation != 3 {
		t.Fatalf("ANULA consumió OP: siguiente %d", s.NextOperation)
	}
}

func TestFormatIDGrowsPast9999(t *testing.T) {
	if got := FormatID("AC", 10000); got != "AC-10000" {
		t.Fatal(got)
	}
}

// El diseño exige comprobar el desbordamiento antes de escribir: si algún
// saldo resultante no cabe en int64, no cambia nada (ni saldos, ni operación,
// ni contador). Sin evidencia del original: el motor lo trata como fallo.
func TestApplyRejectsOverflowWithoutMutating(t *testing.T) {
	s := New()
	a, b := s.OpenAccount("A"), s.OpenAccount("B")
	s.Accounts[b].Balance = math.MaxInt64 - 5
	s.Accounts[a].Balance = 10
	if _, err := s.Apply(Delta{a, -10}, Delta{b, 10}); !errors.Is(err, ErrOverflow) {
		t.Fatalf("err = %v, want ErrOverflow", err)
	}
	if s.Accounts[a].Balance != 10 || s.Accounts[b].Balance != math.MaxInt64-5 {
		t.Fatalf("saldos mutados: %d %d", s.Accounts[a].Balance, s.Accounts[b].Balance)
	}
	if s.NextOperation != 1 || len(s.Operations) != 0 {
		t.Fatalf("operación registrada: next=%d ops=%d", s.NextOperation, len(s.Operations))
	}
	if op, err := s.Apply(Delta{b, 5}); err != nil || op != "OP-0001" || s.Accounts[b].Balance != math.MaxInt64 {
		t.Fatalf("borde exacto: %s %v %d", op, err, s.Accounts[b].Balance)
	}
}

func TestAnnulRejectsOverflowWithoutMutating(t *testing.T) {
	s := New()
	a := s.OpenAccount("A")
	op, err := s.Apply(Delta{a, 10})
	if err != nil {
		t.Fatal(err)
	}
	s.Accounts[a].Balance = math.MinInt64 + 5
	if _, _, err := s.Annul(op); !errors.Is(err, ErrOverflow) {
		t.Fatalf("err = %v, want ErrOverflow", err)
	}
	if s.Operations[op].Annulled || s.Accounts[a].Balance != math.MinInt64+5 {
		t.Fatalf("anulación aplicada a medias: %+v %d", s.Operations[op], s.Accounts[a].Balance)
	}
}
