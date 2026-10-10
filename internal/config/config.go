// Package config lee el entorno una sola vez al arrancar. Un valor inválido
// impide arrancar: nunca se elige comportamiento por reloj ni por defecto oculto.
package config

import (
	"errors"
	"fmt"
)

// Versions son las reglas implementadas; la última es el valor por defecto.
var Versions = []string{"v1"}

type Config struct {
	Token       string
	Port        string
	Version     string
	CapturePath string
	Storage     string
	StatePath   string
}

func Load(getenv func(string) string) (Config, error) {
	c := Config{
		Token:       getenv("TEAM_TOKEN"),
		Port:        or(getenv("PORT"), "9900"),
		Version:     or(getenv("BEHAVIOR_VERSION"), Versions[len(Versions)-1]),
		CapturePath: or(getenv("CAPTURE_PATH"), "var/capture.jsonl"),
		Storage:     or(getenv("STORAGE"), "sqlite"),
		StatePath:   or(getenv("STATE_PATH"), "var/state.db"),
	}
	if c.Storage != "sqlite" && c.Storage != "memory" {
		return c, fmt.Errorf("STORAGE desconocido: %q", c.Storage)
	}
	if c.Token == "" {
		return c, errors.New("TEAM_TOKEN es obligatorio")
	}
	for _, v := range Versions {
		if c.Version == v {
			return c, nil
		}
	}
	return c, fmt.Errorf("BEHAVIOR_VERSION desconocida: %q", c.Version)
}

func or(v, def string) string {
	if v == "" {
		return def
	}
	return v
}
