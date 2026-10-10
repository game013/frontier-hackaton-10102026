package sqlite

import (
	"errors"
	"math"
	"path/filepath"
	"reflect"
	"testing"

	"github.com/game013/frontier-hackaton-10102026/internal/state"
)

func openTest(t *testing.T, path string) *Store {
	t.Helper()
	s, err := Open(path)
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() {
		if err := s.Close(); err != nil {
			t.Error(err)
		}
	})
	return s
}

func snapshot(t *testing.T, s *Store) *state.State {
	t.Helper()
	var got *state.State
	if err := s.Update(func(st *state.State) error { got = st.Clone(); return nil }); err != nil {
		t.Fatal(err)
	}
	return got
}

func populated(t *testing.T, s *Store) *state.State {
	t.Helper()
	if err := s.Update(func(st *state.State) error {
		a := st.OpenAccount("  Lucía ?#;\x00  ")
		b := st.OpenAccount("Mateo")
		if _, err := st.Apply(state.Delta{Account: a, Amount: math.MaxInt64}); err != nil {
			return err
		}
		if _, err := st.Apply(state.Delta{Account: a, Amount: -100}, state.Delta{Account: b, Amount: 100}); err != nil {
			return err
		}
		_, _, err := st.Annul("OP-0001") // conserva saldo negativo y marca de anulación
		return err
	}); err != nil {
		t.Fatal(err)
	}
	return snapshot(t, s)
}

func TestReopenPreservesCompleteState(t *testing.T) {
	path := filepath.Join(t.TempDir(), "state ?# con espacios.db")
	s := openTest(t, path)
	want := populated(t, s)
	if err := s.Close(); err != nil {
		t.Fatal(err)
	}
	s = openTest(t, path)
	if got := snapshot(t, s); !reflect.DeepEqual(got, want) {
		t.Fatalf("reapertura: got %+v want %+v", got, want)
	}
	if err := s.Update(func(st *state.State) error {
		found, already, err := st.Annul("OP-0001")
		if !found || !already || err != nil {
			t.Fatalf("anulación persistida: %v %v %v", found, already, err)
		}
		if id := st.OpenAccount("Nueva"); id != "AC-0003" {
			t.Fatalf("id %s", id)
		}
		id, err := st.Apply(state.Delta{Account: "AC-0003", Amount: 1})
		if id != "OP-0003" {
			t.Fatalf("id %s", id)
		}
		return err
	}); err != nil {
		t.Fatal(err)
	}
}

func TestCallbackAndWriteFailureRollBack(t *testing.T) {
	s := openTest(t, filepath.Join(t.TempDir(), "state.db"))
	want := populated(t, s)
	sentinel := errors.New("fallo después de mutar")
	err := s.Update(func(st *state.State) error {
		st.OpenAccount("Descartada")
		st.Accounts["AC-0001"].Balance = 77
		st.Operations["OP-0002"].Deltas[0].Amount = 33
		return sentinel
	})
	if !errors.Is(err, sentinel) {
		t.Fatalf("callback: %v", err)
	}
	if !reflect.DeepEqual(snapshot(t, s), want) {
		t.Fatal("callback fallido cambió estado")
	}
	// El trigger falla durante la escritura, después de posibles cambios SQL.
	if _, err := s.db.Exec(`CREATE TRIGGER fail_account BEFORE INSERT ON accounts BEGIN SELECT RAISE(ABORT, 'fallo inyectado'); END`); err != nil {
		t.Fatal(err)
	}
	err = s.Update(func(st *state.State) error {
		st.OpenAccount("Descartada")
		_, _, err := st.Annul("OP-0002")
		return err
	})
	if err == nil {
		t.Fatal("se esperaba fallo de escritura")
	}
	if !reflect.DeepEqual(snapshot(t, s), want) {
		t.Fatal("fallo SQL dejó escritura parcial")
	}
}

func TestResetAtomicAndDurable(t *testing.T) {
	path := filepath.Join(t.TempDir(), "state.db")
	s := openTest(t, path)
	want := populated(t, s)
	// Fuerza el fallo después de borrar deltas y operaciones.
	if _, err := s.db.Exec(`CREATE TRIGGER fail_reset BEFORE DELETE ON accounts BEGIN SELECT RAISE(ABORT, 'fallo reset'); END`); err != nil {
		t.Fatal(err)
	}
	if err := s.Reset(); err == nil {
		t.Fatal("reset debía fallar")
	}
	if !reflect.DeepEqual(snapshot(t, s), want) {
		t.Fatal("reset fallido dejó estado parcial")
	}
	if _, err := s.db.Exec("DROP TRIGGER fail_reset"); err != nil {
		t.Fatal(err)
	}
	if err := s.Reset(); err != nil {
		t.Fatal(err)
	}
	if err := s.Close(); err != nil {
		t.Fatal(err)
	}
	s = openTest(t, path)
	if !reflect.DeepEqual(snapshot(t, s), state.New()) {
		t.Fatal("reset no persistió estado inicial")
	}
}

func TestSnapshotDoesNotEscape(t *testing.T) {
	s := openTest(t, filepath.Join(t.TempDir(), "state.db"))
	var escaped *state.State
	if err := s.Update(func(st *state.State) error { st.OpenAccount("A"); escaped = st; return nil }); err != nil {
		t.Fatal(err)
	}
	escaped.Accounts["AC-0001"].Balance = 100
	escaped.NextAccount = 99
	got := snapshot(t, s)
	if got.Accounts["AC-0001"].Balance != 0 || got.NextAccount != 2 {
		t.Fatal("alias modificó estado persistido")
	}
}

func TestOpenRefusesInvalidState(t *testing.T) {
	if _, err := Open(""); err == nil {
		t.Fatal("ruta vacía aceptada")
	}
	if _, err := Open(t.TempDir()); err == nil {
		t.Fatal("directorio aceptado como base")
	}
	for _, stmt := range []string{"PRAGMA user_version=99", "DROP TABLE operations", "DELETE FROM counters"} {
		t.Run(stmt, func(t *testing.T) {
			path := filepath.Join(t.TempDir(), "state.db")
			s := openTest(t, path)
			if _, err := s.db.Exec(stmt); err != nil {
				t.Fatal(err)
			}
			s.Close()
			if reopened, err := Open(path); err == nil {
				reopened.Close()
				t.Fatal("base inválida aceptada")
			}
		})
	}
}

// Semilla sintética: no hace falta generar 10.000 entidades para verificar
// que SQLite conserva IDs sin truncar y ambos contadores al cruzar 9999.
func TestReopenPreservesIDsBeyondFourDigits(t *testing.T) {
	path := filepath.Join(t.TempDir(), "state.db")
	s := openTest(t, path)
	if err := s.Update(func(st *state.State) error {
		st.NextAccount, st.NextOperation = 9999, 9999
		if id := st.OpenAccount("A"); id != "AC-9999" {
			t.Fatalf("cuenta: %s", id)
		}
		id, err := st.Apply(state.Delta{Account: "AC-9999", Amount: 1})
		if id != "OP-9999" {
			t.Fatalf("operación: %s", id)
		}
		return err
	}); err != nil {
		t.Fatal(err)
	}
	if err := s.Close(); err != nil {
		t.Fatal(err)
	}
	s = openTest(t, path)
	if err := s.Update(func(st *state.State) error {
		if id := st.OpenAccount("B"); id != "AC-10000" {
			t.Fatalf("cuenta: %s", id)
		}
		id, err := st.Apply(state.Delta{Account: "AC-10000", Amount: 2})
		if id != "OP-10000" {
			t.Fatalf("operación: %s", id)
		}
		return err
	}); err != nil {
		t.Fatal(err)
	}
	if err := s.Close(); err != nil {
		t.Fatal(err)
	}
	s = openTest(t, path)
	st := snapshot(t, s)
	if st.NextAccount != 10001 || st.NextOperation != 10001 {
		t.Fatalf("contadores: %d/%d", st.NextAccount, st.NextOperation)
	}
	acc := st.Accounts["AC-10000"]
	if acc == nil || acc.ID != "AC-10000" || acc.Name != "B" || acc.Balance != 2 {
		t.Fatalf("cuenta releída: %+v", acc)
	}
	op := st.Operations["OP-10000"]
	if op == nil || op.ID != "OP-10000" || !reflect.DeepEqual(op.Deltas, []state.Delta{{Account: "AC-10000", Amount: 2}}) {
		t.Fatalf("operación releída: %+v", op)
	}
}
