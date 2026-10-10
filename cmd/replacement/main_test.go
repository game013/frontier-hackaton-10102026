package main

import (
	"bufio"
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"syscall"
	"testing"
	"time"

	"github.com/game013/frontier-hackaton-10102026/internal/protocol"
)

// Ejecuta la composición real en un proceso separado, sin compilar otro binario.
func TestReplacementProcess(t *testing.T) {
	if os.Getenv("B5_PROCESS_HELPER") != "1" {
		return
	}
	if err := run(); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
	os.Exit(0)
}

type process struct {
	cmd     *exec.Cmd
	done    chan error
	url     string
	stopped bool
}

func startProcess(t *testing.T, dir string) *process {
	t.Helper()
	return startVersionProcess(t, dir, "v1")
}

func startVersionProcess(t *testing.T, dir, version string) *process {
	t.Helper()
	exe, err := os.Executable()
	if err != nil {
		t.Fatal(err)
	}
	cmd := exec.Command(exe, "-test.run=^TestReplacementProcess$")
	// Entorno cerrado: nunca heredar tokens del operador ni ajustes del runtime.
	cmd.Env = []string{
		"B5_PROCESS_HELPER=1", "TEAM_TOKEN=b5-local-test", "PORT=0", "STORAGE=sqlite", "BEHAVIOR_VERSION=" + version,
		"STATE_PATH=" + filepath.Join(dir, "state.db"), "CAPTURE_PATH=" + filepath.Join(dir, "capture.jsonl"),
	}
	stderr, err := cmd.StderrPipe()
	if err != nil {
		t.Fatal(err)
	}
	cmd.Stdout = io.Discard
	if err := cmd.Start(); err != nil {
		t.Fatal(err)
	}
	p := &process{cmd: cmd, done: make(chan error, 1)}
	go func() { p.done <- cmd.Wait() }()
	ready := make(chan string, 1)
	go func() {
		scanner := bufio.NewScanner(stderr)
		for scanner.Scan() {
			line := scanner.Text()
			_, tail, ok := strings.Cut(line, "replacement escuchando en ")
			if ok {
				addr, _, _ := strings.Cut(tail, " ")
				ready <- addr
			}
		}
	}()
	t.Cleanup(func() {
		if !p.stopped {
			cmd.Process.Kill()
			<-p.done
		}
	})
	select {
	case addr := <-ready:
		i := strings.LastIndex(addr, ":")
		if i < 0 {
			t.Fatalf("dirección inesperada: %q", addr)
		}
		p.url = "http://127.0.0.1:" + addr[i+1:]
	case err := <-p.done:
		p.stopped = true
		t.Fatalf("proceso salió antes de escuchar: %v", err)
	case <-time.After(10 * time.Second):
		t.Fatal("proceso no quedó listo")
	}
	return p
}

func (p *process) stop(t *testing.T, sig os.Signal) {
	t.Helper()
	if err := p.cmd.Process.Signal(sig); err != nil {
		t.Fatal(err)
	}
	select {
	case err := <-p.done:
		p.stopped = true
		if sig != os.Kill && err != nil {
			t.Fatalf("shutdown: %v", err)
		}
	case <-time.After(10 * time.Second):
		t.Fatal("proceso no terminó")
	}
}

func message(t *testing.T, p *process, text string, status int, expected string) {
	t.Helper()
	path := "/msg"
	var body []byte
	if text == "RESET" {
		path = "/__reset"
	} else {
		control := protocol.Control(text)
		body, _ = json.Marshal(map[string]string{"m": fmt.Sprintf("%s;%02d", text, control)})
	}
	req, err := http.NewRequest("POST", p.url+path, bytes.NewReader(body))
	if err != nil {
		t.Fatal(err)
	}
	req.Header.Set("Authorization", "Bearer b5-local-test")
	client := &http.Client{Timeout: 5 * time.Second}
	resp, err := client.Do(req)
	if err != nil {
		t.Fatal(err)
	}
	defer resp.Body.Close()
	raw, err := io.ReadAll(resp.Body)
	if err != nil {
		t.Fatal(err)
	}
	if resp.StatusCode != status || string(raw) != expected {
		t.Fatalf("%s: got %d %q want %d %q", text, resp.StatusCode, raw, status, expected)
	}
}

func TestProcessRestartAndReset(t *testing.T) {
	dir := t.TempDir()
	p := startProcess(t, dir)
	message(t, p, "ALTA;A", 201, `{"cuentaId":"AC-0001"}`)
	message(t, p, "ALTA;B", 201, `{"cuentaId":"AC-0002"}`)
	message(t, p, "DEPOSITO;AC-0001;100", 200, `{"status":"recieved","operacionId":"OP-0001"}`)
	message(t, p, "TRANSFER;AC-0001;AC-0002;30", 200, `{"status":"recieved","operacionId":"OP-0002"}`)
	message(t, p, "ANULA;OP-0001", 200, `{"ok":true,"anulada":"OP-0001"}`)
	p.stop(t, os.Kill) // respuesta confirmada permanece incluso sin cierre limpio
	p = startProcess(t, dir)
	message(t, p, "CONSULTA;AC-0001", 200, `{"cuenta_id":"AC-0001","saldo":-30}`)
	message(t, p, "CONSULTA;AC-0002", 200, `{"cuenta_id":"AC-0002","saldo":30}`)
	message(t, p, "ANULA;OP-0001", 200, `{"ok":false,"motivo":"ya anulada"}`)
	message(t, p, "ANULA;OP-0002", 200, `{"ok":true,"anulada":"OP-0002"}`)
	message(t, p, "ALTA;C", 201, `{"cuentaId":"AC-0003"}`)
	message(t, p, "DEPOSITO;AC-0003;1", 200, `{"status":"recieved","operacionId":"OP-0003"}`)
	message(t, p, "RESET", 200, `{"ok":true}`)
	p.stop(t, syscall.SIGTERM)
	p = startProcess(t, dir)
	message(t, p, "CONSULTA;AC-0001", 404, `{"error":"E401","mensaje":"cuenta inexistente"}`)
	message(t, p, "ANULA;OP-0001", 404, `{"error":"E402","mensaje":"operación inexistente"}`)
	message(t, p, "ALTA;D", 201, `{"cuentaId":"AC-0001"}`)
	message(t, p, "DEPOSITO;AC-0001;1", 200, `{"status":"recieved","operacionId":"OP-0001"}`)
	p.stop(t, syscall.SIGTERM)
}
