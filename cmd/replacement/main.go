// Command replacement es el único binario desplegado del reemplazo.
package main

import (
	"io"
	"log"
	"net/http"
	"os"
	"path/filepath"
	"time"

	"github.com/game013/frontier-hackaton-10102026/internal/app"
	"github.com/game013/frontier-hackaton-10102026/internal/capture"
	"github.com/game013/frontier-hackaton-10102026/internal/config"
)

func main() {
	log.SetOutput(os.Stderr)
	cfg, err := config.Load(os.Getenv)
	if err != nil {
		log.Fatal(err)
	}
	// La captura es obligatoria: sin archivo donde escribir, no se arranca.
	if err := os.MkdirAll(filepath.Dir(cfg.CapturePath), 0o700); err != nil {
		log.Fatal(err)
	}
	file, err := capture.FileSink(cfg.CapturePath)
	if err != nil {
		log.Fatal(err)
	}
	defer file.Close()

	handler := capture.Middleware(app.New(cfg), capture.Options{
		Token: cfg.Token, Version: cfg.Version, Sinks: []io.Writer{file, os.Stdout},
	})
	srv := &http.Server{
		Addr:              ":" + cfg.Port,
		Handler:           handler,
		ReadHeaderTimeout: 5 * time.Second,
		ReadTimeout:       10 * time.Second,
		WriteTimeout:      10 * time.Second,
	}
	log.Printf("replacement escuchando en :%s version=%s capture=%s", cfg.Port, cfg.Version, cfg.CapturePath)
	log.Fatal(srv.ListenAndServe())
}
