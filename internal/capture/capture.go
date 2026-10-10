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

// replayBody entrega al handler los bytes ya leídos y después el mismo error
// de lectura que dio el cuerpo original (EOF si no hubo error).
type replayBody struct {
	*bytes.Reader
	err error
}

func (b replayBody) Read(p []byte) (int, error) {
	n, err := b.Reader.Read(p)
	if err == io.EOF && b.err != nil {
		err = b.err
	}
	return n, err
}

func (replayBody) Close() error { return nil }

// Middleware envuelve next. Un reset autenticado con 200 abre una secuencia
// nueva; lo anterior al primer reset queda en la secuencia 0. N y seq se fijan
// a la llegada, así un request lento no cambia de secuencia por un reset paralelo.
// No ve lo que net/http rechaza antes del handler (request mal formado, 431).
func Middleware(next http.Handler, o Options) http.Handler {
	var mu sync.Mutex
	n, seq := 0, 0
	boot := time.Now().UTC().Format(time.RFC3339Nano)
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		start := time.Now()
		mu.Lock()
		n++
		line := Record{N: n, Seq: seq}
		mu.Unlock()
		body, readErr := io.ReadAll(r.Body)
		r.Body = replayBody{bytes.NewReader(body), readErr}
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

		line.Kind, line.TS, line.Boot, line.Version = "capture", start.UTC().Format(time.RFC3339Nano), boot, o.Version
		line.Method, line.URI, line.Proto, line.Host, line.RemoteAddr = r.Method, r.RequestURI, r.Proto, r.Host, r.RemoteAddr
		line.Auth, line.Headers = authLabel(r.Header, o.Token), redactHeaders(r.Header, o.Token)
		line.Status, line.DurationMS = rec.status, float64(time.Since(start).Microseconds())/1000
		if o.Token != "" && strings.Contains(line.URI, o.Token) {
			line.URI, line.Redacted = strings.ReplaceAll(line.URI, o.Token, redacted), true
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
		mu.Lock()
		defer mu.Unlock()
		if r.Method == http.MethodPost && path(r.RequestURI) == "/__reset" && line.Auth == "team" && rec.status == http.StatusOK {
			seq++
			line.Seq = seq
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

// authLabel usa el primer valor, igual que el handler (Header.Get).
func authLabel(h http.Header, token string) string {
	switch {
	case len(h.Values("Authorization")) == 0:
		return "none"
	case token != "" && h.Get("Authorization") == "Bearer "+token:
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
