package differential

import (
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"slices"
	"sort"
	"testing"
	"time"

	"github.com/game013/frontier-hackaton-10102026/internal/app"
	"github.com/game013/frontier-hackaton-10102026/internal/config"
)

const (
	repoRoot  = "../.."
	testToken = "equipo-secreto"
)

// stepTimeout es el tiempo que el evaluador da a cada paso, cuerpo incluido.
const stepTimeout = 5 * time.Second

func behaviorVersion() string {
	if v := os.Getenv("BEHAVIOR_VERSION"); v != "" {
		return v
	}
	return config.Versions[len(config.Versions)-1]
}

// serve levanta una instancia nueva del reemplazo sobre TCP real, para que el
// parseo de net/http (rutas crudas, cuerpos) sea el mismo que en despliegue.
func serve(t *testing.T, version string) (*httptest.Server, *http.Client) {
	t.Helper()
	srv := httptest.NewServer(app.New(config.Config{Token: testToken, Version: version}))
	t.Cleanup(srv.Close)
	client := srv.Client()
	client.Timeout = stepTimeout
	client.CheckRedirect = func(*http.Request, []*http.Request) error { return http.ErrUseLastResponse }
	return srv, client
}

// TestCorpus reproduce la suite de BEHAVIOR_VERSION. Una secuencia en
// pending-<version>.txt se ejecuta y se informa sin fallar; si ya coincide en
// todos sus pasos, falla para que se quite de la lista.
func TestCorpus(t *testing.T) {
	version := behaviorVersion()
	if !slices.Contains(config.Versions, version) {
		t.Fatalf("BEHAVIOR_VERSION desconocida: %q (conocidas %v)", version, config.Versions)
	}
	seqs, err := LoadSuite(repoRoot, version+".json")
	if err != nil {
		t.Fatalf("la versión %s necesita su suite: %v", version, err)
	}
	pending, err := LoadPending(filepath.Join(".", "pending-"+version+".txt"))
	if err != nil {
		t.Fatal(err)
	}
	known := map[string]bool{}
	for _, q := range seqs {
		known[q.Name] = true
	}
	var stale []string
	for name := range pending {
		if !known[name] {
			stale = append(stale, name)
		}
	}
	sort.Strings(stale)
	for _, name := range stale {
		t.Errorf("pending-%s.txt nombra %q, que no está en la suite", version, name)
	}

	passed, pend := 0, 0
	for _, q := range seqs {
		t.Run(q.Name, func(t *testing.T) {
			srv, client := serve(t, version)
			m, err := Replay(client, srv.URL, testToken, q)
			if err != nil {
				t.Fatal(err)
			}
			switch {
			case pending[q.Name] && m == nil:
				t.Errorf("ya coincide en sus %d pasos: quitarla de pending-%s.txt", len(q.Steps), version)
			case pending[q.Name]:
				pend++
				t.Logf("pendiente:\n%s", m)
			case m != nil:
				t.Errorf("%s", m)
			default:
				passed++
			}
		})
	}
	t.Logf("%s: %d secuencias, %d coinciden, %d pendientes", version, len(seqs), passed, pend)
}
