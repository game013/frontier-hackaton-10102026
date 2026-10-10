// Package state es el modelo de negocio del reemplazo: cuentas, operaciones y
// contadores de un token. No valida nada: las reglas y su orden viven en el
// motor, que solo llama a estas transiciones cuando ya decidió aplicarlas.
package state

import "fmt"

type Account struct {
	ID      string
	Name    string // tal como llegó en ALTA (CMD-NOMBRE)
	Balance int64
}

// Delta es el efecto de una operación sobre una cuenta. Guardarlo permite
// anular sin recalcular las reglas que la aceptaron.
type Delta struct {
	Account string
	Amount  int64
}

type Operation struct {
	ID       string
	Deltas   []Delta
	Annulled bool
}

// State: AC y OP son contadores separados que empiezan en 1 (MEM-01).
type State struct {
	Accounts      map[string]*Account
	Operations    map[string]*Operation
	NextAccount   int
	NextOperation int
}

func New() *State {
	return &State{
		Accounts:      map[string]*Account{},
		Operations:    map[string]*Operation{},
		NextAccount:   1,
		NextOperation: 1,
	}
}

// OpenAccount crea una cuenta con saldo 0 y consume un número AC.
func (s *State) OpenAccount(name string) string {
	id := FormatID("AC", s.NextAccount)
	s.NextAccount++
	s.Accounts[id] = &Account{ID: id, Name: name}
	return id
}

// Apply registra una operación con sus deltas, los suma a los saldos y
// consume un número OP. Las cuentas deben existir.
func (s *State) Apply(deltas ...Delta) string {
	id := FormatID("OP", s.NextOperation)
	s.NextOperation++
	s.Operations[id] = &Operation{ID: id, Deltas: deltas}
	for _, d := range deltas {
		s.Accounts[d.Account].Balance += d.Amount
	}
	return id
}

// Annul revierte los deltas de la operación una sola vez, sin comprobar saldos
// (CMD-ANULA, MEM-04). found es false si el ID no coincide exactamente con una
// operación emitida; already es true si ya estaba anulada (y no se toca nada).
func (s *State) Annul(id string) (found, already bool) {
	op, ok := s.Operations[id]
	if !ok {
		return false, false
	}
	if op.Annulled {
		return true, true
	}
	op.Annulled = true
	for _, d := range op.Deltas {
		s.Accounts[d.Account].Balance -= d.Amount
	}
	return true, false
}

// FormatID da `AC-0001`/`OP-0001`. Pasado 9999 crece sin truncar: supuesto,
// el original no se observó más allá de AC-0013.
func FormatID(prefix string, n int) string {
	return fmt.Sprintf("%s-%04d", prefix, n)
}
