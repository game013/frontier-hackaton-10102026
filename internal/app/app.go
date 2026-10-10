// Package app compone el motor, su almacenamiento y el adaptador HTTP.
package app

import (
	"fmt"
	"net/http"

	"github.com/game013/frontier-hackaton-10102026/internal/config"
	"github.com/game013/frontier-hackaton-10102026/internal/engine"
	"github.com/game013/frontier-hackaton-10102026/internal/httpadapter"
	"github.com/game013/frontier-hackaton-10102026/internal/storage/sqlite"
)

type closableStore interface {
	engine.Store
	Close() error
}

// App posee el almacenamiento. Close se llama después de detener el servidor.
type App struct {
	http.Handler
	close func() error
}

func (a *App) Close() error { return a.close() }

// New abre el almacenamiento antes de devolver un handler listo para servir.
func New(cfg config.Config) (*App, error) {
	var store closableStore
	switch cfg.Storage {
	case config.StorageSQLite:
		s, err := sqlite.Open(cfg.StatePath)
		if err != nil {
			return nil, err
		}
		store = s
	case config.StorageMemory:
		store = engine.NewMemoryStore()
	default:
		// New también recibe Config construidos directamente, sin config.Load.
		return nil, fmt.Errorf("STORAGE desconocido: %q", cfg.Storage)
	}
	eng := engine.New(store)
	return &App{
		Handler: httpadapter.New(cfg.Token,
			httpadapter.WithExec(eng.Exec),
			httpadapter.WithReset(eng.Reset),
		),
		close: store.Close,
	}, nil
}
