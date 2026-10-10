package engine

import (
	"errors"
	"testing"

	"github.com/game013/frontier-hackaton-10102026/internal/state"
)

func TestMemoryUpdateRollsBackAndIsolatesPointers(t *testing.T) {
	s := NewMemoryStore()
	var escaped *state.State
	if err := s.Update(func(st *state.State) error { st.OpenAccount("A"); escaped = st; return nil }); err != nil {
		t.Fatal(err)
	}
	escaped.Accounts["AC-0001"].Balance = 99
	sentinel := errors.New("rollback")
	if err := s.Update(func(st *state.State) error {
		st.OpenAccount("B")
		st.Accounts["AC-0001"].Balance = 10
		return sentinel
	}); !errors.Is(err, sentinel) {
		t.Fatal(err)
	}
	if err := s.Update(func(st *state.State) error {
		if st.NextAccount != 2 || len(st.Accounts) != 1 || st.Accounts["AC-0001"].Balance != 0 {
			t.Fatalf("estado parcial: %+v", st)
		}
		return nil
	}); err != nil {
		t.Fatal(err)
	}
}
