package app

import (
	"net/http/httptest"
	"path/filepath"
	"strings"
	"testing"

	"github.com/game013/frontier-hackaton-10102026/internal/config"
)

func request(t *testing.T, app *App, token, path, body string, status int, expected string) {
	t.Helper()
	r := httptest.NewRequest("POST", path, strings.NewReader(body))
	r.Header.Set("Authorization", "Bearer "+token)
	w := httptest.NewRecorder()
	app.ServeHTTP(w, r)
	if w.Code != status || w.Body.String() != expected {
		t.Fatalf("%s got %d %q, want %d %q", path, w.Code, w.Body.String(), status, expected)
	}
}

func TestStorageSelection(t *testing.T) {
	for _, storage := range []string{"sqlite", "memory"} {
		t.Run(storage, func(t *testing.T) {
			cfg := config.Config{Token: "test-token", Storage: storage, StatePath: filepath.Join(t.TempDir(), "state.db")}
			a, err := New(cfg)
			if err != nil {
				t.Fatal(err)
			}
			request(t, a, cfg.Token, "/msg", `{"m":"ALTA;Lucia;82"}`, 201, `{"cuentaId":"AC-0001"}`)
			a.Close()
			a, err = New(cfg)
			if err != nil {
				t.Fatal(err)
			}
			defer a.Close()
			want := `{"cuentaId":"AC-0002"}`
			if storage == "memory" {
				want = `{"cuentaId":"AC-0001"}`
			}
			request(t, a, cfg.Token, "/msg", `{"m":"ALTA;Lucia;82"}`, 201, want)
			request(t, a, cfg.Token, "/__reset", "", 200, `{"ok":true}`)
			request(t, a, cfg.Token, "/msg", `{"m":"ALTA;Lucia;82"}`, 201, `{"cuentaId":"AC-0001"}`)
		})
	}
}

func TestInitializationAndStorageFailure(t *testing.T) {
	for _, cfg := range []config.Config{
		{Storage: "unknown"}, {Storage: "sqlite"}, {Storage: "sqlite", StatePath: t.TempDir()},
	} {
		if a, err := New(cfg); err == nil {
			a.Close()
			t.Fatal("config inválida aceptada")
		}
	}
	a, err := New(config.Config{Token: "test-token", Storage: "sqlite", StatePath: filepath.Join(t.TempDir(), "state.db")})
	if err != nil {
		t.Fatal(err)
	}
	if err := a.Close(); err != nil {
		t.Fatal(err)
	}
	request(t, a, "test-token", "/__reset", "", 500, `{"error":"E500","mensaje":"error interno"}`)
	request(t, a, "test-token", "/msg", `{"m":"ALTA;Lucia;82"}`, 500, `{"error":"E500","mensaje":"error interno"}`)
}
