package app

import (
	"encoding/json"
	"fmt"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"github.com/game013/frontier-hackaton-10102026/internal/config"
	"github.com/game013/frontier-hackaton-10102026/internal/protocol"
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
	for _, storage := range []config.Storage{config.StorageSQLite, config.StorageMemory} {
		t.Run(string(storage), func(t *testing.T) {
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
			if storage == config.StorageMemory {
				want = `{"cuentaId":"AC-0001"}`
			}
			request(t, a, cfg.Token, "/msg", `{"m":"ALTA;Lucia;82"}`, 201, want)
			request(t, a, cfg.Token, "/__reset", "", 200, `{"ok":true}`)
			request(t, a, cfg.Token, "/msg", `{"m":"ALTA;Lucia;82"}`, 201, `{"cuentaId":"AC-0001"}`)
		})
	}
}

func TestBehaviorVersionComposition(t *testing.T) {
	for _, storage := range []config.Storage{config.StorageMemory, config.StorageSQLite} {
		for _, version := range []string{"", "v1", "v2"} {
			t.Run(string(storage)+"/"+version, func(t *testing.T) {
				cfg := config.Config{Token: "test-token", Version: version, Storage: storage, StatePath: filepath.Join(t.TempDir(), "state.db")}
				a, err := New(cfg)
				if err != nil {
					t.Fatal(err)
				}
				defer a.Close()
				request(t, a, cfg.Token, "/msg", `{"m":"ALTA;Lucia;82"}`, 201, `{"cuentaId":"AC-0001"}`)
				text := "CONSULTA;AC-0001"
				body, _ := json.Marshal(map[string]string{"m": fmt.Sprintf("%s;%02d", text, protocol.Control(text))})
				want := `{"cuenta_id":"AC-0001","saldo":"0.00"}`
				if version == "v1" {
					want = `{"cuenta_id":"AC-0001","saldo":0}`
				}
				request(t, a, cfg.Token, "/msg", string(body), 200, want)
			})
		}
	}
	path := filepath.Join(t.TempDir(), "must-not-exist.db")
	if a, err := New(config.Config{Version: "v9", Storage: config.StorageSQLite, StatePath: path}); err == nil {
		a.Close()
		t.Fatal("versión desconocida aceptada sin Load")
	}
	if _, err := os.Stat(path); !os.IsNotExist(err) {
		t.Fatalf("versión inválida abrió almacenamiento: %v", err)
	}
}

func TestInitializationAndStorageFailure(t *testing.T) {
	for _, cfg := range []config.Config{
		{Storage: "unknown"}, {Storage: config.StorageSQLite}, {Storage: config.StorageSQLite, StatePath: t.TempDir()},
	} {
		if a, err := New(cfg); err == nil {
			a.Close()
			t.Fatal("config inválida aceptada")
		}
	}
	a, err := New(config.Config{Token: "test-token", Storage: config.StorageSQLite, StatePath: filepath.Join(t.TempDir(), "state.db")})
	if err != nil {
		t.Fatal(err)
	}
	if err := a.Close(); err != nil {
		t.Fatal(err)
	}
	request(t, a, "test-token", "/__reset", "", 500, `{"error":"E500","mensaje":"error interno"}`)
	request(t, a, "test-token", "/msg", `{"m":"ALTA;Lucia;82"}`, 500, `{"error":"E500","mensaje":"error interno"}`)
}
