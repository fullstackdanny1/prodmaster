package config

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

func write(t *testing.T, content string) string {
	t.Helper()
	p := filepath.Join(t.TempDir(), "config.toml")
	if err := os.WriteFile(p, []byte(content), 0o644); err != nil {
		t.Fatal(err)
	}
	return p
}

func TestMissingFileUsesDefaults(t *testing.T) {
	cfg, err := Load(filepath.Join(t.TempDir(), "nu-exista.toml"))
	if err != nil {
		t.Fatal(err)
	}
	if cfg.General.StartPage != "agenda" || cfg.General.RefreshSeconds != 60 || cfg.General.AgendaDays != 7 {
		t.Errorf("general = %+v", cfg.General)
	}
	if cfg.Palette.Default != "4" { // "blue"
		t.Errorf("default colour = %q", cfg.Palette.Default)
	}
	if len(cfg.Warnings) != 1 || !strings.Contains(cfg.Warnings[0], "lipsește") {
		t.Errorf("warnings = %v", cfg.Warnings)
	}
}

// The example file shipped with the repository (spec section 10) must load
// without warnings.
func TestSpecExample(t *testing.T) {
	cfg, err := Load("../../config.example.toml")
	if err != nil {
		t.Fatal(err)
	}
	if len(cfg.Warnings) != 0 {
		t.Errorf("warnings = %v", cfg.Warnings)
	}
	if got := cfg.Calendar.Projects["Curs Inteligență Artificială"]; got != "ia" {
		t.Errorf("calendar.projects = %v", cfg.Calendar.Projects)
	}
	if got := cfg.Palette.Color("ia"); got != "2" {
		t.Errorf("ia colour = %q", got)
	}
	if got := cfg.Palette.Color("proiect-y"); got != "#e5a50a" {
		t.Errorf("proiect-y colour = %q", got)
	}
	if got := cfg.Palette.Color("altceva"); got != "4" {
		t.Errorf("default colour = %q", got)
	}
	if len(cfg.Habits.Auto) != 1 || cfg.Habits.Auto[0].Min != 30*time.Minute {
		t.Errorf("habits.auto = %+v", cfg.Habits.Auto)
	}
	home, _ := os.UserHomeDir()
	if cfg.Notes.Dir != filepath.Join(home, "notite") {
		t.Errorf("notes dir = %q", cfg.Notes.Dir)
	}
}

func TestPartialFileKeepsDefaults(t *testing.T) {
	cfg, err := Load(write(t, "[general]\nagenda_days = 3\n"))
	if err != nil {
		t.Fatal(err)
	}
	if cfg.General.AgendaDays != 3 || cfg.General.RefreshSeconds != 60 || cfg.Adapters.Tasks != "taskwarrior" {
		t.Errorf("cfg = %+v", cfg)
	}
}

func TestInvalidValuesProduceWarnings(t *testing.T) {
	cfg, err := Load(write(t, `
[general]
start_page = "nicaieri"
refresh_seconds = 0

[colors]
default = "violet-ish"

[colors.projects]
ia = "999"
bd = "red"

[[habits.auto]]
habit = "Citit"
project = "citit"
min = "jumătate de oră"
`))
	if err != nil {
		t.Fatal(err)
	}
	if cfg.General.StartPage != "agenda" || cfg.General.RefreshSeconds != 60 {
		t.Errorf("fallbacks not applied: %+v", cfg.General)
	}
	if cfg.Palette.Default != "4" {
		t.Errorf("default colour fallback = %q", cfg.Palette.Default)
	}
	if got := cfg.Palette.Color("ia"); got != "4" {
		t.Errorf("invalid project colour should fall back to default, got %q", got)
	}
	if got := cfg.Palette.Color("bd"); got != "1" {
		t.Errorf("bd colour = %q", got)
	}
	if len(cfg.Habits.Auto) != 0 {
		t.Errorf("invalid habits.auto kept: %+v", cfg.Habits.Auto)
	}
	if len(cfg.Warnings) != 5 {
		t.Errorf("want 5 warnings, got %d: %v", len(cfg.Warnings), cfg.Warnings)
	}
}

func TestUnknownKeyWarns(t *testing.T) {
	cfg, err := Load(write(t, "[general]\nculoare_fundal = 1\n"))
	if err != nil {
		t.Fatal(err)
	}
	if len(cfg.Warnings) != 1 || !strings.Contains(cfg.Warnings[0], "culoare_fundal") {
		t.Errorf("warnings = %v", cfg.Warnings)
	}
}

func TestBrokenSyntaxIsAnError(t *testing.T) {
	if _, err := Load(write(t, "[general\n")); err == nil {
		t.Error("expected error")
	}
}
