package main

import (
	"os"
	"syscall"
	"testing"
)

func TestV2ProcessBlockingRestartAndVersionRollback(t *testing.T) {
	dir := t.TempDir()
	p := startVersionProcess(t, dir, "") // default real del runtime: v2
	message(t, p, "ALTA;A", 201, `{"cuentaId":"AC-0001"}`)
	message(t, p, "ALTA;B", 201, `{"cuentaId":"AC-0002"}`)
	message(t, p, "CONSULTA;AC-0001", 200, `{"cuenta_id":"AC-0001","saldo":"0.00"}`)
	for range 2 {
		message(t, p, "TRANSFER;AC-0001;AC-0002;1", 422, `{"error":"E507","mensaje":"saldo insuficiente"}`)
	}
	p.stop(t, os.Kill)
	p = startVersionProcess(t, dir, "v2")
	// La racha parcial también sobrevive, no solo una cuenta ya bloqueada.
	message(t, p, "TRANSFER;AC-0001;AC-0002;50001", 422, `{"error":"E506","mensaje":"límite excedido"}`)
	message(t, p, "TRANSFER;AC-0001;AC-0002;1", 423, `{"error":"E510","mensaje":"cuenta bloqueada","intentos":1}`)
	p.stop(t, os.Kill)
	p = startVersionProcess(t, dir, "v1")
	// El mismo binario/esquema ignora (pero conserva) los contadores en v1.
	message(t, p, "CONSULTA;AC-0001", 200, `{"cuenta_id":"AC-0001","saldo":0}`)
	message(t, p, "TRANSFER;AC-0001;AC-0002;1", 422, `{"error":"E507","mensaje":"saldo insuficiente"}`)
	p.stop(t, syscall.SIGTERM)
	p = startVersionProcess(t, dir, "v2")
	message(t, p, "TRANSFER;AC-0001;AC-0002;1", 423, `{"error":"E510","mensaje":"cuenta bloqueada","intentos":2}`)
	message(t, p, "DEPOSITO;AC-0001;100", 200, `{"status":"recieved","operacionId":"OP-0001"}`)
	p.stop(t, os.Kill)
	p = startVersionProcess(t, dir, "v2")
	message(t, p, "TRANSFER;AC-0001;AC-0002;1", 200, `{"status":"recieved","operacionId":"OP-0002"}`)
	message(t, p, "CONSULTA;AC-0001", 200, `{"cuenta_id":"AC-0001","saldo":"0.99"}`)
	for range 3 {
		message(t, p, "TRANSFER;AC-0001;AC-0002;50001", 422, `{"error":"E506","mensaje":"límite excedido"}`)
	}
	message(t, p, "TRANSFER;AC-0001;AC-0002;1", 423, `{"error":"E510","mensaje":"cuenta bloqueada","intentos":1}`)
	message(t, p, "RESET", 200, `{"ok":true}`)
	p.stop(t, os.Kill)
	p = startVersionProcess(t, dir, "v2")
	message(t, p, "ALTA;A", 201, `{"cuentaId":"AC-0001"}`)
	message(t, p, "ALTA;B", 201, `{"cuentaId":"AC-0002"}`)
	message(t, p, "TRANSFER;AC-0001;AC-0002;1", 422, `{"error":"E507","mensaje":"saldo insuficiente"}`)
	message(t, p, "DEPOSITO;AC-0001;1", 200, `{"status":"recieved","operacionId":"OP-0001"}`)
	p.stop(t, syscall.SIGTERM)
}
