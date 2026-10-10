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
