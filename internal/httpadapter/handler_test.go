package httpadapter

import (
	"errors"
	"io"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/game013/frontier-hackaton-10102026/internal/protocol"
)

const testToken = "equipo-secreto"

const (
	bodyOK       = `{"ok":true}`
	bodyPong     = `{"pong":true}`
	bodyE001     = `{"error":"E001","mensaje":"no autorizado"}`
	bodyE100     = `{"error":"E100","mensaje":"json inválido"}`
	bodyE101     = `{"error":"E101","mensaje":"cuerpo demasiado grande"}`
	bodyE102     = `{"error":"E102","mensaje":"falta m"}`
	bodyE103     = `{"error":"E103","mensaje":"falta control"}`
	bodyE202     = `{"error":"E202","mensaje":"control inválido"}`
	bodyE301Sug  = `{"error":"E301","mensaje":"comando desconocido ","sugerencia":"ALTA"}`
	bodyE302     = `{"error":"E302","mensaje":"aridad inválida"}`
	bodyE404     = `{"error":"E404","mensaje":"ruta desconocida"}`
	bodyNoEngine = `{"error":"B4","mensaje":"comando sin motor"}`
	authNone     = "\x00none"
	authValid    = "Bearer " + testToken
	authEmpty    = "Bearer "
	authInvalid  = "Bearer token-invalido-0000"
	authScheme   = "Basic " + testToken
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

// ENT-05: método+ruta → auth → tamaño → JSON (A4 log 888–896, 1300–1301,
// 1329–1331). Una ruta desconocida da E404 aunque falte la auth.
func TestPrecedence(t *testing.T) {
	big := str(`{"m":"PING;64","x":"` + strings.Repeat("a", 9000) + `"}`)
	run(t, []exchange{
		{"log888_sin_auth_ruta_inexistente", "GET", "/no-existe", authNone, "", nil, 404, bodyE404},
		{"log1329_sin_auth_post_health", "POST", "/health", authNone, "", nil, 404, bodyE404},
		{"log1330_sin_auth_get_reset", "GET", "/__reset", authNone, "", nil, 404, bodyE404},
		{"log1331_sin_auth_put_msg", "PUT", "/msg", authNone, "", str(`{"m":"PING;64"}`), 404, bodyE404},
		{"token_invalido_metodo_incorrecto", "GET", "/msg", authInvalid, "", nil, 404, bodyE404},
		{"sin_auth_json_malformado", "POST", "/msg", authNone, "", str(`{`), 401, bodyE001},
		{"log1300_sin_auth_cuerpo_grande", "POST", "/msg", authNone, "", big, 401, bodyE001},
		{"log1301_ruta_inexistente_cuerpo_grande", "POST", "/nada", authValid, "", big, 404, bodyE404},
		{"ruta_inexistente_json_malformado", "POST", "/no-existe", authValid, "", str(`{`), 404, bodyE404},
		{"head_health_sin_auth", "HEAD", "/health", authNone, "", nil, 404, bodyE404},
	})
}

// ENT-10: el cuerpo de /msg admite 8192 bytes; 8193 → 413 E101, antes que el
// JSON (A4 log 1298–1299, 958). El tope en otras rutas no se midió: /__reset
// ignora el cuerpo (supuesto: sin tope).
func TestBodyLimit(t *testing.T) {
	pad := func(n int) *string {
		head, tail := `{"m":"PING;64","x":"`, `"}`
		return str(head + strings.Repeat("a", n-len(head)-len(tail)) + tail)
	}
	run(t, []exchange{
		{"log1298_8192_pasa", "POST", "/msg", authValid, "", pad(8192), 200, bodyPong},
		{"log1299_8193_e101", "POST", "/msg", authValid, "", pad(8193), 413, bodyE101},
		{"e101_antes_que_json", "POST", "/msg", authValid, "", str("{" + strings.Repeat(" ", 9000)), 413, bodyE101},
	})
}

// Supuestos de B1 sin evidencia: ruta sin decodificar, query ignorada.
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
	})
}

// /msg delega en protocol.Parse; los errores de protocolo salen tal cual y
// PING responde sin motor. Casos del log (A4).
func TestMsgUsesProtocol(t *testing.T) {
	run(t, []exchange{
		{"log939_m_vacia", "POST", "/msg", authValid, "", str(`{"m":""}`), 400, bodyE103},
		{"log1074_ping_minusculas", "POST", "/msg", authValid, "", str(`{"m":"ping;64"}`), 200, bodyPong},
		{"log1066_ping_control_libre", "POST", "/msg", authValid, "", str(`{"m":"PING;XX"}`), 200, bodyPong},
		{"log1073_ping_aridad", "POST", "/msg", authValid, "", str(`{"m":"PING;1;2"}`), 400, bodyE302},
		{"log60_control_invalido", "POST", "/msg", authValid, "", str(`{"m":"ALTA;Lucia;83"}`), 400, bodyE202},
		{"log1307_sugerencia", "POST", "/msg", authValid, "", str(`{"m":"ALT;Lucia;24"}`), 400, bodyE301Sug},
		// Supuesto hasta B4: un comando con estado válido no tiene motor.
		{"sin_motor_hasta_b4", "POST", "/msg", authValid, "", str(`{"m":"ALTA;Lucia;82"}`), 501, bodyNoEngine},
	})
}

func TestMsgExecReceivesParsedMessage(t *testing.T) {
	var got protocol.Message
	h := New(testToken, WithExec(func(m protocol.Message) (int, []byte) {
		got = m
		return 201, []byte(`{"cuentaId":"AC-0001"}`)
	}))
	req := httptest.NewRequest("POST", "/msg", strings.NewReader(`{"m":"alta;Lucia;82"}`))
	req.Header.Set("Authorization", authValid)
	rec := httptest.NewRecorder()
	h.ServeHTTP(rec, req)
	if rec.Code != 201 || rec.Body.String() != `{"cuentaId":"AC-0001"}` {
		t.Fatalf("got %d %q", rec.Code, rec.Body.String())
	}
	if got.Cmd != "ALTA" || len(got.Args) != 1 || got.Args[0] != "Lucia" {
		t.Fatalf("exec recibió %+v", got)
	}
}

func TestResetCallsHook(t *testing.T) {
	calls := 0
	h := New(testToken, WithReset(func() error { calls++; return nil }))
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

func TestResetFailureDoesNotReportSuccess(t *testing.T) {
	h := New(testToken, WithReset(func() error { return errors.New("storage unavailable") }))
	req := httptest.NewRequest("POST", "/__reset", nil)
	req.Header.Set("Authorization", authValid)
	rec := httptest.NewRecorder()
	h.ServeHTTP(rec, req)
	if rec.Code != 500 || rec.Body.String() != `{"error":"E500","mensaje":"error interno"}` {
		t.Fatalf("got %d %q", rec.Code, rec.Body.String())
	}
}

// ERR-599: la detención intercepta solo POST /msg autenticado, antes del
// tamaño y del JSON; no llama a exec. E599 frente a E101 es supuesto.
func TestHaltedInterceptsOnlyAuthenticatedMsg(t *testing.T) {
	execs := 0
	h := New(testToken,
		WithExec(func(protocol.Message) (int, []byte) { execs++; return 200, nil }),
		WithHalted(func() bool { return true }, 503, []byte("detenido")))
	for _, c := range []struct {
		method, target, auth, body string
		status                     int
	}{
		{"POST", "/msg", authValid, `{"m":"PING;64"}`, 503},
		{"POST", "/msg", authValid, "{", 503},
		{"POST", "/msg", authValid, strings.Repeat("x", maxBody+1), 503},
		{"POST", "/msg", "", `{"m":"PING;64"}`, 401},
		{"GET", "/health", authValid, "", 200},
		{"POST", "/__reset", authValid, "", 200},
		{"GET", "/no-existe", authValid, "", 404},
	} {
		req := httptest.NewRequest(c.method, c.target, strings.NewReader(c.body))
		if c.auth != "" {
			req.Header.Set("Authorization", c.auth)
		}
		rec := httptest.NewRecorder()
		h.ServeHTTP(rec, req)
		if rec.Code != c.status {
			t.Fatalf("%s %s %.20q: status %d, want %d", c.method, c.target, c.body, rec.Code, c.status)
		}
	}
	if execs != 0 {
		t.Fatalf("exec llamado %d veces durante la detención", execs)
	}
}
