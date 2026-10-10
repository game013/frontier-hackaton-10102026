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
	respE102 = []byte(`{"error":"E102","mensaje":"falta m"}`)
	respE404 = []byte(`{"error":"E404","mensaje":"ruta desconocida"}`)
	// No es del original: marca los comandos con estado hasta que B4 conecte
	// el motor. 501 para que nunca se confunda con una respuesta observada.
	respNoEngine = []byte(`{"error":"B4","mensaje":"comando sin motor"}`)
)

type Handler struct {
	auth  []byte
	reset func()
	exec  func(protocol.Message) (int, []byte)
}

type Option func(*Handler)

// WithReset registra la acción que vacía el estado en POST /__reset.
func WithReset(fn func()) Option { return func(h *Handler) { h.reset = fn } }

// WithExec registra quien ejecuta un mensaje que ya pasó el protocolo (forma,
// control, comando y aridad). Por defecto solo PING tiene respuesta.
func WithExec(fn func(protocol.Message) (int, []byte)) Option {
	return func(h *Handler) { h.exec = fn }
}

// defaultExec responde PING (CMD-PING) y marca el resto como sin motor.
func defaultExec(m protocol.Message) (int, []byte) {
	if m.Cmd == "PING" {
		return http.StatusOK, respPong
	}
	return http.StatusNotImplemented, respNoEngine
}

func New(token string, opts ...Option) *Handler {
	h := &Handler{auth: []byte("Bearer " + token), reset: func() {}, exec: defaultExec}
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

// precedence fija el orden de evaluación: auth, método/ruta exactos, JSON, m.
// Auth antes que ruta y JSON es supuesto (ENT-05) hasta que A4 lo mida.
func (h *Handler) precedence(r *http.Request) (int, []byte) {
	if subtle.ConstantTimeCompare([]byte(r.Header.Get("Authorization")), h.auth) != 1 {
		return http.StatusUnauthorized, respE001
	}
	switch route := r.Method + " " + rawPath(r); route {
	case "GET /health":
		return http.StatusOK, respOK
	case "POST /__reset":
		h.reset()
		return http.StatusOK, respOK
	case "POST /msg":
		return h.msg(r)
	}
	return http.StatusNotFound, respE404
}

func (h *Handler) msg(r *http.Request) (int, []byte) {
	raw, err := io.ReadAll(r.Body)
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
