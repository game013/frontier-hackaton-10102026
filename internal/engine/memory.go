package engine

import (
	"sync"

	"github.com/game013/frontier-hackaton-10102026/internal/state"
)

// MemoryStore es transitorio: da al motor un Store mientras B5 añade SQLite,
// que lo reemplaza en producción. No persiste tras reiniciar (MEM-03).
// Update no revierte cambios parciales: es atómico porque apply valida todo
// antes de mutar y state solo devuelve error (ErrOverflow) antes de escribir.
type MemoryStore struct {
	mu sync.Mutex
	st *state.State
}

func NewMemoryStore() *MemoryStore { return &MemoryStore{st: state.New()} }

func (m *MemoryStore) Update(fn func(*state.State) error) error {
	m.mu.Lock()
	defer m.mu.Unlock()
	return fn(m.st)
}

func (m *MemoryStore) Reset() error {
	m.mu.Lock()
	defer m.mu.Unlock()
	m.st = state.New()
	return nil
}
