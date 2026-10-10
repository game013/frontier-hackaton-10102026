// Package config lee el entorno una sola vez al arrancar. Un valor inválido
// impide arrancar: nunca se elige comportamiento por reloj ni por defecto oculto.
package config

import (
	"errors"
	"fmt"
)

// Versions son las reglas implementadas; la última es el valor por defecto.
var Versions = []string{"v1", "v2"}

// Storage selecciona el adaptador; los valores desconocidos se rechazan al arrancar.
type Storage string

const (
	StorageSQLite Storage = "sqlite"
	StorageMemory Storage = "memory"
)

type Config struct {
	Token       string
	Port        string
	Version     string
	CapturePath string
	Storage     Storage
	StatePath   string
}

func Load(getenv func(string) string) (Config, error) {
	c := Config{
		Token:       getenv("TEAM_TOKEN"),
		Port:        or(getenv("PORT"), "9900"),
		Version:     or(getenv("BEHAVIOR_VERSION"), Versions[len(Versions)-1]),
		CapturePath: or(getenv("CAPTURE_PATH"), "var/capture.jsonl"),
		Storage:     Storage(or(getenv("STORAGE"), string(StorageSQLite))),
		StatePath:   or(getenv("STATE_PATH"), "var/state.db"),
	}
	if c.Storage != StorageSQLite && c.Storage != StorageMemory {
		return c, fmt.Errorf("STORAGE desconocido: %q", c.Storage)
	}
	if c.Token == "" {
		return c, errors.New("TEAM_TOKEN es obligatorio")
	}
	var err error
	c.Version, err = ResolveVersion(c.Version)
	return c, err
}

// ResolveVersion también valida Config construidos sin Load. El valor vacío
// selecciona la última versión implementada; nunca se consulta el reloj.
func ResolveVersion(version string) (string, error) {
	version = or(version, Versions[len(Versions)-1])
	for _, v := range Versions {
		if version == v {
			return version, nil
		}
	}
	return "", fmt.Errorf("BEHAVIOR_VERSION desconocida: %q", version)
}

func or(v, def string) string {
	if v == "" {
		return def
	}
	return v
}
