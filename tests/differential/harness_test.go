package differential

import (
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

// Pruebas del propio arnés con evidencia sintética de testdata/.

func loadFixture(t *testing.T) map[string]Sequence {
	t.Helper()
	seqs, err := LoadSuite("testdata", "testdata/ok.json")
	if err != nil {
		t.Fatal(err)
	}
	out := map[string]Sequence{}
	for _, q := range seqs {
		out[q.Name] = q
	}
	return out
}

func TestLoadSuiteGroupsBySeqAndDropsInfrastructure(t *testing.T) {
	q := loadFixture(t)["ok"]
	var ids []int
	for _, st := range q.Steps {
		ids = append(ids, st.ID)
	}
	// 3 es la respuesta de rate limit; 7 llega intercalada tras otra secuencia.
	want := []int{1, 2, 4, 7}
	if len(ids) != len(want) {
		t.Fatalf("ids %v, quiero %v", ids, want)
	}
	for i := range want {
		if ids[i] != want[i] {
			t.Fatalf("ids %v, quiero %v", ids, want)
		}
	}
	if q.Steps[3].ContentType != "application/json" || q.Steps[2].Body != nil || q.Steps[0].Body == nil {
		t.Fatalf("cuerpos/Content-Type mal reconstruidos: %+v", q.Steps)
	}
}

func TestReplayMatchesAndReportsByteDiffs(t *testing.T) {
	seqs := loadFixture(t)
	srv, client := serve(t, "v1")
	if m, err := Replay(client, srv.URL, testToken, seqs["ok"]); err != nil || m != nil {
		t.Fatalf("ok debería coincidir: %v %v", m, err)
	}
	srv, client = serve(t, "v1")
	m, err := Replay(client, srv.URL, testToken, seqs["reordenado"])
	if err != nil || m == nil {
		t.Fatalf("reordenado debería diferir en bytes: %v %v", m, err)
	}
	if m.Index != 1 || !strings.Contains(m.Error(), "JSON equivalente: sí") {
		t.Fatalf("mensaje inesperado:\n%s", m)
	}
}

// Un paso que tarda más que el límite del evaluador es un fallo, no un acierto.
func TestReplayEnforcesStepTimeout(t *testing.T) {
	release := make(chan struct{})
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Write([]byte(`{"ok":`))
		w.(http.Flusher).Flush()
		<-release
		w.Write([]byte(`true}`))
	}))
	defer srv.Close()
	defer close(release)
	client := srv.Client()
	client.Timeout = 50 * time.Millisecond
	q := Sequence{Name: "lenta", Steps: []Step{{Method: "POST", Path: "/__reset", Auth: "valid",
		Body: []byte{}, Status: 200, Response: []byte(`{"ok":true}`)}}}
	if _, err := Replay(client, srv.URL, testToken, q); err == nil {
		t.Fatal("se esperaba timeout al leer el cuerpo")
	}
	if _, c := serve(t, "v1"); c.Timeout != stepTimeout {
		t.Fatalf("el cliente del arnés usa timeout %v", c.Timeout)
	}
}

func TestLoadSuiteRejectsUnreproducibleSequences(t *testing.T) {
	cases := map[string]string{
		"sin-bytes":  "no tiene bytes",
		"incompleta": "secuencia incompleta",
		"sin-reset":  "no empieza con POST /__reset",
		"no-existe":  "ninguna secuencia coincide",
	}
	dir := t.TempDir()
	data, err := os.ReadFile("testdata/invalidas.jsonl")
	if err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(dir, "invalidas.jsonl"), data, 0o600); err != nil {
		t.Fatal(err)
	}
	for seq, want := range cases {
		suite := filepath.Join(dir, seq+".json")
		body := `{"sources":[{"file":"invalidas.jsonl","seqs":["` + seq + `"]}]}`
		if err := os.WriteFile(suite, []byte(body), 0o600); err != nil {
			t.Fatal(err)
		}
		if _, err := LoadSuite(dir, suite); err == nil || !strings.Contains(err.Error(), want) {
			t.Errorf("%s: error %v, quiero %q", seq, err, want)
		}
	}
}

func TestLoadPending(t *testing.T) {
	file := filepath.Join(t.TempDir(), "pending.txt")
	if err := os.WriteFile(file, []byte("# comentario\n a  # nota\n\nb\n"), 0o600); err != nil {
		t.Fatal(err)
	}
	got, err := LoadPending(file)
	if err != nil || len(got) != 2 || !got["a"] || !got["b"] {
		t.Fatalf("%v %v", got, err)
	}
	if got, err := LoadPending(file + ".no"); err != nil || len(got) != 0 {
		t.Fatalf("ausente: %v %v", got, err)
	}
}

func TestJSONEqual(t *testing.T) {
	for _, c := range []struct {
		a, b string
		want bool
	}{
		{`{"a":1,"b":[1,2]}`, `{"b":[1,2],"a":1}`, true},
		{`{"b":[2,1]}`, `{"b":[1,2]}`, false},
		{`{"n":1.0}`, `{"n":1}`, false},
		{`{"a":1} x`, `{"a":1}`, false},
		{`texto`, `texto`, false},
	} {
		if got := jsonEqual([]byte(c.a), []byte(c.b)); got != c.want {
			t.Errorf("jsonEqual(%s, %s) = %v", c.a, c.b, got)
		}
	}
}
