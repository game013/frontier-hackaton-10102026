package sqlite

import (
	"database/sql"
	"errors"
	"path/filepath"
	"reflect"
	"testing"

	"github.com/game013/frontier-hackaton-10102026/internal/state"
)

// Base sintética con el esquema real de B5, no evidencia del original.
func legacyDB(t *testing.T, path string) *sql.DB {
	t.Helper()
	db, err := sql.Open("sqlite", path)
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { db.Close() })
	if _, err := db.Exec(schemaV1 + `
 PRAGMA user_version = 1;
 INSERT INTO accounts VALUES ('AC-0001', 'Lucía', -50), ('AC-0002', 'B', 100);
 INSERT INTO operations VALUES ('OP-0001', 1);
 INSERT INTO operation_deltas VALUES ('OP-0001', 0, 'AC-0001', 100);
 UPDATE counters SET next_account=3, next_operation=2 WHERE id=1;
 `); err != nil {
		t.Fatal(err)
	}
	return db
}

func TestMigrateB5PreservesState(t *testing.T) {
	path := filepath.Join(t.TempDir(), "legacy.db")
	db := legacyDB(t, path)
	db.Close()
	s := openTest(t, path)
	want := state.New()
	want.Accounts["AC-0001"] = &state.Account{ID: "AC-0001", Name: "Lucía", Balance: -50}
	want.Accounts["AC-0002"] = &state.Account{ID: "AC-0002", Name: "B", Balance: 100}
	want.Operations["OP-0001"] = &state.Operation{ID: "OP-0001", Annulled: true, Deltas: []state.Delta{{Account: "AC-0001", Amount: 100}}}
	want.NextAccount, want.NextOperation = 3, 2
	if !reflect.DeepEqual(snapshot(t, s), want) {
		t.Fatal("migración perdió estado B5 o no inicializó contadores")
	}
	var version int
	if err := s.db.QueryRow("PRAGMA user_version").Scan(&version); err != nil || version != schemaVersion {
		t.Fatalf("versión %d: %v", version, err)
	}
	if err := s.Close(); err != nil {
		t.Fatal(err)
	}
	s = openTest(t, path)
	if !reflect.DeepEqual(snapshot(t, s), want) {
		t.Fatal("migración no es durable/idempotente")
	}
}

func TestMigrationFailureRollsBackSchema(t *testing.T) {
	path := filepath.Join(t.TempDir(), "legacy.db")
	db := legacyDB(t, path)
	// La validación final falla después de ejecutar ambos ALTER y el PRAGMA.
	if _, err := db.Exec("DROP TABLE operations"); err != nil {
		t.Fatal(err)
	}
	db.Close()
	if s, err := Open(path); err == nil {
		s.Close()
		t.Fatal("base incompleta aceptada")
	}
	db, err := sql.Open("sqlite", path)
	if err != nil {
		t.Fatal(err)
	}
	defer db.Close()
	var version int
	if err := db.QueryRow("PRAGMA user_version").Scan(&version); err != nil || version != 1 {
		t.Fatalf("migración parcial: versión %d: %v", version, err)
	}
	if _, err := db.Exec("SELECT transfer_failures FROM accounts"); err == nil {
		t.Fatal("ALTER persistió pese al rollback")
	}
	var balance int64
	if err := db.QueryRow("SELECT balance FROM accounts WHERE id='AC-0001'").Scan(&balance); err != nil || balance != -50 {
		t.Fatalf("saldo %d: %v", balance, err)
	}
}

func TestBlockingCountersDurableAndAtomic(t *testing.T) {
	path := filepath.Join(t.TempDir(), "state.db")
	s := openTest(t, path)
	populated(t, s)
	if err := s.Update(func(st *state.State) error {
		st.Accounts["AC-0001"].TransferFailures = 3
		st.Accounts["AC-0001"].BlockedAttempts = 7
		return nil
	}); err != nil {
		t.Fatal(err)
	}
	want := snapshot(t, s)
	if err := s.Close(); err != nil {
		t.Fatal(err)
	}
	s = openTest(t, path)
	if !reflect.DeepEqual(snapshot(t, s), want) {
		t.Fatal("contadores no persistieron")
	}
	sentinel := errors.New("callback fallido")
	if err := s.Update(func(st *state.State) error {
		st.Accounts["AC-0001"].TransferFailures = 0
		st.Accounts["AC-0001"].BlockedAttempts = 0
		return sentinel
	}); !errors.Is(err, sentinel) {
		t.Fatalf("callback: %v", err)
	}
	if !reflect.DeepEqual(snapshot(t, s), want) {
		t.Fatal("callback fallido modificó contadores")
	}
	if _, err := s.db.Exec(`CREATE TRIGGER fail_counter BEFORE UPDATE ON counters BEGIN SELECT RAISE(ABORT, 'fallo contador'); END`); err != nil {
		t.Fatal(err)
	}
	if err := s.Update(func(st *state.State) error {
		st.Accounts["AC-0001"].BlockedAttempts++
		st.NextOperation++
		return nil
	}); err == nil {
		t.Fatal("fallo SQL esperado")
	}
	if !reflect.DeepEqual(snapshot(t, s), want) {
		t.Fatal("escritura SQL fallida modificó contadores")
	}
	if _, err := s.db.Exec("DROP TRIGGER fail_counter"); err != nil {
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
		t.Fatal("reset no borró bloqueo y contadores")
	}
}
