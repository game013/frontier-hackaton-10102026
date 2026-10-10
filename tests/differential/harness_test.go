package differential

import (
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"reflect"
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
	if diffs, err := Replay(client, srv.URL, testToken, seqs["ok"]); err != nil || len(diffs) != 0 {
		t.Fatalf("ok debería coincidir: %v %v", diffs, err)
	}
	srv, client = serve(t, "v1")
	diffs, err := Replay(client, srv.URL, testToken, seqs["reordenado"])
	if err != nil || len(diffs) != 1 {
		t.Fatalf("reordenado debería diferir en un paso: %v %v", diffs, err)
	}
	if diffs[0].Index != 1 || !strings.Contains(diffs[0].Error(), "JSON equivalente: sí") {
		t.Fatalf("mensaje inesperado:\n%s", diffs[0])
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
	dir := t.TempDir()
	write := func(body string) string {
		file := filepath.Join(dir, "pending.txt")
		if err := os.WriteFile(file, []byte(body), 0o600); err != nil {
			t.Fatal(err)
		}
		return file
	}
	got, err := LoadPending(write("# comentario\n a 1,3-5  # nota\n\nb 0\n"))
	if err != nil || len(got) != 2 || FormatSteps(got["a"]) != "1,3-5" || FormatSteps(got["b"]) != "0" {
		t.Fatalf("%v %v", got, err)
	}
	for _, bad := range []string{"a\n", "a 1 2\n", "a 5-3\n", "a x\n", "a -1\n", "a 1\na 2\n"} {
		if _, err := LoadPending(write(bad)); err == nil {
			t.Errorf("%q debería ser inválido", bad)
		}
	}
	if got, err := LoadPending(filepath.Join(dir, "no-existe")); err != nil || len(got) != 0 {
		t.Fatalf("ausente: %v %v", got, err)
	}
}

func TestWritePendingRoundTrip(t *testing.T) {
	file := filepath.Join(t.TempDir(), "pending.txt")
	seqs := []Sequence{{Name: "b"}, {Name: "a"}, {Name: "c"}}
	in := Pending{"a": {1: true, 2: true, 3: true, 7: true}, "b": {0: true}}
	if err := WritePending(file, seqs, in); err != nil {
		t.Fatal(err)
	}
	raw, _ := os.ReadFile(file)
	if !strings.HasSuffix(string(raw), "b 0\na 1-3,7\n") {
		t.Fatalf("orden o rangos inesperados:\n%s", raw)
	}
	out, err := LoadPending(file)
	if err != nil || !reflect.DeepEqual(in, out) {
		t.Fatalf("%v %v", out, err)
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

// Las variantes reproducen exactamente las cabeceras de AUTH_VARIANTS en bb.py.
func TestAuthHeaderMatchesExplorerVariants(t *testing.T) {
	cases := map[string]string{
		"valid":   "Bearer tok",
		"empty":   "Bearer ",
		"invalid": "Bearer token-invalido-0000",
		"scheme":  "Basic tok",
		"lower":   "bearer tok",
		"spaces":  "Bearer  tok",
		"bare":    "tok",
	}
	for label, want := range cases {
		if !knownAuth[label] {
			t.Errorf("%s no está en knownAuth", label)
		}
		if got, ok := authHeader(label, "tok"); !ok || got != want {
			t.Errorf("authHeader(%s) = %q, %v; want %q", label, got, ok, want)
		}
	}
	if _, ok := authHeader("none", "tok"); ok {
		t.Error("none no debe enviar Authorization")
	}
}
