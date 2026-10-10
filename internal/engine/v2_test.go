package engine_test

import (
	"encoding/json"
	"math"
	"strconv"
	"testing"

	"github.com/game013/frontier-hackaton-10102026/internal/engine"
	"github.com/game013/frontier-hackaton-10102026/internal/protocol"
	"github.com/game013/frontier-hackaton-10102026/internal/state"
)

type harness struct {
	t     *testing.T
	e     *engine.Engine
	store engine.Store
}

func (h harness) expect(cmd string, status int, body string, args ...string) {
	h.t.Helper()
	got, b := h.e.Exec(protocol.Message{Cmd: cmd, Args: args})
	if got != status || string(b) != body {
		h.t.Fatalf("%s %v: got %d %s, want %d %s", cmd, args, got, b, status, body)
	}
}
func (h harness) op(n int, cmd string, args ...string) {
	h.t.Helper()
	h.expect(cmd, 200, `{"status":"recieved","operacionId":"`+state.FormatID("OP", int64(n))+`"}`, args...)
}
func (h harness) blocked(n int, from, to, amount string) {
	h.t.Helper()
	h.expect("TRANSFER", 423, `{"error":"E510","mensaje":"cuenta bloqueada","intentos":`+strconv.Itoa(n)+`}`, from, to, amount)
}
func (h harness) snapshot() *state.State {
	h.t.Helper()
	var s *state.State
	if err := h.store.Update(func(st *state.State) error { s = st.Clone(); return nil }); err != nil {
		h.t.Fatal(err)
	}
	return s
}
func newHarness(t *testing.T, store engine.Store, version string) harness {
	t.Helper()
	h := harness{t: t, e: testEngine(t, store, version), store: store}
	for i, name := range []string{"A", "B", "C"} {
		h.expect("ALTA", 201, `{"cuentaId":"`+state.FormatID("AC", int64(i+1))+`"}`, name)
	}
	return h
}
func bothStores(t *testing.T, fn func(*testing.T, engine.Store)) {
	t.Helper()
	t.Run("sqlite", func(t *testing.T) { fn(t, testStore(t)) })
	t.Run("memory", func(t *testing.T) { fn(t, engine.NewMemoryStore()) })
}

// CAM-V2-1: evidencia de A6 + bordes sintéticos de representación int64.
func TestV2BalanceFormatting(t *testing.T) {
	bothStores(t, func(t *testing.T, store engine.Store) {
		h := newHarness(t, store, "v2")
		for _, tc := range []struct {
			n    int64
			want string
		}{
			{0, "0.00"}, {1, "0.01"}, {5, "0.05"}, {99, "0.99"}, {100, "1.00"}, {12345, "123.45"},
			{-1, "-0.01"}, {-50, "-0.50"}, {-99, "-0.99"}, {-100, "-1.00"}, {-800, "-8.00"},
			{math.MaxInt64, "92233720368547758.07"}, {math.MinInt64, "-92233720368547758.08"},
		} {
			if err := store.Update(func(s *state.State) error { s.Accounts["AC-0001"].Balance = tc.n; return nil }); err != nil {
				t.Fatal(err)
			}
			h.expect("CONSULTA", 200, `{"cuenta_id":"AC-0001","saldo":"`+tc.want+`"}`, "AC-0001")
		}
	})
}

// CAM-V2-2 y v1 explícita: límites inclusivos, sin aplicar a depósitos.
func TestVersionedTransferLimits(t *testing.T) {
	for _, version := range []string{"v1", "v2"} {
		t.Run(version, func(t *testing.T) {
			bothStores(t, func(t *testing.T, store engine.Store) {
				h := newHarness(t, store, version)
				h.op(1, "DEPOSITO", "AC-0001", "9999999999")
				amounts := []string{"50000", "50001", "100000", "100001"}
				next := 2
				for _, amount := range amounts {
					n, _ := strconv.Atoi(amount)
					limit := 100000
					if version == "v2" {
						limit = 50000
					}
					if n > limit {
						h.expect("TRANSFER", 422, bodyE506, "AC-0001", "AC-0002", amount)
					} else {
						h.op(next, "TRANSFER", "AC-0001", "AC-0002", amount)
						next++
					}
				}
				if version == "v1" {
					// v1 nunca bloquea ni actualiza contadores aunque acumule cuatro fallos.
					for range 4 {
						h.expect("TRANSFER", 422, bodyE507, "AC-0003", "AC-0001", "1")
					}
					acc := h.snapshot().Accounts["AC-0003"]
					if acc.TransferFailures != 0 || acc.BlockedAttempts != 0 {
						t.Fatal("v2 se filtró a v1")
					}
				} else {
					h.blocked(1, "AC-0001", "AC-0002", "1")
				}
			})
		})
	}
	if _, err := engine.New(engine.NewMemoryStore(), "v9"); err == nil {
		t.Fatal("versión desconocida aceptada")
	}
}

// CAM-V2-3: tercer fallo normal, contador consecutivo, bloqueo por origen,
// no consumo de OP, ingreso/ANULA sin liberar y depósito/rebloqueo/reset.
func TestV2BlockingLifecycle(t *testing.T) {
	bothStores(t, func(t *testing.T, store engine.Store) {
		h := newHarness(t, store, "v2")
		h.op(1, "DEPOSITO", "AC-0001", "100000")
		for range 2 {
			h.expect("TRANSFER", 422, bodyE506, "AC-0001", "AC-0002", "50001")
		}
		h.op(2, "TRANSFER", "AC-0001", "AC-0002", "50000")
		if h.snapshot().Accounts["AC-0001"].TransferFailures != 0 {
			t.Fatal("éxito no reinicia racha")
		}
		h.op(3, "TRANSFER", "AC-0001", "AC-0002", "50000")
		h.expect("TRANSFER", 422, bodyE506, "AC-0001", "AC-0002", "50001")
		h.expect("TRANSFER", 422, bodyE507, "AC-0001", "AC-0002", "1")
		h.expect("TRANSFER", 422, bodyE506, "AC-0001", "AC-0002", "50001")
		h.blocked(1, "AC-0001", "AC-0002", "1")
		h.blocked(2, "AC-0001", "AC-0002", "50001")
		h.op(4, "DEPOSITO", "AC-0002", "1")            // otra cuenta no libera A
		h.op(5, "TRANSFER", "AC-0002", "AC-0001", "1") // ingreso no libera A
		h.expect("CONSULTA", 200, `{"cuenta_id":"AC-0001","saldo":"0.01"}`, "AC-0001")
		h.blocked(3, "AC-0001", "AC-0002", "1")
		h.expect("ANULA", 200, `{"ok":true,"anulada":"OP-0001"}`, "OP-0001")
		h.blocked(4, "AC-0001", "AC-0002", "1")
		h.expect("DEPOSITO", 400, bodyE303, "AC-0001", "0")
		h.blocked(5, "AC-0001", "AC-0002", "1")
		h.op(6, "DEPOSITO", "AC-0001", "1")
		acc := h.snapshot().Accounts["AC-0001"]
		if acc.TransferFailures != 0 || acc.BlockedAttempts != 0 {
			t.Fatal("depósito no reinicia ambos contadores")
		}
		for range 3 {
			h.expect("TRANSFER", 422, bodyE507, "AC-0001", "AC-0002", "1")
		}
		h.blocked(1, "AC-0001", "AC-0002", "1")
		if err := h.e.Reset(); err != nil {
			t.Fatal(err)
		}
		h.expect("CONSULTA", 404, bodyE401, "AC-0001")
		h.expect("ALTA", 201, `{"cuentaId":"AC-0001"}`, "A")
		h.op(1, "DEPOSITO", "AC-0001", "1")
	})
}

// Supuestos B7: errores anteriores a E510 no incrementan ni reinician racha,
// ni consumen intentos bloqueados. Depósito entre fallos también libera.
func TestV2BlockingPrecedenceAndNonCountingErrors(t *testing.T) {
	bothStores(t, func(t *testing.T, store engine.Store) {
		h := newHarness(t, store, "v2")
		earlyErrors := func() {
			h.expect("TRANSFER", 400, bodyE303, "AC-0001", "AC-0002", "0")
			h.expect("TRANSFER", 400, bodyE304, "AC-0001", "AC-0001", "1")
			h.expect("TRANSFER", 404, bodyE401, "AC-0001", "AC-0009", "1")
			h.expect("TRANSFER", 404, bodyE401, "AC-0009", "AC-0001", "1")
		}
		h.expect("TRANSFER", 422, bodyE507, "AC-0001", "AC-0002", "1")
		earlyErrors()
		if h.snapshot().Accounts["AC-0001"].TransferFailures != 1 {
			t.Fatal("errores anteriores cambiaron racha")
		}
		h.expect("TRANSFER", 422, bodyE507, "AC-0001", "AC-0002", "1")
		h.op(1, "DEPOSITO", "AC-0001", "1")
		h.expect("TRANSFER", 422, bodyE506, "AC-0001", "AC-0002", "50001")
		h.op(2, "TRANSFER", "AC-0001", "AC-0002", "1")
		for range 3 {
			h.expect("TRANSFER", 422, bodyE507, "AC-0001", "AC-0002", "1")
		}
		earlyErrors()
		h.blocked(1, "AC-0001", "AC-0002", "1")
		earlyErrors()
		h.blocked(2, "AC-0001", "AC-0002", "50001")
	})
}

func TestV2InternalFailureDoesNotUnlock(t *testing.T) {
	store := testStore(t)
	h := newHarness(t, store, "v2")
	if err := store.Update(func(s *state.State) error {
		acc := s.Accounts["AC-0001"]
		acc.Balance, acc.TransferFailures, acc.BlockedAttempts = math.MaxInt64, 3, 2
		return nil
	}); err != nil {
		t.Fatal(err)
	}
	h.expect("DEPOSITO", 500, `{"error":"E500","mensaje":"error interno"}`, "AC-0001", "1")
	h.blocked(3, "AC-0001", "AC-0002", "1")
	if h.snapshot().NextOperation != 1 {
		t.Fatal("error consumió OP")
	}
}

func TestV2ConcurrentBlockedAttempts(t *testing.T) {
	bothStores(t, func(t *testing.T, store engine.Store) {
		h := newHarness(t, store, "v2")
		for range 3 {
			h.expect("TRANSFER", 422, bodyE507, "AC-0001", "AC-0002", "1")
		}
		type result struct {
			status int
			body   []byte
		}
		done := make(chan result, 30)
		for range 30 {
			go func() {
				status, body := h.e.Exec(protocol.Message{Cmd: "TRANSFER", Args: a("AC-0001", "AC-0002", "1")})
				done <- result{status, body}
			}()
		}
		seen := map[int64]bool{}
		for range 30 {
			r := <-done
			var body struct {
				Error    string
				Attempts int64 `json:"intentos"`
			}
			if err := json.Unmarshal(r.body, &body); err != nil || r.status != 423 || body.Error != "E510" || body.Attempts < 1 || body.Attempts > 30 || seen[body.Attempts] {
				t.Fatalf("respuesta concurrente %d %s: %v", r.status, r.body, err)
			}
			seen[body.Attempts] = true
		}
		if acc := h.snapshot().Accounts["AC-0001"]; acc.TransferFailures != 3 || acc.BlockedAttempts != 30 {
			t.Fatalf("contadores %+v", acc)
		}
	})
}

// Mismo titular byte a byte: sin E506 (r1 log 4252, 4341, 4436). Otro titular,
// caja, espacio o forma Unicode distinta sí dan E506 (4247, 4418, 4423, 4437).
// E507 y el bloqueo siguen aplicando (4411, 4413, 4430).
func TestSameHolderSkipsTransferLimit(t *testing.T) {
	for _, version := range []string{"v1", "v2"} {
		t.Run(version, func(t *testing.T) {
			h := harness{t: t, e: testEngine(t, engine.NewMemoryStore(), version)}
			for i, name := range []string{"Ana", "Ana", "ana", "Ana ", "Irene Pen\u0303a", "Irene Peña"} {
				h.expect("ALTA", 201, `{"cuentaId":"`+state.FormatID("AC", int64(i+1))+`"}`, name)
			}
			h.expect("TRANSFER", 422, bodyE507, "AC-0001", "AC-0002", "9999999999")
			h.op(1, "DEPOSITO", "AC-0001", "9999999999")
			h.op(2, "DEPOSITO", "AC-0001", "9999999999")
			h.op(3, "TRANSFER", "AC-0001", "AC-0002", "9999999999")
			// Un éxito entre pares corta la racha v2 antes del tercer fallo.
			h.expect("TRANSFER", 422, bodyE506, "AC-0001", "AC-0003", "100001")
			h.expect("TRANSFER", 422, bodyE506, "AC-0001", "AC-0004", "100001")
			h.op(4, "TRANSFER", "AC-0001", "AC-0002", "1")
			h.expect("TRANSFER", 422, bodyE506, "AC-0001", "AC-0005", "100001")
			h.expect("TRANSFER", 422, bodyE506, "AC-0001", "AC-0006", "100001")
			h.op(5, "DEPOSITO", "AC-0006", "200000")
			h.op(6, "TRANSFER", "AC-0006", "AC-0005", "100") // distinto titular, bajo el límite
			h.expect("TRANSFER", 422, bodyE506, "AC-0006", "AC-0005", "100001")
		})
	}
}
