// Package app compone el reemplazo sin transporte ni captura: es lo que main
// despliega y lo que el arnés diferencial reproduce. Cada llamada a New
// devuelve una instancia con estado propio.
package app

import (
	"net/http"

	"github.com/game013/frontier-hackaton-10102026/internal/config"
	"github.com/game013/frontier-hackaton-10102026/internal/httpadapter"
)

func New(cfg config.Config) http.Handler {
	return httpadapter.New(cfg.Token)
}
