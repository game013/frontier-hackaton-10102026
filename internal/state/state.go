// Package state es el modelo de negocio del reemplazo: cuentas, operaciones y
// contadores de un token. No valida nada: las reglas y su orden viven en el
// motor, que solo llama a estas transiciones cuando ya decidió aplicarlas.
package state

import (
	"errors"
	"fmt"
	"math"
)

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
	NextAccount   int64
	NextOperation int64
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

// ErrOverflow: algún saldo resultante no cabe en int64. El diseño exige
// comprobarlo antes de escribir y no saturar; el original nunca lo mostró.
var ErrOverflow = errors.New("state: saldo fuera de int64")

// Apply registra una operación con sus deltas, los suma a los saldos y
// consume un número OP. Las cuentas deben existir. Si un saldo desbordaría,
// devuelve ErrOverflow sin cambiar nada.
func (s *State) Apply(deltas ...Delta) (string, error) {
	if err := s.check(deltas, 1); err != nil {
		return "", err
	}
	id := FormatID("OP", s.NextOperation)
	s.NextOperation++
	s.Operations[id] = &Operation{ID: id, Deltas: deltas}
	for _, d := range deltas {
		s.Accounts[d.Account].Balance += d.Amount
	}
	return id, nil
}

// Annul revierte los deltas de la operación una sola vez, sin comprobar saldos
// (CMD-ANULA, MEM-04). found es false si el ID no coincide exactamente con una
// operación emitida; already es true si ya estaba anulada (y no se toca nada).
// Si un saldo desbordaría, devuelve ErrOverflow sin cambiar nada.
func (s *State) Annul(id string) (found, already bool, err error) {
	op, ok := s.Operations[id]
	if !ok {
		return false, false, nil
	}
	if op.Annulled {
		return true, true, nil
	}
	if err := s.check(op.Deltas, -1); err != nil {
		return true, false, err
	}
	op.Annulled = true
	for _, d := range op.Deltas {
		s.Accounts[d.Account].Balance -= d.Amount
	}
	return true, false, nil
}

// check simula sign·deltas sobre los saldos (acumulando si una cuenta se
// repite) y falla si alguno sale de int64.
func (s *State) check(deltas []Delta, sign int64) error {
	next := map[string]int64{}
	for _, d := range deltas {
		cur, ok := next[d.Account]
		if !ok {
			cur = s.Accounts[d.Account].Balance
		}
		amount := sign * d.Amount
		if (amount > 0 && cur > math.MaxInt64-amount) || (amount < 0 && cur < math.MinInt64-amount) {
			return ErrOverflow
		}
		next[d.Account] = cur + amount
	}
	return nil
}

// FormatID da `AC-0001`/`OP-0001`. Pasado 9999 crece sin truncar: supuesto,
// el original no se observó más allá de AC-0013.
func FormatID(prefix string, n int64) string {
	return fmt.Sprintf("%s-%04d", prefix, n)
}

// Clone devuelve un estado sin punteros ni slices compartidos: cada callback
// trabaja sobre una copia que puede descartarse si falla.
func (s *State) Clone() *State {
	out := New()
	out.NextAccount, out.NextOperation = s.NextAccount, s.NextOperation
	for id, acc := range s.Accounts {
		copy := *acc
		out.Accounts[id] = &copy
	}
	for id, op := range s.Operations {
		copy := *op
		copy.Deltas = append([]Delta(nil), op.Deltas...)
		out.Operations[id] = &copy
	}
	return out
}
