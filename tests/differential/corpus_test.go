package differential

import (
	"flag"
	"net/http"
	"net/http/httptest"
	"os"
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

// Con -update-pending, TestCorpus reescribe pending-<version>.txt con los pasos
// que difieren hoy, en vez de fallar. Revisar el diff antes de commitear.
var updatePending = flag.Bool("update-pending", false, "reescribe pending-<version>.txt")

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

// TestCorpus reproduce la suite de BEHAVIOR_VERSION. Los pasos listados en
// pending-<version>.txt pueden diferir; falla si difiere cualquier otro paso
// (regresión) o si uno listado ya coincide (hay que sacarlo de la lista).
func TestCorpus(t *testing.T) {
	version := behaviorVersion()
	if !slices.Contains(config.Versions, version) {
		t.Fatalf("BEHAVIOR_VERSION desconocida: %q (conocidas %v)", version, config.Versions)
	}
	seqs, err := LoadSuite(repoRoot, version+".json")
	if err != nil {
		t.Fatalf("la versión %s necesita su suite: %v", version, err)
	}
	pendingFile := "pending-" + version + ".txt"
	// Al regenerar, la lista actual no se lee: puede estar desfasada o mal formada.
	pending := Pending{}
	if !*updatePending {
		if pending, err = LoadPending(pendingFile); err != nil {
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
			t.Errorf("%s nombra %q, que no está en la suite", pendingFile, name)
		}
	}

	current := Pending{}
	passed, pend, ran := 0, 0, 0
	for _, q := range seqs {
		t.Run(q.Name, func(t *testing.T) {
			ran++
			srv, client := serve(t, version)
			diffs, err := Replay(client, srv.URL, testToken, q)
			if err != nil {
				t.Fatal(err)
			}
			allowed := pending[q.Name]
			differing := map[int]bool{}
			for _, m := range diffs {
				differing[m.Index] = true
				if !allowed[m.Index] && !*updatePending {
					t.Errorf("regresión: %s", m)
				}
			}
			if len(differing) > 0 {
				current[q.Name] = differing
			}
			if *updatePending {
				return
			}
			fixed := map[int]bool{}
			for i := range allowed {
				if !differing[i] {
					fixed[i] = true
				}
			}
			if len(fixed) > 0 {
				t.Errorf("pasos %s ya coinciden: quitarlos de %s (-update-pending)", FormatSteps(fixed), pendingFile)
			}
			switch {
			case len(diffs) == 0:
				passed++
			case len(diffs) > 0 && !t.Failed():
				pend++
				t.Logf("pendiente, %d pasos difieren; primero:\n%s", len(diffs), diffs[0])
			}
		})
	}
	if *updatePending {
		// Escribir con un filtro -run o tras un fallo borraría pendientes de
		// secuencias que no se compararon.
		if ran != len(seqs) || t.Failed() {
			t.Fatalf("%s sin cambios: -update-pending exige ejecutar las %d secuencias sin errores (se ejecutaron %d)",
				pendingFile, len(seqs), ran)
		}
		if err := WritePending(pendingFile, seqs, current); err != nil {
			t.Fatal(err)
		}
		t.Logf("%s reescrito: %d secuencias con pasos pendientes", pendingFile, len(current))
		return
	}
	t.Logf("%s: %d secuencias, %d coinciden, %d pendientes", version, len(seqs), passed, pend)
}
