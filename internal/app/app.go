// Package app compone el reemplazo sin transporte ni captura: es lo que main
// despliega y lo que el arnés diferencial reproduce. Cada llamada a New
// devuelve una instancia con estado propio.
package app

import (
	"log"
	"net/http"

	"github.com/game013/frontier-hackaton-10102026/internal/config"
	"github.com/game013/frontier-hackaton-10102026/internal/engine"
	"github.com/game013/frontier-hackaton-10102026/internal/httpadapter"
)

// New usa el store en memoria transitorio hasta que B5 conecte SQLite.
func New(cfg config.Config) http.Handler {
	eng := engine.New(engine.NewMemoryStore())
	return httpadapter.New(cfg.Token,
		httpadapter.WithExec(eng.Exec),
		httpadapter.WithReset(func() {
			if err := eng.Reset(); err != nil {
				log.Printf("reset: %v", err)
			}
		}),
	)
}
