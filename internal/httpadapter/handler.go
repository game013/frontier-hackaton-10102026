// Package httpadapter es el sobre HTTP del reemplazo: autenticación, rutas
// exactas y escritura de cuerpos byte a byte. No contiene reglas de negocio.
package httpadapter

import (
	"crypto/subtle"
	"encoding/json"
	"io"
	"net/http"
	"strings"

	"github.com/game013/frontier-hackaton-10102026/internal/protocol"
)

// Cuerpos exactos observados (spec, sección 5). Sin newline final.
var (
	respOK   = []byte(`{"ok":true}`)
	respPong = []byte(`{"pong":true}`)
	respE001 = []byte(`{"error":"E001","mensaje":"no autorizado"}`)
	respE100 = []byte(`{"error":"E100","mensaje":"json inválido"}`)
	respE101 = []byte(`{"error":"E101","mensaje":"cuerpo demasiado grande"}`)
	respE102 = []byte(`{"error":"E102","mensaje":"falta m"}`)
	respE500 = []byte(`{"error":"E500","mensaje":"error interno"}`) // fallo de persistencia, supuesto MEM-07
	respE404 = []byte(`{"error":"E404","mensaje":"ruta desconocida"}`)
	// No es del original: solo lo ve un Handler sin WithExec (pruebas del
	// sobre); app conecta el motor. 501 para no confundirlo con lo observado.
	respNoEngine = []byte(`{"error":"B4","mensaje":"comando sin motor"}`)
)

type Handler struct {
	auth   []byte
	reset  func() error
	exec   func(protocol.Message) (int, []byte)
	halted func() (bool, int, []byte)
}

type Option func(*Handler)

// WithReset registra la acción que vacía el estado en POST /__reset.
func WithReset(fn func() error) Option { return func(h *Handler) { h.reset = fn } }

// WithExec registra quien ejecuta un mensaje que ya pasó el protocolo (forma,
// control, comando y aridad). Por defecto solo PING tiene respuesta.
func WithExec(fn func(protocol.Message) (int, []byte)) Option {
	return func(h *Handler) { h.exec = fn }
}

// WithHalted registra la detención del servicio: mientras fn devuelva true,
// todo POST /msg autenticado responde status y body, antes del tamaño, el
// JSON y el protocolo (ERR-599, r1 log 4378–4382, 4404–4407). Rutas, auth,
// /health y /__reset no cambian (4377, 4380, 4381, 4383, 4406).
func WithHalted(fn func() bool, status int, body []byte) Option {
	return func(h *Handler) { h.halted = func() (bool, int, []byte) { return fn(), status, body } }
}

// defaultExec responde PING (CMD-PING) y marca el resto como sin motor.
func defaultExec(m protocol.Message) (int, []byte) {
	if m.Cmd == "PING" {
		return http.StatusOK, respPong
	}
	return http.StatusNotImplemented, respNoEngine
}

func New(token string, opts ...Option) *Handler {
	h := &Handler{auth: []byte("Bearer " + token), reset: func() error { return nil }, exec: defaultExec,
		halted: func() (bool, int, []byte) { return false, 0, nil }}
	for _, o := range opts {
		o(h)
	}
	return h
}

func (h *Handler) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	status, body := h.precedence(r)
	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	w.WriteHeader(status)
	w.Write(body)
}

// precedence fija el orden medido del sobre (ENT-05): método+ruta exactos,
// luego auth, luego tamaño y JSON (estos dos, dentro de msg). Una ruta
// desconocida da E404 aunque falte la auth (A4 log 888–896).
func (h *Handler) precedence(r *http.Request) (int, []byte) {
	route := r.Method + " " + rawPath(r)
	switch route {
	case "GET /health", "POST /__reset", "POST /msg":
	default:
		return http.StatusNotFound, respE404
	}
	if subtle.ConstantTimeCompare([]byte(r.Header.Get("Authorization")), h.auth) != 1 {
		return http.StatusUnauthorized, respE001
	}
	switch route {
	case "POST /__reset":
		if err := h.reset(); err != nil {
			return http.StatusInternalServerError, respE500
		}
		return http.StatusOK, respOK
	case "POST /msg":
		if halted, status, body := h.halted(); halted {
			return status, body
		}
		return h.msg(r)
	}
	return http.StatusOK, respOK // GET /health
}

// maxBody es el mayor cuerpo de /msg que el original acepta (ENT-10).
const maxBody = 8192

func (h *Handler) msg(r *http.Request) (int, []byte) {
	// Se lee un byte de más para distinguir 8192 (pasa) de 8193 (E101).
	raw, err := io.ReadAll(io.LimitReader(r.Body, maxBody+1))
	if err == nil && len(raw) > maxBody {
		return http.StatusRequestEntityTooLarge, respE101
	}
	if err != nil || !json.Valid(raw) {
		return http.StatusBadRequest, respE100
	}
	// Clave exacta "m": un struct con tag aceptaría también "M".
	var obj map[string]json.RawMessage
	var m string
	// JSON válido que no es objeto, o m ausente/no string: E102 (log 46-47).
	if json.Unmarshal(raw, &obj) != nil || obj["m"] == nil || json.Unmarshal(obj["m"], &m) != nil ||
		string(obj["m"]) == "null" {
		return http.StatusBadRequest, respE102
	}
	msg, perr := protocol.Parse(m)
	if perr != nil {
		return perr.Status, perr.Body
	}
	return h.exec(msg)
}

// rawPath devuelve la ruta tal como llegó, sin query, sin decodificar escapes
// ni limpiar barras: /%6dsg y //msg no son /msg.
func rawPath(r *http.Request) string {
	p, _, _ := strings.Cut(r.RequestURI, "?")
	return p
}
