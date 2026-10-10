package protocol

import (
	"encoding/json"
	"os"
	"reflect"
	"testing"
)

// logCase es una respuesta del original a un m, sin dependencia de estado:
// E103, E104, E201, E202, E301, E302 o pong. testdata/log-cases.json se extrajo
// de experimentos.jsonl (request_b64 y raw), deduplicado por m.
type logCase struct {
	IDs    []string `json:"ids"`
	M      string   `json:"m"`
	Status int      `json:"status"`
	Body   string   `json:"body"`
}

func TestParseLogCases(t *testing.T) {
	raw, err := os.ReadFile("testdata/log-cases.json")
	if err != nil {
		t.Fatal(err)
	}
	var cases []logCase
	if err := json.Unmarshal(raw, &cases); err != nil {
		t.Fatal(err)
	}
	if len(cases) == 0 {
		t.Fatal("fixture vacío")
	}
	for _, c := range cases {
		msg, perr := Parse(c.M)
		if c.Body == `{"pong":true}` {
			if perr != nil || msg.Cmd != "PING" {
				t.Errorf("log %v: Parse(%q) = %+v, %v; want PING", c.IDs, c.M, msg, perr)
			}
			continue
		}
		if perr == nil {
			t.Errorf("log %v: Parse(%q) = %+v; want %d %s", c.IDs, c.M, msg, c.Status, c.Body)
			continue
		}
		if perr.Status != c.Status || string(perr.Body) != c.Body {
			t.Errorf("log %v: Parse(%q) = %d %s; want %d %s", c.IDs, c.M, perr.Status, perr.Body, c.Status, c.Body)
		}
	}
}

// Mensajes que el original aceptó: el parser los entrega crudos al motor.
func TestParseValidMessages(t *testing.T) {
	cases := []struct {
		m    string
		cmd  string
		args []string
		ids  string
	}{
		{"ALTA;Lucia;82", "ALTA", []string{"Lucia"}, "4"},
		{"alta;Iris;21", "ALTA", []string{"Iris"}, "175"},
		{"CONSULTa;AC-0001;14", "CONSULTA", []string{"AC-0001"}, "spec CMD-CONSULTA"},
		{"DEPOSITO;AC-0001;007;70", "DEPOSITO", []string{"AC-0001", "007"}, "224 (E303 es del motor)"},
		{"TRANSFER;AC-0002;AC-0001;6789;10", "TRANSFER", []string{"AC-0002", "AC-0001", "6789"}, "171"},
		{"ANULA;OP-0042;46", "ANULA", []string{"OP-0042"}, "173"},
		{"ALTA; Lucia;82", "ALTA", []string{" Lucia"}, "969: nombre sin recortar"},
		{"PING;64\x00", "PING", nil, "964"},
	}
	for _, c := range cases {
		msg, perr := Parse(c.m)
		if perr != nil {
			t.Errorf("Parse(%q) = %d %s (log %s)", c.m, perr.Status, perr.Body, c.ids)
			continue
		}
		if msg.Cmd != c.cmd || !reflect.DeepEqual(msg.Args, c.args) {
			t.Errorf("Parse(%q) = %q %q; want %q %q (log %s)", c.m, msg.Cmd, msg.Args, c.cmd, c.args, c.ids)
		}
	}
}

// Supuestos sin medir (spec ERR-301): sugerencia con distancia de edición ≤ 2
// sin distinguir caja ASCII; gana la menor distancia y, en empate, el primero
// de la tabla de comandos.
func TestSuggestion(t *testing.T) {
	cases := []struct{ cmd, want string }{
		{"ALT", "ALTA"},
		{"ATLA", "ALTA"},
		{"AXXA", "ALTA"},
		{" ALTA", "ALTA"},
		{"alt", "ALTA"},
		{"PIN", "PING"},
		{"CONSULT", "CONSULTA"},
		{"TRANSFE", "TRANSFER"},
		{"ZZZ", ""},
		{"SALDOS", ""},
		{"ALTAXYZ", ""},   // distancia 3
		{"ANUA", "ANULA"}, // gana la menor distancia (1), no el orden de la tabla
		{"PITA", "PING"},  // empate PING/ALTA a distancia 2: gana el orden de la tabla
	}
	for _, c := range cases {
		if got := suggest(c.cmd); got != c.want {
			t.Errorf("suggest(%q) = %q, want %q", c.cmd, got, c.want)
		}
	}
}

func TestParseOrder(t *testing.T) {
	cases := []struct {
		m, code string
	}{
		{";", "E104"},             // 1305: comando vacío y control vacío
		{";54", "E104"},           // INT-09
		{"ZZZ;Lucia;5X", "E201"},  // E201 antes que E301
		{"ZZZ;Lucia;53", "E202"},  // E202 antes que E301 (orden de log 23-32; m sintético)
		{"ALTA;Q;R;66", "E202"},   // INT-03: integridad antes que aridad
		{"PING;5X;1", "E302"},     // PING no valida control pero sí aridad
		{"ALTA;Lucia;8٢", "E201"}, // dígito no ASCII
	}
	for _, c := range cases {
		_, perr := Parse(c.m)
		if perr == nil || perr.Code != c.code {
			t.Errorf("Parse(%q) = %+v; want %s", c.m, perr, c.code)
		}
	}
}
