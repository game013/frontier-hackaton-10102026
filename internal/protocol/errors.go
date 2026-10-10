package protocol

import "net/http"

// Error es una respuesta de error del original: status y cuerpo exactos, sin
// newline final (spec, sección 5). Code permite a los llamadores y pruebas
// razonar sobre el error sin comparar bytes.
type Error struct {
	Code   string
	Status int
	Body   []byte
}

func (e *Error) Error() string { return e.Code }

func newError(code, body string) *Error {
	return &Error{Code: code, Status: http.StatusBadRequest, Body: []byte(body)}
}

var (
	errFaltaControl      = newError("E103", `{"error":"E103","mensaje":"falta control"}`)
	errSegmentoVacio     = newError("E104", `{"error":"E104","mensaje":"segmento vacío"}`)
	errControlMalFormado = newError("E201", `{"error":"E201","mensaje":"control mal formado"}`)
	errControlInvalido   = newError("E202", `{"error":"E202","mensaje":"control inválido"}`)
	errAridad            = newError("E302", `{"error":"E302","mensaje":"aridad inválida"}`)
	errComando           = newError("E301", `{"error":"E301","mensaje":"comando desconocido "}`)
)

// errComandoSugerido es E301 con la clave sugerencia (ERR-301). Los nombres de
// comando son ASCII en mayúsculas: no necesitan escape JSON.
func errComandoSugerido(cmd string) *Error {
	return newError("E301", `{"error":"E301","mensaje":"comando desconocido ","sugerencia":"`+cmd+`"}`)
}
