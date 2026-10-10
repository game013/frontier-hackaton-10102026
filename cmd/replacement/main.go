// Command replacement es el único binario desplegado del reemplazo.
package main

import (
	"context"
	"errors"
	"io"
	"log"
	"net"
	"net/http"
	"os"
	"os/signal"
	"path/filepath"
	"syscall"
	"time"

	"github.com/game013/frontier-hackaton-10102026/internal/app"
	"github.com/game013/frontier-hackaton-10102026/internal/capture"
	"github.com/game013/frontier-hackaton-10102026/internal/config"
)

func main() {
	log.SetOutput(os.Stderr)
	if err := run(); err != nil {
		log.Fatal(err)
	}
}

func run() (runErr error) {
	cfg, err := config.Load(os.Getenv)
	if err != nil {
		return err
	}
	// La captura es obligatoria: sin archivo donde escribir, no se arranca.
	if err := os.MkdirAll(filepath.Dir(cfg.CapturePath), 0o700); err != nil {
		return err
	}
	file, err := capture.FileSink(cfg.CapturePath)
	if err != nil {
		return err
	}
	defer func() { runErr = errors.Join(runErr, file.Close()) }()

	replacement, err := app.New(cfg)
	if err != nil {
		return err
	}
	defer func() { runErr = errors.Join(runErr, replacement.Close()) }()
	handler := capture.Middleware(replacement, capture.Options{
		Token: cfg.Token, Version: cfg.Version, Sinks: []io.Writer{file, os.Stdout},
	})
	srv := &http.Server{
		Addr:              ":" + cfg.Port,
		Handler:           handler,
		ReadHeaderTimeout: 5 * time.Second,
		ReadTimeout:       10 * time.Second,
		WriteTimeout:      10 * time.Second,
	}
	listener, err := net.Listen("tcp", srv.Addr)
	if err != nil {
		return err
	}
	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()
	done := make(chan error, 1)
	go func() { done <- srv.Serve(listener) }()
	log.Printf("replacement escuchando en %s version=%s storage=%s", listener.Addr(), cfg.Version, cfg.Storage)
	select {
	case err := <-done:
		if errors.Is(err, http.ErrServerClosed) {
			return nil
		}
		return err
	case <-ctx.Done():
		shutdownCtx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
		defer cancel()
		if err := srv.Shutdown(shutdownCtx); err != nil {
			srv.Close()
			return err
		}
		err := <-done
		if errors.Is(err, http.ErrServerClosed) {
			return nil
		}
		return err
	}
}
