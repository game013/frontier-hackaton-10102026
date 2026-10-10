package capture

import (
	"bytes"
	"encoding/base64"
	"encoding/json"
	"errors"
	"io"
	"net/http"
	"net/http/httptest"
	"slices"
	"strings"
	"testing"
)

const token = "equipo-secreto"

type failingWriter struct{}

func (failingWriter) Write([]byte) (int, error) { return 0, errors.New("disco lleno") }

// echo responde con el cuerpo recibido para comprobar que la captura no lo consume.
func echo(w http.ResponseWriter, r *http.Request) {
	b, _ := io.ReadAll(r.Body)
	if r.URL.Path == "/__reset" {
		w.WriteHeader(http.StatusOK)
		w.Write([]byte(`{"ok":true}`))
		return
	}
	w.WriteHeader(http.StatusTeapot)
	w.Write(b)
}

func records(t *testing.T, buf *bytes.Buffer) []Record {
	t.Helper()
	var out []Record
	for _, line := range strings.Split(strings.TrimSpace(buf.String()), "\n") {
		var rec Record
		if err := json.Unmarshal([]byte(line), &rec); err != nil {
			t.Fatalf("línea no es JSON: %q", line)
		}
		out = append(out, rec)
	}
	return out
}

func do(h http.Handler, method, target, auth, body string) *httptest.ResponseRecorder {
	req := httptest.NewRequest(method, target, strings.NewReader(body))
	if auth != "" {
		req.Header.Set("Authorization", auth)
	}
	req.Header.Set("X-Evaluador", "caso-7")
	rec := httptest.NewRecorder()
	h.ServeHTTP(rec, req)
	return rec
}

func TestCapturesFullExchangeWithoutAlteringIt(t *testing.T) {
	var buf bytes.Buffer
	h := Middleware(http.HandlerFunc(echo), Options{Token: token, Version: "v1", Sinks: []io.Writer{&buf}})

	body := "{\"m\":\"ALTA;Lucía;82\"}\xff"
	rec := do(h, "POST", "/no%2Dexiste?x=1", "Bearer "+token, body)
	if rec.Code != http.StatusTeapot || rec.Body.String() != body {
		t.Fatalf("la captura alteró la respuesta: %d %q", rec.Code, rec.Body.String())
	}

	got := records(t, &buf)[0]
	if got.Kind != "capture" || got.Boot == "" || got.N != 1 || got.Seq != 0 || got.Version != "v1" {
		t.Fatalf("metadatos: %+v", got)
	}
	if got.Method != "POST" || got.URI != "/no%2Dexiste?x=1" {
		t.Fatalf("método/URI no crudos: %q %q", got.Method, got.URI)
	}
	if b, _ := base64.StdEncoding.DecodeString(got.BodyB64); string(b) != body {
		t.Fatalf("cuerpo b64 = %q", b)
	}
	if b, _ := base64.StdEncoding.DecodeString(got.RespB64); string(b) != body || got.Status != http.StatusTeapot {
		t.Fatalf("respuesta capturada = %d %q", got.Status, b)
	}
	if got.Auth != "team" || got.Headers["X-Evaluador"][0] != "caso-7" {
		t.Fatalf("auth/headers: %q %v", got.Auth, got.Headers)
	}
	if got.Headers["Authorization"][0] != "Bearer ${TEAM_TOKEN}" {
		t.Fatalf("Authorization no redactado: %v", got.Headers["Authorization"])
	}
	if strings.Contains(buf.String(), token) {
		t.Fatal("el token del equipo aparece en la captura")
	}
}

func TestAuthLabelsKeepForeignHeadersForReplay(t *testing.T) {
	var buf bytes.Buffer
	h := Middleware(http.HandlerFunc(echo), Options{Token: token, Sinks: []io.Writer{&buf}})
	do(h, "GET", "/health", "", "")
	do(h, "GET", "/health", "Basic "+token, "")
	do(h, "GET", "/health", "Bearer otro", "")
	recs := records(t, &buf)
	want := []struct{ label, header string }{
		{"none", ""},
		{"other", "Basic ${TEAM_TOKEN}"},
		{"other", "Bearer otro"},
	}
	for i, w := range want {
		var h string
		if v := recs[i].Headers["Authorization"]; len(v) > 0 {
			h = v[0]
		}
		if recs[i].Auth != w.label || h != w.header {
			t.Fatalf("registro %d: auth=%q header=%q, want %q %q", i, recs[i].Auth, h, w.label, w.header)
		}
	}
}

func TestSequencesAdvanceOnlyOnSuccessfulTeamReset(t *testing.T) {
	var buf bytes.Buffer
	h := Middleware(http.HandlerFunc(echo), Options{Token: token, Sinks: []io.Writer{&buf}})
	do(h, "POST", "/msg", "Bearer "+token, "a")
	do(h, "POST", "/__reset", "", "")              // sin auth: no abre secuencia
	do(h, "POST", "/__reset", "Bearer "+token, "") // abre la 1
	do(h, "POST", "/msg", "Bearer "+token, "b")
	do(h, "POST", "/__reset", "Bearer "+token, "") // abre la 2
	var seqs []int
	for _, r := range records(t, &buf) {
		seqs = append(seqs, r.Seq)
	}
	if want := []int{0, 0, 1, 1, 2}; !slices.Equal(seqs, want) {
		t.Fatalf("seqs = %v, want %v", seqs, want)
	}
}

func TestSinkFailureDoesNotChangeResponse(t *testing.T) {
	var ok bytes.Buffer
	h := Middleware(http.HandlerFunc(echo), Options{Token: token, Sinks: []io.Writer{failingWriter{}, &ok}})
	rec := do(h, "POST", "/msg", "", "hola")
	if rec.Code != http.StatusTeapot || rec.Body.String() != "hola" {
		t.Fatalf("respuesta alterada: %d %q", rec.Code, rec.Body.String())
	}
	if len(records(t, &ok)) != 1 {
		t.Fatal("un sink caído impidió escribir en los demás")
	}
}

func TestPanicIsCapturedAndAnswered500(t *testing.T) {
	var buf bytes.Buffer
	boom := http.HandlerFunc(func(http.ResponseWriter, *http.Request) { panic("x") })
	h := Middleware(boom, Options{Token: token, Sinks: []io.Writer{&buf}})
	rec := do(h, "POST", "/msg", "", "cuerpo")
	if rec.Code != http.StatusInternalServerError {
		t.Fatalf("status = %d", rec.Code)
	}
	got := records(t, &buf)[0]
	if got.Status != http.StatusInternalServerError || got.Panic == "" {
		t.Fatalf("pánico no registrado: %+v", got)
	}
}

func TestTokenRedactedFromURI(t *testing.T) {
	var buf bytes.Buffer
	h := Middleware(http.HandlerFunc(echo), Options{Token: token, Sinks: []io.Writer{&buf}})
	do(h, "GET", "/health?t="+token, "", "")
	got := records(t, &buf)[0]
	if got.URI != "/health?t=${TEAM_TOKEN}" || !got.Redacted || strings.Contains(buf.String(), token) {
		t.Fatalf("URI sin redactar: %q redacted=%v", got.URI, got.Redacted)
	}
}

// La etiqueta debe coincidir con lo que decide el handler (Header.Get: primer valor).
func TestDuplicateAuthorizationUsesFirstValue(t *testing.T) {
	var buf bytes.Buffer
	h := Middleware(http.HandlerFunc(echo), Options{Token: token, Sinks: []io.Writer{&buf}})
	req := httptest.NewRequest("POST", "/__reset", nil)
	req.Header.Add("Authorization", "Bearer "+token)
	req.Header.Add("Authorization", "x")
	h.ServeHTTP(httptest.NewRecorder(), req)
	if got := records(t, &buf)[0]; got.Auth != "team" || got.Seq != 1 {
		t.Fatalf("auth=%q seq=%d", got.Auth, got.Seq)
	}
}

// N y seq se asignan a la llegada: un request lento que empezó antes de un
// reset sigue en su secuencia aunque termine después.
func TestNumberingByArrival(t *testing.T) {
	var buf bytes.Buffer
	release, entered := make(chan struct{}), make(chan struct{})
	slow := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.RequestURI == "/lento" {
			close(entered)
			<-release
		}
		echo(w, r)
	})
	h := Middleware(slow, Options{Token: token, Sinks: []io.Writer{&buf}})
	done := make(chan struct{})
	go func() { do(h, "POST", "/lento", "Bearer "+token, "a"); close(done) }()
	<-entered
	do(h, "POST", "/__reset", "Bearer "+token, "")
	close(release)
	<-done
	byURI := map[string]Record{}
	for _, r := range records(t, &buf) {
		byURI[r.URI] = r
	}
	if r := byURI["/lento"]; r.N != 1 || r.Seq != 0 {
		t.Fatalf("lento: n=%d seq=%d, want 1 0", r.N, r.Seq)
	}
	if r := byURI["/__reset"]; r.N != 2 || r.Seq != 1 {
		t.Fatalf("reset: n=%d seq=%d, want 2 1", r.N, r.Seq)
	}
}

type failAfter struct {
	data []byte
	err  error
}

func (f *failAfter) Read(p []byte) (int, error) {
	if len(f.data) == 0 {
		return 0, f.err
	}
	n := copy(p, f.data)
	f.data = f.data[n:]
	return n, nil
}

// La captura no debe ocultar al handler un error de lectura del cuerpo.
func TestBodyReadErrorReachesHandler(t *testing.T) {
	strict := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if _, err := io.ReadAll(r.Body); err != nil {
			w.WriteHeader(http.StatusBadRequest)
			w.Write([]byte("E100"))
			return
		}
		w.Write([]byte("pong"))
	})
	serve := func(h http.Handler) *httptest.ResponseRecorder {
		req := httptest.NewRequest("POST", "/msg", nil)
		req.Body = io.NopCloser(&failAfter{[]byte(`{"m":"PING;1"}`), io.ErrUnexpectedEOF})
		rec := httptest.NewRecorder()
		h.ServeHTTP(rec, req)
		return rec
	}
	var buf bytes.Buffer
	plain := serve(strict)
	captured := serve(Middleware(strict, Options{Token: token, Sinks: []io.Writer{&buf}}))
	if captured.Code != plain.Code || captured.Body.String() != plain.Body.String() {
		t.Fatalf("con captura %d %q, sin captura %d %q", captured.Code, captured.Body, plain.Code, plain.Body)
	}
	got := records(t, &buf)[0]
	if got.BodyError == "" || got.Body == nil || *got.Body != `{"m":"PING;1"}` {
		t.Fatalf("captura del cuerpo parcial: %+v", got)
	}
}

