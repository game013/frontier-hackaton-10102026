package httpadapter

import (
	"io"
	"net/http/httptest"
	"strings"
	"testing"
)

const testToken = "equipo-secreto"

const (
	bodyOK      = `{"ok":true}`
	bodyPong    = `{"pong":true}`
	bodyE001    = `{"error":"E001","mensaje":"no autorizado"}`
	bodyE100    = `{"error":"E100","mensaje":"json inválido"}`
	bodyE102    = `{"error":"E102","mensaje":"falta m"}`
	bodyE301    = `{"error":"E301","mensaje":"comando desconocido "}`
	bodyE404    = `{"error":"E404","mensaje":"ruta desconocida"}`
	authNone    = "\x00none"
	authValid   = "Bearer " + testToken
	authEmpty   = "Bearer "
	authInvalid = "Bearer token-invalido-0000"
	authScheme  = "Basic " + testToken
)

type exchange struct {
	name, method, target, auth, contentType string
	body                                    *string
	status                                  int
	want                                    string
}

func str(s string) *string { return &s }

func run(t *testing.T, cases []exchange) {
	t.Helper()
	h := New(testToken)
	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			var body io.Reader
			if c.body != nil {
				body = strings.NewReader(*c.body)
			}
			req := httptest.NewRequest(c.method, c.target, body)
			if c.auth != authNone {
				req.Header.Set("Authorization", c.auth)
			}
			if c.contentType != "" {
				req.Header.Set("Content-Type", c.contentType)
			} else if c.body != nil {
				req.Header.Set("Content-Type", "application/json")
			}
			rec := httptest.NewRecorder()
			h.ServeHTTP(rec, req)
			if rec.Code != c.status || rec.Body.String() != c.want {
				t.Fatalf("got %d %q, want %d %q", rec.Code, rec.Body.String(), c.status, c.want)
			}
		})
	}
}

// Casos observados en experimentos.jsonl; el nombre lleva el ID del log.
func TestLogCases(t *testing.T) {
	ping64 := str(`{"m":"PING;64"}`)
	run(t, []exchange{
		{"log02_ping", "POST", "/msg", authValid, "", ping64, 200, bodyPong},
		{"log33_ping_1", "POST", "/msg", authValid, "", str(`{"m":"PING;1"}`), 200, bodyPong},
		{"log34_reset", "POST", "/__reset", authValid, "", nil, 200, bodyOK},
		{"log35_health", "GET", "/health", authValid, "", nil, 200, bodyOK},
		{"log36_health_sin_auth", "GET", "/health", authNone, "", nil, 401, bodyE001},
		{"log37_msg_sin_auth", "POST", "/msg", authNone, "", ping64, 401, bodyE001},
		{"log38_msg_bearer_vacio", "POST", "/msg", authEmpty, "", ping64, 401, bodyE001},
		{"log39_msg_token_invalido", "POST", "/msg", authInvalid, "", ping64, 401, bodyE001},
		{"log40_msg_esquema_basic", "POST", "/msg", authScheme, "", ping64, 401, bodyE001},
		{"log41_get_msg", "GET", "/msg", authValid, "", nil, 404, bodyE404},
		{"log42_get_inexistente", "GET", "/no-existe", authValid, "", nil, 404, bodyE404},
		{"log43_post_inexistente", "POST", "/no-existe", authValid, "", ping64, 404, bodyE404},
		{"log44_doble_barra", "POST", "//msg", authValid, "", ping64, 404, bodyE404},
		{"log45_json_malformado", "POST", "/msg", authValid, "", str(`{`), 400, bodyE100},
		{"log46_sin_m", "POST", "/msg", authValid, "", str(`{}`), 400, bodyE102},
		{"log47_m_numerico", "POST", "/msg", authValid, "", str(`{"m":64}`), 400, bodyE102},
		{"log48_campo_extra", "POST", "/msg", authValid, "", str(`{"m":"PING;64","x":1}`), 200, bodyPong},
		{"log49_text_plain", "POST", "/msg", authValid, "text/plain", ping64, 200, bodyPong},
		{"log50_reset_sin_auth", "POST", "/__reset", authNone, "", nil, 401, bodyE001},
	})
}

// Supuesto ENT-05: auth se evalúa antes que ruta y JSON. Sin evidencia del
// original; cuando A4 lo mida, ajustar estos casos y precedence() juntos.
func TestPrecedenceAssumption(t *testing.T) {
	run(t, []exchange{
		{"sin_auth_ruta_inexistente", "GET", "/no-existe", authNone, "", nil, 401, bodyE001},
		{"sin_auth_json_malformado", "POST", "/msg", authNone, "", str(`{`), 401, bodyE001},
		{"token_invalido_metodo_incorrecto", "GET", "/msg", authInvalid, "", nil, 401, bodyE001},
		{"ruta_inexistente_json_malformado", "POST", "/no-existe", authValid, "", str(`{`), 404, bodyE404},
	})
}

// Supuestos de B1 sin evidencia: ruta sin decodificar, query ignorada,
// stub de /msg hasta B3.
func TestRoutingAndStubAssumptions(t *testing.T) {
	run(t, []exchange{
		{"escape_no_se_decodifica", "POST", "/%6dsg", authValid, "", str(`{"m":"PING;64"}`), 404, bodyE404},
		{"barra_final", "POST", "/msg/", authValid, "", str(`{"m":"PING;64"}`), 404, bodyE404},
		{"query_ignorada", "POST", "/msg?x=1", authValid, "", str(`{"m":"PING;64"}`), 200, bodyPong},
		{"health_post", "POST", "/health", authValid, "", nil, 404, bodyE404},
		{"reset_get", "GET", "/__reset", authValid, "", nil, 404, bodyE404},
		{"json_no_objeto", "POST", "/msg", authValid, "", str(`[]`), 400, bodyE102},
		{"m_null", "POST", "/msg", authValid, "", str(`{"m":null}`), 400, bodyE102},
		{"clave_M_mayuscula", "POST", "/msg", authValid, "", str(`{"M":"PING;1"}`), 400, bodyE102},
		{"cuerpo_vacio", "POST", "/msg", authValid, "", str(``), 400, bodyE100},
		{"json_con_basura", "POST", "/msg", authValid, "", str(`{"m":"PING;1"} x`), 400, bodyE100},
		{"stub_comando_no_ping", "POST", "/msg", authValid, "", str(`{"m":"ALTA;Lucia;82"}`), 400, bodyE301},
	})
}

func TestResetCallsHook(t *testing.T) {
	calls := 0
	h := New(testToken, WithReset(func() { calls++ }))
	req := httptest.NewRequest("POST", "/__reset", nil)
	req.Header.Set("Authorization", authValid)
	h.ServeHTTP(httptest.NewRecorder(), req)
	if calls != 1 {
		t.Fatalf("reset hook calls = %d, want 1", calls)
	}
	req = httptest.NewRequest("POST", "/__reset", nil)
	h.ServeHTTP(httptest.NewRecorder(), req)
	if calls != 1 {
		t.Fatalf("unauthenticated reset ran hook")
	}
}

func TestResponseHeaders(t *testing.T) {
	h := New(testToken)
	req := httptest.NewRequest("GET", "/health", nil)
	req.Header.Set("Authorization", authValid)
	rec := httptest.NewRecorder()
	h.ServeHTTP(rec, req)
	if got := rec.Header().Get("Content-Type"); got != "application/json; charset=utf-8" {
		t.Fatalf("Content-Type = %q", got)
	}
}
