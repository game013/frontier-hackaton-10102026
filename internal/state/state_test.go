package state

import "testing"

func TestCountersAreSeparateAndStartAtOne(t *testing.T) {
	s := New()
	a, b := s.OpenAccount("Lucia"), s.OpenAccount("Mateo")
	if a != "AC-0001" || b != "AC-0002" {
		t.Fatalf("cuentas %s %s", a, b)
	}
	if op := s.Apply(Delta{a, 250000}); op != "OP-0001" {
		t.Fatalf("operación %s", op)
	}
	if s.Accounts[a].Name != "Lucia" || s.Accounts[b].Balance != 0 {
		t.Fatalf("cuentas %+v %+v", s.Accounts[a], s.Accounts[b])
	}
}

func TestAnnulRevertsOnceWithoutBalanceCheck(t *testing.T) {
	s := New()
	a, b := s.OpenAccount("A"), s.OpenAccount("B")
	dep := s.Apply(Delta{a, 1000})
	s.Apply(Delta{a, -800}, Delta{b, 800})
	if found, already := s.Annul(dep); !found || already {
		t.Fatalf("primera anulación found=%v already=%v", found, already)
	}
	// MEM-04: el depósito ya gastado deja el origen en negativo.
	if s.Accounts[a].Balance != -800 || s.Accounts[b].Balance != 800 {
		t.Fatalf("saldos %d %d", s.Accounts[a].Balance, s.Accounts[b].Balance)
	}
	if found, already := s.Annul(dep); !found || !already {
		t.Fatalf("segunda anulación found=%v already=%v", found, already)
	}
	if s.Accounts[a].Balance != -800 {
		t.Fatalf("la segunda anulación movió saldo: %d", s.Accounts[a].Balance)
	}
	if found, _ := s.Annul("op-0001"); found {
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
