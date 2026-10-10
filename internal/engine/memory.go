package engine

import (
	"sync"

	"github.com/game013/frontier-hackaton-10102026/internal/state"
)

// MemoryStore es la opción STORAGE=memory: estado volátil para uso local.
// Update descarta todos los cambios si el callback devuelve error.
type MemoryStore struct {
	mu sync.Mutex
	st *state.State
}

func NewMemoryStore() *MemoryStore { return &MemoryStore{st: state.New()} }

func (m *MemoryStore) Update(fn func(*state.State) error) error {
	m.mu.Lock()
	defer m.mu.Unlock()
	next := m.st.Clone()
	if err := fn(next); err != nil {
		return err
	}
	m.st = next.Clone()
	return nil
}

func (m *MemoryStore) Reset() error {
	m.mu.Lock()
	defer m.mu.Unlock()
	m.st = state.New()
	return nil
}

// Close permite usar el mismo ciclo de vida que SQLite.
func (m *MemoryStore) Close() error { return nil }
