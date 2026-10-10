// Package sqlite implementa el Store del motor con un archivo SQLite local.
// Un proceso, una conexión y transacciones serializadas para Update y Reset.
package sqlite

import (
	"database/sql"
	"errors"
	"fmt"
	"net/url"
	"os"
	"path/filepath"
	"reflect"
	"sync"

	"github.com/game013/frontier-hackaton-10102026/internal/state"
	_ "modernc.org/sqlite"
)

const schemaVersion = 2
const schemaV1 = `
CREATE TABLE accounts (id TEXT PRIMARY KEY, name TEXT NOT NULL, balance INTEGER NOT NULL);
CREATE TABLE operations (id TEXT PRIMARY KEY, annulled INTEGER NOT NULL);
CREATE TABLE operation_deltas (
 operation_id TEXT NOT NULL REFERENCES operations(id),
 position INTEGER NOT NULL,
 account_id TEXT NOT NULL REFERENCES accounts(id),
 amount INTEGER NOT NULL,
 PRIMARY KEY (operation_id, position)
);
CREATE TABLE counters (id INTEGER PRIMARY KEY CHECK (id = 1), next_account INTEGER NOT NULL, next_operation INTEGER NOT NULL);
INSERT INTO counters VALUES (1, 1, 1);
`

// Los contadores empiezan en cero al migrar una base B5. Ambas versiones de
// comportamiento usan el esquema actual; cambiar a v1 no elimina este estado.
const migrateSchema2 = `
ALTER TABLE accounts ADD COLUMN transfer_failures INTEGER NOT NULL DEFAULT 0;
ALTER TABLE accounts ADD COLUMN blocked_attempts INTEGER NOT NULL DEFAULT 0;
`

type Store struct {
	mu sync.Mutex
	db *sql.DB
}

// Open prepara el esquema antes de permitir requests. path es una ruta de
// archivo, no un DSN: sus signos ?, # y espacios se conservan literalmente.
func Open(path string) (*Store, error) {
	if path == "" {
		return nil, errors.New("sqlite: STATE_PATH vacío")
	}
	abs, err := filepath.Abs(path)
	if err != nil {
		return nil, err
	}
	if err := os.MkdirAll(filepath.Dir(abs), 0o700); err != nil {
		return nil, err
	}
	// Crear privadamente; un archivo existente nunca se trunca.
	f, err := os.OpenFile(abs, os.O_CREATE|os.O_RDWR, 0o600)
	if err != nil {
		return nil, err
	}
	if err := f.Close(); err != nil {
		return nil, err
	}
	uri := url.URL{Scheme: "file", Path: abs}
	q := url.Values{}
	q.Add("_pragma", "busy_timeout(1000)")
	q.Add("_pragma", "foreign_keys(ON)")
	q.Add("_pragma", "journal_mode(WAL)")
	q.Add("_pragma", "synchronous(FULL)")
	q.Set("_txlock", "immediate")
	uri.RawQuery = q.Encode()
	db, err := sql.Open("sqlite", uri.String())
	if err != nil {
		return nil, err
	}
	db.SetMaxOpenConns(1)
	db.SetMaxIdleConns(1)
	s := &Store{db: db}
	if err := s.initialize(); err != nil {
		db.Close()
		return nil, fmt.Errorf("sqlite: abrir estado: %w", err)
	}
	return s, nil
}

func (s *Store) initialize() error {
	tx, err := s.db.Begin()
	if err != nil {
		return err
	}
	defer tx.Rollback()
	var version int
	if err := tx.QueryRow("PRAGMA user_version").Scan(&version); err != nil {
		return err
	}
	switch version {
	case 0:
		if _, err := tx.Exec(schemaV1); err != nil {
			return err
		}
		fallthrough
	case 1:
		if _, err := tx.Exec(migrateSchema2); err != nil {
			return err
		}
		if _, err := tx.Exec(fmt.Sprintf("PRAGMA user_version = %d", schemaVersion)); err != nil {
			return err
		}
	case schemaVersion:
	default:
		return fmt.Errorf("versión de esquema desconocida: %d", version)
	}
	// Comprueba que una base existente tenga las tablas y contadores requeridos.
	if _, err := load(tx); err != nil {
		return err
	}
	return tx.Commit()
}

func (s *Store) Close() error {
	s.mu.Lock()
	defer s.mu.Unlock()
	return s.db.Close()
}

// Update ejecuta el callback una sola vez sobre una copia aislada. La respuesta
// del motor solo se publica después de confirmar todos sus cambios en SQLite.
func (s *Store) Update(fn func(*state.State) error) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	tx, err := s.db.Begin()
	if err != nil {
		return err
	}
	defer tx.Rollback()
	before, err := load(tx)
	if err != nil {
		return err
	}
	after := before.Clone()
	if err := fn(after); err != nil {
		return err
	}
	if err := save(tx, before, after); err != nil {
		return err
	}
	return tx.Commit()
}

func (s *Store) Reset() error {
	s.mu.Lock()
	defer s.mu.Unlock()
	tx, err := s.db.Begin()
	if err != nil {
		return err
	}
	defer tx.Rollback()
	for _, stmt := range []string{
		"DELETE FROM operation_deltas", "DELETE FROM operations", "DELETE FROM accounts",
		"UPDATE counters SET next_account = 1, next_operation = 1 WHERE id = 1",
	} {
		if _, err := tx.Exec(stmt); err != nil {
			return err
		}
	}
	return tx.Commit()
}

func load(tx *sql.Tx) (*state.State, error) {
	st := state.New()
	if err := tx.QueryRow("SELECT next_account, next_operation FROM counters WHERE id = 1").Scan(&st.NextAccount, &st.NextOperation); err != nil {
		return nil, err
	}
	rows, err := tx.Query("SELECT id, name, balance, transfer_failures, blocked_attempts FROM accounts")
	if err != nil {
		return nil, err
	}
	for rows.Next() {
		var a state.Account
		if err := rows.Scan(&a.ID, &a.Name, &a.Balance, &a.TransferFailures, &a.BlockedAttempts); err != nil {
			rows.Close()
			return nil, err
		}
		st.Accounts[a.ID] = &a
	}
	err = rows.Err()
	rows.Close()
	if err != nil {
		return nil, err
	}
	rows, err = tx.Query("SELECT id, annulled FROM operations")
	if err != nil {
		return nil, err
	}
	for rows.Next() {
		var op state.Operation
		if err := rows.Scan(&op.ID, &op.Annulled); err != nil {
			rows.Close()
			return nil, err
		}
		st.Operations[op.ID] = &op
	}
	err = rows.Err()
	rows.Close()
	if err != nil {
		return nil, err
	}
	rows, err = tx.Query("SELECT operation_id, account_id, amount FROM operation_deltas ORDER BY operation_id, position")
	if err != nil {
		return nil, err
	}
	for rows.Next() {
		var id string
		var delta state.Delta
		if err := rows.Scan(&id, &delta.Account, &delta.Amount); err != nil {
			rows.Close()
			return nil, err
		}
		op := st.Operations[id]
		if op == nil || st.Accounts[delta.Account] == nil {
			rows.Close()
			return nil, errors.New("sqlite: delta sin operación o cuenta")
		}
		op.Deltas = append(op.Deltas, delta)
	}
	err = rows.Err()
	rows.Close()
	if err != nil {
		return nil, err
	}
	return st, nil
}

// save escribe solo las entidades que cambian: consultar no reescribe el
// historial completo. Los deltas se guardan en su orden original.
func save(tx *sql.Tx, before, after *state.State) error {
	for id, old := range before.Operations {
		if !reflect.DeepEqual(old, after.Operations[id]) {
			if _, err := tx.Exec("DELETE FROM operation_deltas WHERE operation_id = ?", id); err != nil {
				return err
			}
			if after.Operations[id] == nil {
				if _, err := tx.Exec("DELETE FROM operations WHERE id = ?", id); err != nil {
					return err
				}
			}
		}
	}
	for id := range before.Accounts {
		if after.Accounts[id] == nil {
			if _, err := tx.Exec("DELETE FROM accounts WHERE id = ?", id); err != nil {
				return err
			}
		}
	}
	for id, acc := range after.Accounts {
		old := before.Accounts[id]
		if old != nil && *old == *acc {
			continue
		}
		if _, err := tx.Exec(`INSERT INTO accounts (id, name, balance, transfer_failures, blocked_attempts) VALUES (?, ?, ?, ?, ?)
ON CONFLICT(id) DO UPDATE SET name=excluded.name, balance=excluded.balance,
transfer_failures=excluded.transfer_failures, blocked_attempts=excluded.blocked_attempts`,
			id, acc.Name, acc.Balance, acc.TransferFailures, acc.BlockedAttempts); err != nil {
			return err
		}
	}
	for id, op := range after.Operations {
		if reflect.DeepEqual(before.Operations[id], op) {
			continue
		}
		if _, err := tx.Exec("INSERT INTO operations VALUES (?, ?) ON CONFLICT(id) DO UPDATE SET annulled=excluded.annulled", id, op.Annulled); err != nil {
			return err
		}
		for i, delta := range op.Deltas {
			if _, err := tx.Exec("INSERT INTO operation_deltas VALUES (?, ?, ?, ?)", id, i, delta.Account, delta.Amount); err != nil {
				return err
			}
		}
	}
	if before.NextAccount != after.NextAccount || before.NextOperation != after.NextOperation {
		if _, err := tx.Exec("UPDATE counters SET next_account = ?, next_operation = ? WHERE id = 1", after.NextAccount, after.NextOperation); err != nil {
			return err
		}
	}
	return nil
}
