package protocol

import "testing"

// Controles observados en v1 (spec INT-01, INT-05..07; informe A1). Cada caso
// cita un ID del log donde el original aceptó ese control (pasó de E202).
func TestControl(t *testing.T) {
	cases := []struct {
		base string
		want int
		ids  string
	}{
		{"ALTA;A", 62, "124"},
		{"ALTA;BZ", 97, "A1 bordes: 97, no 0"},
		{"ALTA;HD", 98, "A1 bordes: 98, no 1"},
		{"ALTA;Lucia", 82, "4"},
		// Reservados A1: 163, 165, 167, 169, 171, 173, 175, 177, 179.
		{"ALTA;Zoë", 90, "163"},
		{"ALTA;Á", 62, "165"},
		{"CONSULTA;AC-0042", 85, "167"},
		{"DEPOSITO;AC-0001;1234", 12, "169"},
		{"TRANSFER;AC-0002;AC-0001;6789", 10, "171"},
		{"ANULA;OP-0042", 46, "173"},
		{"alta;Iris", 21, "175"},
		{"CONSULTA;AC-00042", 35, "177"},
		{"ALTA;Q;R", 65, "179"},
		// Unicode filtrado antes de la caja, sin normalizar (INT-05).
		{"ALTA;Ána", 61, "139"},
		{"ALTA;Äna", 50, "142–144"},
		{"ALTA;ßa", 62, "149"},
		{"ALTA;ıa", 62, "151"},
		// Ceros como texto (INT-06, INT-07).
		{"CONSULTA;AC-0001", 14, "135"},
		{"CONSULTA;AC-00001", 61, "136"},
		{"DEPOSITO;AC-0001;7", 10, "222"},
		{"DEPOSITO;AC-0001;007", 70, "224"},
	}
	for _, c := range cases {
		if got := Control(c.base); got != c.want {
			t.Errorf("Control(%q) = %d, want %d (log %s)", c.base, got, c.want, c.ids)
		}
	}
}

func TestControlLongBaseDoesNotOverflow(t *testing.T) {
	long := make([]byte, 10000)
	for i := range long {
		long[i] = 'Z'
	}
	if got := Control(string(long)); got < 2 || got > 98 {
		t.Fatalf("Control fuera de 2..98: %d", got)
	}
}
