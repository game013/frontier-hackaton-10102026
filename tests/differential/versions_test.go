package differential

import (
	"bytes"
	"os"
	"os/exec"
	"reflect"
	"strings"
	"testing"

	"github.com/game013/frontier-hackaton-10102026/internal/config"
)

func TestCorpusVersionSelection(t *testing.T) {
	for _, tc := range []struct {
		name, version string
		updating      bool
		want          []string
		errorText     string
	}{
		{name: "default_all", want: config.Versions},
		{name: "explicit_v1", version: "v1", want: []string{"v1"}},
		{name: "explicit_v2", version: "v2", want: []string{"v2"}},
		{name: "unknown", version: "v9", errorText: "desconocida"},
		{name: "update_needs_version", updating: true, errorText: "explícita"},
		{name: "update_explicit", version: "v2", updating: true, want: []string{"v2"}},
	} {
		t.Run(tc.name, func(t *testing.T) {
			got, err := corpusVersions(tc.version, tc.updating)
			if tc.errorText != "" {
				if err == nil || !strings.Contains(err.Error(), tc.errorText) {
					t.Fatalf("error %v", err)
				}
			} else if err != nil || !reflect.DeepEqual(got, tc.want) {
				t.Fatalf("got %v %v, want %v", got, err, tc.want)
			}
		})
	}
}

// El guard se comprueba en el binario real de pruebas y antes de toda escritura,
// tanto ante selección ambigua como ante un filtro parcial de secuencias.
func TestCorpusUpdateGuardsPreservePending(t *testing.T) {
	exe, err := os.Executable()
	if err != nil {
		t.Fatal(err)
	}
	for _, tc := range []struct{ name, version, filter, errorText string }{
		{"no_version", "", "^TestCorpus$", "BEHAVIOR_VERSION explícita"},
		{"filtered", "v1", "^TestCorpus$/^v1$/^a3-v1r-17", "exige ejecutar las"},
	} {
		t.Run(tc.name, func(t *testing.T) {
			before := map[string][]byte{}
			for _, v := range config.Versions {
				path := "pending-" + v + ".txt"
				raw, err := os.ReadFile(path)
				if err != nil {
					t.Fatal(err)
				}
				before[path] = raw
			}
			cmd := exec.Command(exe, "-test.run="+tc.filter, "-update-pending")
			cmd.Env = []string{"BEHAVIOR_VERSION=" + tc.version}
			out, err := cmd.CombinedOutput()
			if err == nil || !strings.Contains(string(out), tc.errorText) {
				t.Fatalf("guard no falló como se esperaba: %v\n%s", err, out)
			}
			for path, want := range before {
				got, err := os.ReadFile(path)
				if err != nil || !bytes.Equal(got, want) {
					t.Fatalf("guard modificó %s: %v", path, err)
				}
			}
		})
	}
}
