package main

import (
	"strings"
	"testing"

	"github.com/fullstackdanny1/prodmaster/internal/config"
)

func TestRunRejectsBadArguments(t *testing.T) {
	for _, args := range [][]string{
		{"--page", "nicaieri"},
		{"altceva"},
		{"notify"}, // not implemented yet
	} {
		if code := run(args); code != 2 {
			t.Errorf("run(%v) = %d, want 2", args, code)
		}
	}
}

func TestBuildDepsFake(t *testing.T) {
	cfg := config.Default()
	cfg.Adapters = config.Adapters{Calendar: "fake", Tasks: "fake", Time: "fake", Habits: "fake"}
	deps, warnings := buildDeps(cfg)
	if len(warnings) != 0 {
		t.Errorf("warnings = %v", warnings)
	}
	if deps.Calendar == nil || deps.Tasks == nil || deps.Time == nil || deps.Habits == nil {
		t.Errorf("deps = %+v", deps)
	}
}

func TestBuildDepsPlannedAndUnknown(t *testing.T) {
	cfg := config.Default() // khal, taskwarrior, timewarrior, harsh
	cfg.Adapters.Habits = "loop"
	deps, warnings := buildDeps(cfg)
	if deps.Tasks != nil || deps.Time != nil {
		t.Error("planned adapters should leave the port empty")
	}
	if len(warnings) != 4 {
		t.Fatalf("warnings = %v", warnings)
	}
	if !strings.Contains(warnings[1], "etapa 2") || !strings.Contains(warnings[3], "necunoscut") {
		t.Errorf("warnings = %v", warnings)
	}
}
