package config

import "testing"

func env(m map[string]string) func(string) string { return func(k string) string { return m[k] } }

func TestDefaults(t *testing.T) {
	c, err := Load(env(map[string]string{"TEAM_TOKEN": "t"}))
	if err != nil {
		t.Fatal(err)
	}
	if c.Token != "t" || c.Port != "9900" || c.Version != "v1" || c.CapturePath != "var/capture.jsonl" {
		t.Fatalf("defaults: %+v", c)
	}
}

func TestOverrides(t *testing.T) {
	c, err := Load(env(map[string]string{"TEAM_TOKEN": "t", "PORT": "8123", "BEHAVIOR_VERSION": "v1", "CAPTURE_PATH": "/data/c.jsonl"}))
	if err != nil || c.Port != "8123" || c.CapturePath != "/data/c.jsonl" {
		t.Fatalf("%+v %v", c, err)
	}
}

func TestRefusesToStart(t *testing.T) {
	for name, e := range map[string]map[string]string{
		"sin_token":           {},
		"version_desconocida": {"TEAM_TOKEN": "t", "BEHAVIOR_VERSION": "v9"},
	} {
		if _, err := Load(env(e)); err == nil {
			t.Errorf("%s: debía fallar", name)
		}
	}
}
