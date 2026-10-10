// Package differential reproduce secuencias grabadas del original contra el
// reemplazo y compara status y bytes exactos del cuerpo. Nunca contacta al
// original: lee los registros de evidencia que escribe tools/explorer/bb.py.
//
// Una suite por versión (<version>.json) lista los archivos de evidencia y los
// patrones de seq que entran; pending-<version>.txt lista, por secuencia, los
// pasos que el reemplazo todavía no reproduce. Formato y uso: README.md.
package differential

import (
	"bufio"
	"bytes"
	"encoding/base64"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"os"
	"path"
	"path/filepath"
	"reflect"
	"sort"
	"strconv"
	"strings"
)

// Suite es <version>.json. Las rutas de Sources son relativas a la raíz del repo.
type Suite struct {
	Sources []Source `json:"sources"`
}

type Source struct {
	File string   `json:"file"`
	Seqs []string `json:"seqs"` // patrones de path.Match sobre seq
}

// record son los campos de un registro de evidencia que el arnés necesita.
// request_b64 y response_b64 se leen crudos para distinguir clave ausente
// (registro sin bytes, inválido) de null (request sin cuerpo).
type record struct {
	ID             int             `json:"id"`
	Seq            string          `json:"seq"`
	Method         string          `json:"method"`
	Path           string          `json:"path"`
	Auth           string          `json:"auth"`
	ContentType    *string         `json:"content_type"`
	RequestB64     json.RawMessage `json:"request_b64"`
	ResponseB64    json.RawMessage `json:"response_b64"`
	Status         int             `json:"status"`
	Outcome        string          `json:"outcome"`
	Infrastructure string          `json:"infrastructure"`
}

// Step es un intercambio listo para reproducir.
type Step struct {
	ID          int
	Method      string
	Path        string
	Auth        string
	ContentType string
	Body        []byte // nil: sin cuerpo
	Status      int
	Response    []byte
}

type Sequence struct {
	Name  string
	Steps []Step
}

// LoadSuite lee la suite y devuelve sus secuencias en orden de aparición.
// Cualquier secuencia que no se pueda reproducir con fidelidad es un error:
// un corpus inválido nunca se salta en silencio.
func LoadSuite(root, file string) ([]Sequence, error) {
	raw, err := os.ReadFile(file)
	if err != nil {
		return nil, err
	}
	var s Suite
	dec := json.NewDecoder(bytes.NewReader(raw))
	dec.DisallowUnknownFields()
	if err := dec.Decode(&s); err != nil {
		return nil, fmt.Errorf("%s: %w", file, err)
	}
	var out []Sequence
	seen := map[string]bool{}
	for _, src := range s.Sources {
		seqs, err := loadSource(filepath.Join(root, src.File), src.Seqs)
		if err != nil {
			return nil, err
		}
		if len(seqs) == 0 {
			return nil, fmt.Errorf("%s: ninguna secuencia coincide con %q", src.File, src.Seqs)
		}
		for _, q := range seqs {
			if seen[q.Name] {
				return nil, fmt.Errorf("secuencia %q repetida en la suite", q.Name)
			}
			seen[q.Name] = true
			out = append(out, q)
		}
	}
	return out, nil
}

func loadSource(file string, patterns []string) ([]Sequence, error) {
	f, err := os.Open(file)
	if err != nil {
		return nil, err
	}
	defer f.Close()
	var order []string
	bySeq := map[string][]record{}
	sc := bufio.NewScanner(f)
	sc.Buffer(make([]byte, 1<<20), 1<<24)
	for line := 1; sc.Scan(); line++ {
		if len(bytes.TrimSpace(sc.Bytes())) == 0 {
			continue
		}
		var r record
		if err := json.Unmarshal(sc.Bytes(), &r); err != nil {
			return nil, fmt.Errorf("%s:%d: %w", file, line, err)
		}
		ok, err := matchAny(patterns, r.Seq)
		if err != nil {
			return nil, err
		}
		if !ok {
			continue
		}
		if _, known := bySeq[r.Seq]; !known {
			order = append(order, r.Seq)
		}
		bySeq[r.Seq] = append(bySeq[r.Seq], r)
	}
	if err := sc.Err(); err != nil {
		return nil, fmt.Errorf("%s: %w", file, err)
	}
	out := make([]Sequence, 0, len(order))
	for _, name := range order {
		q, err := toSequence(name, bySeq[name])
		if err != nil {
			return nil, fmt.Errorf("%s: %w", file, err)
		}
		out = append(out, q)
	}
	return out, nil
}

func matchAny(patterns []string, seq string) (bool, error) {
	for _, p := range patterns {
		ok, err := path.Match(p, seq)
		if err != nil {
			return false, fmt.Errorf("patrón %q: %w", p, err)
		}
		if ok {
			return true, nil
		}
	}
	return false, nil
}

// toSequence descarta respuestas de infraestructura (rate limit: bb.py
// reintenta) y rechaza la secuencia si algún intento quedó sin respuesta, si
// faltan bytes o si no empieza con un reset autenticado.
func toSequence(name string, recs []record) (Sequence, error) {
	q := Sequence{Name: name}
	for _, r := range recs {
		if r.Infrastructure != "" || r.Outcome == "infrastructure" {
			continue
		}
		if r.Outcome != "" && r.Outcome != "completed" {
			return q, fmt.Errorf("%s: id %d con outcome %q: secuencia incompleta", name, r.ID, r.Outcome)
		}
		st, err := toStep(r)
		if err != nil {
			return q, fmt.Errorf("%s: id %d: %w", name, r.ID, err)
		}
		q.Steps = append(q.Steps, st)
	}
	if len(q.Steps) == 0 {
		return q, fmt.Errorf("%s: sin pasos", name)
	}
	if first := q.Steps[0]; first.Method != http.MethodPost || first.Path != "/__reset" || first.Auth != "valid" {
		return q, fmt.Errorf("%s: no empieza con POST /__reset autenticado", name)
	}
	return q, nil
}

func toStep(r record) (Step, error) {
	if r.RequestB64 == nil || r.ResponseB64 == nil {
		return Step{}, fmt.Errorf("sin request_b64/response_b64: el registro no tiene bytes")
	}
	if !knownAuth[r.Auth] {
		return Step{}, fmt.Errorf("auth desconocido %q", r.Auth)
	}
	body, err := decodeB64(r.RequestB64)
	if err != nil {
		return Step{}, fmt.Errorf("request_b64: %w", err)
	}
	resp, err := decodeB64(r.ResponseB64)
	if err != nil || resp == nil {
		return Step{}, fmt.Errorf("response_b64 inválido o null")
	}
	st := Step{ID: r.ID, Method: r.Method, Path: r.Path, Auth: r.Auth, Body: body,
		Status: r.Status, Response: resp}
	// Igual que bb.py: con cuerpo, Content-Type explícito o application/json.
	if body != nil {
		st.ContentType = "application/json"
		if r.ContentType != nil {
			st.ContentType = *r.ContentType
		}
	}
	return st, nil
}

// decodeB64 devuelve nil para null y un slice vacío no nil para "".
func decodeB64(raw json.RawMessage) ([]byte, error) {
	var s *string
	if err := json.Unmarshal(raw, &s); err != nil {
		return nil, err
	}
	if s == nil {
		return nil, nil
	}
	b, err := base64.StdEncoding.DecodeString(*s)
	if b == nil {
		b = []byte{}
	}
	return b, err
}

// Variantes de AUTH_VARIANTS en bb.py; "valid" usa el token del reemplazo.
var knownAuth = map[string]bool{"valid": true, "none": true, "empty": true, "invalid": true, "scheme": true,
	"lower": true, "spaces": true, "bare": true}

func authHeader(label, token string) (string, bool) {
	switch label {
	case "valid":
		return "Bearer " + token, true
	case "empty":
		return "Bearer ", true
	case "invalid":
		return "Bearer token-invalido-0000", true
	case "scheme":
		return "Basic " + token, true
	case "lower":
		return "bearer " + token, true
	case "spaces":
		return "Bearer  " + token, true
	case "bare":
		return token, true
	}
	return "", false
}

// Mismatch describe un paso cuya respuesta no coincide con la grabada.
type Mismatch struct {
	Index  int // posición del paso (0 = reset)
	Step   Step
	Status int
	Body   []byte
}

func (m Mismatch) Error() string {
	equiv := "no"
	if jsonEqual(m.Body, m.Step.Response) {
		equiv = "sí"
	}
	return fmt.Sprintf("paso %d (id %d) %s %s auth=%s cuerpo=%q\n  esperado %d %q\n  obtenido %d %q\n  JSON equivalente: %s",
		m.Index, m.Step.ID, m.Step.Method, m.Step.Path, m.Step.Auth, m.Step.Body,
		m.Step.Status, m.Step.Response, m.Status, m.Body, equiv)
}

// Replay ejecuta la secuencia contra baseURL en orden y devuelve todos los
// pasos que no coinciden. err solo indica un fallo de transporte (incluido
// superar el timeout del cliente).
func Replay(client *http.Client, baseURL, token string, q Sequence) ([]Mismatch, error) {
	var out []Mismatch
	for i, st := range q.Steps {
		var body io.Reader
		if st.Body != nil {
			body = bytes.NewReader(st.Body)
		}
		req, err := http.NewRequest(st.Method, baseURL+st.Path, body)
		if err != nil {
			return nil, fmt.Errorf("%s paso %d: %w", q.Name, i, err)
		}
		if st.ContentType != "" {
			req.Header.Set("Content-Type", st.ContentType)
		}
		if v, ok := authHeader(st.Auth, token); ok {
			req.Header.Set("Authorization", v)
		}
		resp, err := client.Do(req)
		if err != nil {
			return nil, fmt.Errorf("%s paso %d: %w", q.Name, i, err)
		}
		got, err := io.ReadAll(resp.Body)
		resp.Body.Close()
		if err != nil {
			return nil, fmt.Errorf("%s paso %d: %w", q.Name, i, err)
		}
		if resp.StatusCode != st.Status || !bytes.Equal(got, st.Response) {
			out = append(out, Mismatch{Index: i, Step: st, Status: resp.StatusCode, Body: got})
		}
	}
	return out, nil
}

// jsonEqual compara como el evaluador: orden de claves libre, arrays en orden,
// números por su texto (sin pasar por float).
func jsonEqual(a, b []byte) bool {
	va, ok := decodeJSON(a)
	if !ok {
		return false
	}
	vb, ok := decodeJSON(b)
	return ok && reflect.DeepEqual(va, vb)
}

func decodeJSON(b []byte) (any, bool) {
	dec := json.NewDecoder(bytes.NewReader(b))
	dec.UseNumber()
	var v any
	if dec.Decode(&v) != nil || dec.More() {
		return nil, false
	}
	return v, true
}

// Pending son, por secuencia, los pasos que todavía pueden diferir.
type Pending map[string]map[int]bool

// LoadPending lee líneas "<seq> <pasos>", con pasos como 1,3-17 (posición en
// la secuencia; 0 es el reset). # comenta. Archivo ausente = vacío.
func LoadPending(file string) (Pending, error) {
	raw, err := os.ReadFile(file)
	if os.IsNotExist(err) {
		return Pending{}, nil
	}
	if err != nil {
		return nil, err
	}
	out := Pending{}
	for n, line := range strings.Split(string(raw), "\n") {
		line, _, _ = strings.Cut(line, "#")
		fields := strings.Fields(line)
		if len(fields) == 0 {
			continue
		}
		if len(fields) != 2 {
			return nil, fmt.Errorf("%s:%d: se espera \"<seq> <pasos>\"", file, n+1)
		}
		if _, dup := out[fields[0]]; dup {
			return nil, fmt.Errorf("%s:%d: %q repetida", file, n+1, fields[0])
		}
		steps, err := parseSteps(fields[1])
		if err != nil {
			return nil, fmt.Errorf("%s:%d: %w", file, n+1, err)
		}
		out[fields[0]] = steps
	}
	return out, nil
}

func parseSteps(s string) (map[int]bool, error) {
	out := map[int]bool{}
	for _, part := range strings.Split(s, ",") {
		lo, hi, isRange := strings.Cut(part, "-")
		a, err := strconv.Atoi(lo)
		b := a
		if err == nil && isRange {
			b, err = strconv.Atoi(hi)
		}
		if err != nil || a < 0 || b < a {
			return nil, fmt.Errorf("pasos inválidos %q", part)
		}
		for i := a; i <= b; i++ {
			out[i] = true
		}
	}
	return out, nil
}

// FormatSteps es la inversa de parseSteps, con rangos compactos y ordenados.
func FormatSteps(steps map[int]bool) string {
	idx := make([]int, 0, len(steps))
	for i := range steps {
		idx = append(idx, i)
	}
	sort.Ints(idx)
	var parts []string
	for i := 0; i < len(idx); {
		j := i
		for j+1 < len(idx) && idx[j+1] == idx[j]+1 {
			j++
		}
		if i == j {
			parts = append(parts, strconv.Itoa(idx[i]))
		} else {
			parts = append(parts, fmt.Sprintf("%d-%d", idx[i], idx[j]))
		}
		i = j + 1
	}
	return strings.Join(parts, ",")
}

const pendingHeader = `# Pasos que el reemplazo todavía no reproduce, por secuencia de la suite.
# Formato: <seq> <pasos> (posición en la secuencia; 0 es el reset).
# TestCorpus falla si difiere un paso fuera de la lista (regresión) o si uno de
# la lista ya coincide. Regenerar con -update-pending y revisar el diff.
`

// WritePending escribe las secuencias en el orden de la suite.
func WritePending(file string, seqs []Sequence, p Pending) error {
	var b strings.Builder
	b.WriteString(pendingHeader)
	for _, q := range seqs {
		if len(p[q.Name]) > 0 {
			fmt.Fprintf(&b, "%s %s\n", q.Name, FormatSteps(p[q.Name]))
		}
	}
	return os.WriteFile(file, []byte(b.String()), 0o644)
}
