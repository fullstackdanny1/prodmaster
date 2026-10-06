package fake

import (
	"testing"

	"github.com/fullstackdanny1/prodmaster/internal/core"
	"github.com/fullstackdanny1/prodmaster/internal/ports"
	"github.com/fullstackdanny1/prodmaster/internal/ports/contract"
)

// The fake adapters must pass the same contract tests as the real ones.

func TestTasksContract(t *testing.T) {
	contract.Tasks(t, func(t *testing.T, c *core.FixedClock) ports.Tasks { return NewTasks(c) })
}

func TestTimeTrackerContract(t *testing.T) {
	contract.TimeTracker(t, func(t *testing.T, c *core.FixedClock) ports.TimeTracker { return NewTimeTracker(c) })
}

func TestCalendarContract(t *testing.T) {
	contract.Calendar(t, func(t *testing.T) ports.Calendar { return NewCalendar("plan") }, "plan", "cursuri")
}

func TestHabitsContract(t *testing.T) {
	contract.Habits(t, func(t *testing.T) ports.Habits {
		return NewHabits(core.Habit{Name: "Citit", Group: "Minte", Frequency: core.Frequency{Times: 1, PeriodDays: 1}})
	}, "Citit")
}

func TestNotesContract(t *testing.T) {
	contract.Notes(t, func(t *testing.T) ports.Notes { return NewNotes(&core.FixedClock{T: contract.T0}) })
}

func TestNotesCreateFromTemplate(t *testing.T) {
	n := NewNotes(&core.FixedClock{T: contract.T0})
	n.Templates["proiecte"] = "# {{titlu}} ({{proiect}}) {{data}}\n"
	p, err := n.CreateFromTemplate("proiecte", "ia", map[string]string{"proiect": "ia"})
	if err != nil {
		t.Fatal(err)
	}
	c, _ := n.Read(p)
	if c != "# ia (ia) 2026-10-06\n" {
		t.Errorf("content = %q", c)
	}
	if _, err := n.CreateFromTemplate("proiecte", "ia", nil); err == nil {
		t.Error("creating an existing note should fail")
	}
}
