package main

import (
	"fmt"

	"github.com/fullstackdanny1/prodmaster/internal/adapters/fake"
	"github.com/fullstackdanny1/prodmaster/internal/config"
	"github.com/fullstackdanny1/prodmaster/internal/core"
	"github.com/fullstackdanny1/prodmaster/internal/ui"
)

// plannedAdapters are the real adapters from spec 3 and the stage that brings
// each of them. Until then, selecting one leaves the port empty (nil) and a
// warning is shown.
var plannedAdapters = map[string]int{
	"taskwarrior": 2,
	"timewarrior": 2,
	"khal":        3,
	"harsh":       6,
}

// buildDeps creates the adapters named in the [adapters] section. This is the
// only place that knows which concrete type implements each port.
//
// The name "fake" selects the in-memory adapter, useful to try the interface
// without the tools installed (data is lost on exit).
func buildDeps(cfg config.Config) (ui.Deps, []string) {
	clock := core.SystemClock{}
	deps := ui.Deps{Clock: clock}
	var warnings []string

	// pick reports whether the fake adapter was chosen and records a warning
	// for names that are not available yet.
	pick := func(port, name string) bool {
		if name == "fake" {
			return true
		}
		if stage, ok := plannedAdapters[name]; ok {
			warnings = append(warnings, fmt.Sprintf("Adaptorul %s (%s) vine în etapa %d", name, port, stage))
		} else {
			warnings = append(warnings, fmt.Sprintf("Adaptor necunoscut pentru %s: %q", port, name))
		}
		return false
	}

	if pick("calendar", cfg.Adapters.Calendar) {
		deps.Calendar = fake.NewCalendar(cfg.Calendar.Writable...)
	}
	if pick("tasks", cfg.Adapters.Tasks) {
		deps.Tasks = fake.NewTasks(clock)
	}
	if pick("time", cfg.Adapters.Time) {
		deps.Time = fake.NewTimeTracker(clock)
	}
	if pick("habits", cfg.Adapters.Habits) {
		deps.Habits = fake.NewHabits()
	}
	// Notes, editor and notifier are not selectable in [adapters]; their real
	// implementations arrive in stages 5 and 6.
	return deps, warnings
}
