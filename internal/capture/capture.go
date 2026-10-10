// Package capture registra cada intercambio HTTP que recibe el reemplazo, sea
// cual sea su método, ruta o cuerpo, para reproducirlo después en local como
// semilla de pruebas. Va por fuera de todo el handler y nunca altera la respuesta.
package capture

import (
	"bytes"
	"encoding/base64"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"os"
	"strings"
	"sync"
	"time"
	"unicode/utf8"
)

const redacted = "${TEAM_TOKEN}"

// Record es una línea JSONL. Authorization se conserva con el token del
// equipo sustituido por ${TEAM_TOKEN}, para poder repetir el request exacto.
type Record struct {
	Kind       string              `json:"kind"`
	TS         string              `json:"ts"`
	Boot       string              `json:"boot"`
	N          int                 `json:"n"`
	Seq        int                 `json:"seq"`
	Version    string              `json:"version"`
	Method     string              `json:"method"`
	URI        string              `json:"uri"`
	Proto      string              `json:"proto"`
	Host       string              `json:"host"`
	RemoteAddr string              `json:"remote_addr"`
	Auth       string              `json:"auth"`
	Headers    map[string][]string `json:"headers"`
	BodyB64    string              `json:"body_b64"`
	Body       *string             `json:"body,omitempty"`
	BodyError  string              `json:"body_error,omitempty"`
	Redacted   bool                `json:"redacted,omitempty"`
	Status     int                 `json:"status"`
	RespB64    string              `json:"resp_b64"`
	Resp       *string             `json:"resp,omitempty"`
	DurationMS float64             `json:"duration_ms"`
	Panic      string              `json:"panic,omitempty"`
}

type Options struct {
	Token   string
	Version string
	Sinks   []io.Writer
}

type recorder struct {
	http.ResponseWriter
	status int
	body   bytes.Buffer
}

func (r *recorder) WriteHeader(code int) {
	if r.status == 0 {
		r.status = code
	}
	r.ResponseWriter.WriteHeader(code)
}

func (r *recorder) Write(b []byte) (int, error) {
	if r.status == 0 {
		r.status = http.StatusOK
	}
	r.body.Write(b)
	return r.ResponseWriter.Write(b)
}

// Middleware envuelve next. Un reset autenticado con 200 abre una secuencia
// nueva; lo anterior al primer reset queda en la secuencia 0.
func Middleware(next http.Handler, o Options) http.Handler {
	var mu sync.Mutex
	n, seq := 0, 0
	boot := time.Now().UTC().Format(time.RFC3339Nano)
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		start := time.Now()
		body, readErr := io.ReadAll(r.Body)
		r.Body = io.NopCloser(bytes.NewReader(body))
		rec := &recorder{ResponseWriter: w}
		var panicked any
		func() {
			defer func() {
				if panicked = recover(); panicked != nil && rec.status == 0 {
					rec.WriteHeader(http.StatusInternalServerError)
				}
			}()
			next.ServeHTTP(rec, r)
		}()

		auth := authLabel(r.Header, o.Token)
		mu.Lock()
		defer mu.Unlock()
		n++
		if r.Method == http.MethodPost && path(r.RequestURI) == "/__reset" && auth == "team" && rec.status == http.StatusOK {
			seq++
		}
		line := Record{
			Kind: "capture", TS: start.UTC().Format(time.RFC3339Nano), Boot: boot, N: n, Seq: seq, Version: o.Version,
			Method: r.Method, URI: r.RequestURI, Proto: r.Proto, Host: r.Host, RemoteAddr: r.RemoteAddr,
			Auth: auth, Headers: redactHeaders(r.Header, o.Token),
			Status: rec.status, DurationMS: float64(time.Since(start).Microseconds()) / 1000,
		}
		if readErr != nil {
			line.BodyError = readErr.Error()
		}
		if o.Token != "" && bytes.Contains(body, []byte(o.Token)) {
			body, line.Redacted = bytes.ReplaceAll(body, []byte(o.Token), []byte(redacted)), true
		}
		line.BodyB64, line.Body = encode(body)
		line.RespB64, line.Resp = encode(rec.body.Bytes())
		if panicked != nil {
			line.Panic = fmt.Sprint(panicked)
		}
		emit(o.Sinks, line)
	})
}

func emit(sinks []io.Writer, line Record) {
	b, err := json.Marshal(line)
	if err != nil {
		fmt.Fprintf(os.Stderr, "capture: %v\n", err)
		return
	}
	b = append(b, '\n')
	for _, s := range sinks {
		if _, err := s.Write(b); err != nil {
			fmt.Fprintf(os.Stderr, "capture: %v\n", err)
		}
	}
}

// encode devuelve base64 (fiel) y, si es UTF-8 válido, el texto legible.
func encode(b []byte) (string, *string) {
	enc := base64.StdEncoding.EncodeToString(b)
	if !utf8.Valid(b) {
		return enc, nil
	}
	s := string(b)
	return enc, &s
}

func authLabel(h http.Header, token string) string {
	v, ok := h["Authorization"]
	switch {
	case !ok:
		return "none"
	case len(v) == 1 && token != "" && v[0] == "Bearer "+token:
		return "team"
	}
	return "other"
}

func redactHeaders(h http.Header, token string) map[string][]string {
	out := make(map[string][]string, len(h))
	for k, vs := range h {
		cp := make([]string, len(vs))
		for i, v := range vs {
			if token != "" {
				v = strings.ReplaceAll(v, token, redacted)
			}
			cp[i] = v
		}
		out[k] = cp
	}
	return out
}

func path(uri string) string {
	p, _, _ := strings.Cut(uri, "?")
	return p
}

// FileSink abre (o crea) un JSONL en modo append y sincroniza cada línea a disco.
func FileSink(name string) (io.WriteCloser, error) {
	f, err := os.OpenFile(name, os.O_WRONLY|os.O_CREATE|os.O_APPEND, 0o600)
	if err != nil {
		return nil, err
	}
	return syncFile{f}, nil
}

type syncFile struct{ *os.File }

func (s syncFile) Write(b []byte) (int, error) {
	n, err := s.File.Write(b)
	if err == nil {
		err = s.File.Sync()
	}
	return n, err
}
