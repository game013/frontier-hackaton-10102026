package protocol

import (
	"strconv"
	"strings"
)

// Message es un m que pasó forma, integridad, comando y aridad. Cmd es el
// nombre canónico en mayúsculas; Args son los segmentos tal como llegaron, sin
// recortar ni normalizar (los valida el motor: E303, E401…).
type Message struct {
	Cmd  string
	Args []string
}

// commands es la tabla de comandos conocidos y su aridad. El orden decide los
// empates de sugerencia (supuesto, ERR-301).
var commands = []struct {
	name  string
	arity int
}{
	{"PING", 0},
	{"ALTA", 1},
	{"CONSULTA", 1},
	{"DEPOSITO", 2},
	{"TRANSFER", 3},
	{"ANULA", 1},
}

// Parse aplica el orden medido (ERR-ORD): E103 → E104 → E201 → E202 →
// (E301 | E302). PING se salta E201 y E202 (INT-11).
func Parse(m string) (Message, *Error) {
	cut := strings.LastIndexByte(m, ';')
	if cut < 0 {
		return Message{}, errFaltaControl // INT-10
	}
	segs := strings.Split(m, ";")
	for _, s := range segs {
		if s == "" {
			return Message{}, errSegmentoVacio // INT-09
		}
	}
	name, args := segs[0], segs[1:len(segs)-1]
	known, arity := lookup(name)
	if known != "PING" {
		ctl := m[cut+1:]
		if !wellFormed(ctl) {
			return Message{}, errControlMalFormado // INT-02
		}
		// Se compara el texto canónico: `03` da E202 aunque Control sea 3 (INT-02).
		if ctl != strconv.Itoa(Control(m[:cut])) {
			return Message{}, errControlInvalido // INT-01
		}
	}
	if known == "" {
		if s := suggest(name); s != "" {
			return Message{}, errComandoSugerido(s)
		}
		return Message{}, errComando
	}
	if len(args) != arity {
		return Message{}, errAridad // INT-03
	}
	if len(args) == 0 {
		args = nil
	}
	return Message{Cmd: known, Args: args}, nil
}

// lookup reconoce el comando sin distinguir caja ASCII y sin recortar espacios
// (spec CMD-*, ` ALTA` → E301). Plegar solo ASCII es supuesto: evita que
// equivalencias Unicode (signo Kelvin = K) reconozcan comandos.
func lookup(name string) (string, int) {
	for _, c := range commands {
		if asciiUpper(name) == c.name {
			return c.name, c.arity
		}
	}
	return "", 0
}

// wellFormed: uno o dos dígitos ASCII (INT-02); `03` está bien formado.
func wellFormed(ctl string) bool {
	if len(ctl) < 1 || len(ctl) > 2 {
		return false
	}
	for i := 0; i < len(ctl); i++ {
		if ctl[i] < '0' || ctl[i] > '9' {
			return false
		}
	}
	return true
}

func asciiUpper(s string) string {
	b := []byte(s)
	for i, c := range b {
		if 'a' <= c && c <= 'z' {
			b[i] = c - 'a' + 'A'
		}
	}
	return string(b)
}

// suggest devuelve el comando conocido más cercano a name si está a distancia
// de edición ≤ 2 sin distinguir caja ASCII, o "" si ninguno lo está. Umbral,
// métrica y empates (gana el primero de commands) son supuestos compatibles
// con A4 log 967–968, 1307–1315; ERR-301.
func suggest(name string) string {
	up := []rune(asciiUpper(name))
	best, bestDist := "", 3
	for _, c := range commands {
		if d := levenshtein(up, []rune(c.name)); d < bestDist {
			best, bestDist = c.name, d
		}
	}
	return best
}

func levenshtein(a, b []rune) int {
	prev := make([]int, len(b)+1)
	cur := make([]int, len(b)+1)
	for j := range prev {
		prev[j] = j
	}
	for i := 1; i <= len(a); i++ {
		cur[0] = i
		for j := 1; j <= len(b); j++ {
			cost := 1
			if a[i-1] == b[j-1] {
				cost = 0
			}
			cur[j] = min(prev[j]+1, cur[j-1]+1, prev[j-1]+cost)
		}
		prev, cur = cur, prev
	}
	return prev[len(b)]
}
