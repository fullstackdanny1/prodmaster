// Package contract holds the contract tests of the ports (spec 12).
//
// A contract test describes the behaviour every implementation of an interface
// must have, independently of the tool behind it. Each adapter's test file
// calls the matching function with a factory that builds a fresh, empty
// instance:
//
//	func TestContract(t *testing.T) {
//	    contract.Tasks(t, func(t *testing.T, c *core.FixedClock) ports.Tasks { ... })
//	}
//
// The fake adapters run them now; the real adapters (stage 2 onwards) must run
// the same functions against the real tools in temporary directories.
package contract

import (
	"slices"
	"testing"
	"time"

	"github.com/fullstackdanny1/prodmaster/internal/core"
	"github.com/fullstackdanny1/prodmaster/internal/ports"
)

// T0 is the instant the contract tests start from: Tuesday 6 Oct 2026, 09:00.
var T0 = time.Date(2026, 10, 6, 9, 0, 0, 0, time.Local)

func findTask(tasks []core.Task, uuid string) (core.Task, bool) {
	i := slices.IndexFunc(tasks, func(t core.Task) bool { return t.UUID == uuid })
	if i < 0 {
		return core.Task{}, false
	}
	return tasks[i], true
}

// Tasks checks an implementation of ports.Tasks.
func Tasks(t *testing.T, newTasks func(t *testing.T, clock *core.FixedClock) ports.Tasks) {
	setup := func(t *testing.T) ports.Tasks {
		return newTasks(t, &core.FixedClock{T: T0})
	}
	mustAdd := func(t *testing.T, s ports.Tasks, raw string) core.Task {
		t.Helper()
		task, err := s.Add(raw)
		if err != nil {
			t.Fatalf("Add(%q): %v", raw, err)
		}
		return task
	}
	pending := func(t *testing.T, s ports.Tasks) []core.Task {
		t.Helper()
		l, err := s.List(core.TaskFilter{Status: core.StatusPending})
		if err != nil {
			t.Fatalf("List: %v", err)
		}
		return l
	}

	t.Run("add returns a uuid and the task is listed", func(t *testing.T) {
		s := setup(t)
		task := mustAdd(t, s, "Tema 3 project:ia")
		if task.UUID == "" {
			t.Fatal("empty UUID")
		}
		got, ok := findTask(pending(t, s), task.UUID)
		if !ok {
			t.Fatal("task not listed as pending")
		}
		if got.Description != "Tema 3" || got.Project != "ia" {
			t.Errorf("got description %q project %q", got.Description, got.Project)
		}
	})

	t.Run("filter by project", func(t *testing.T) {
		s := setup(t)
		mustAdd(t, s, "A project:ia")
		b := mustAdd(t, s, "B project:bd")
		l, err := s.List(core.TaskFilter{Project: "bd"})
		if err != nil {
			t.Fatal(err)
		}
		if len(l) != 1 || l[0].UUID != b.UUID {
			t.Errorf("got %+v", l)
		}
	})

	t.Run("objective tag sets the kind", func(t *testing.T) {
		s := setup(t)
		o := mustAdd(t, s, "Găsește un job +obiectiv")
		got, _ := findTask(pending(t, s), o.UUID)
		if got.Kind != core.KindObjective {
			t.Errorf("kind = %v, want objective", got.Kind)
		}
	})

	t.Run("modify keeps the description when only attributes change", func(t *testing.T) {
		s := setup(t)
		task := mustAdd(t, s, "Tema 3 project:ia")
		if err := s.Modify(task.UUID, "project:bd"); err != nil {
			t.Fatal(err)
		}
		got, _ := findTask(pending(t, s), task.UUID)
		if got.Project != "bd" || got.Description != "Tema 3" {
			t.Errorf("got %+v", got)
		}
	})

	t.Run("complete and delete remove the task from pending", func(t *testing.T) {
		s := setup(t)
		a := mustAdd(t, s, "A")
		b := mustAdd(t, s, "B")
		if err := s.Complete(a.UUID); err != nil {
			t.Fatal(err)
		}
		if err := s.Delete(b.UUID); err != nil {
			t.Fatal(err)
		}
		if l := pending(t, s); len(l) != 0 {
			t.Errorf("still pending: %+v", l)
		}
		done, _ := s.List(core.TaskFilter{Status: core.StatusCompleted})
		if _, ok := findTask(done, a.UUID); !ok {
			t.Error("completed task not listed as completed")
		}
	})

	t.Run("unknown uuid is an error", func(t *testing.T) {
		s := setup(t)
		if err := s.Complete("00000000-0000-0000-0000-000000000000"); err == nil {
			t.Error("expected error")
		}
	})

	t.Run("subtask is linked to its parent", func(t *testing.T) {
		s := setup(t)
		p := mustAdd(t, s, "Părinte project:y")
		c, err := s.AddSubtask(p.UUID, "Copil project:y")
		if err != nil {
			t.Fatal(err)
		}
		got, _ := findTask(pending(t, s), p.UUID)
		if !slices.Contains(got.Subtasks, c.UUID) {
			t.Errorf("parent subtasks = %v, want to contain %s", got.Subtasks, c.UUID)
		}
	})

	t.Run("annotate", func(t *testing.T) {
		s := setup(t)
		task := mustAdd(t, s, "A")
		if err := s.Annotate(task.UUID, "obiective/job.md"); err != nil {
			t.Fatal(err)
		}
		got, _ := findTask(pending(t, s), task.UUID)
		if len(got.Annotations) != 1 || got.Annotations[0].Text != "obiective/job.md" {
			t.Errorf("annotations = %+v", got.Annotations)
		}
	})

	t.Run("set and clear scheduled", func(t *testing.T) {
		s := setup(t)
		task := mustAdd(t, s, "A")
		when := T0.Add(5 * time.Hour)
		if err := s.SetScheduled(task.UUID, &when); err != nil {
			t.Fatal(err)
		}
		got, _ := findTask(pending(t, s), task.UUID)
		if got.Scheduled == nil || !got.Scheduled.Equal(when) {
			t.Fatalf("scheduled = %v, want %v", got.Scheduled, when)
		}
		if err := s.SetScheduled(task.UUID, nil); err != nil {
			t.Fatal(err)
		}
		got, _ = findTask(pending(t, s), task.UUID)
		if got.Scheduled != nil {
			t.Errorf("scheduled not cleared: %v", got.Scheduled)
		}
	})

	t.Run("start and stop", func(t *testing.T) {
		s := setup(t)
		task := mustAdd(t, s, "A project:ia")
		if err := s.Start(task.UUID); err != nil {
			t.Fatal(err)
		}
		got, _ := findTask(pending(t, s), task.UUID)
		if !got.Active {
			t.Error("task not active after Start")
		}
		if err := s.Stop(task.UUID); err != nil {
			t.Fatal(err)
		}
		got, _ = findTask(pending(t, s), task.UUID)
		if got.Active {
			t.Error("task still active after Stop")
		}
	})
}

// TimeTracker checks an implementation of ports.TimeTracker.
func TimeTracker(t *testing.T, newTracker func(t *testing.T, clock *core.FixedClock) ports.TimeTracker) {
	t.Run("start, active, stop", func(t *testing.T) {
		clock := &core.FixedClock{T: T0}
		s := newTracker(t, clock)
		if a, err := s.Active(); err != nil || a != nil {
			t.Fatalf("Active on empty = %v, %v", a, err)
		}
		if err := s.Start("ia"); err != nil {
			t.Fatal(err)
		}
		a, err := s.Active()
		if err != nil || a == nil {
			t.Fatalf("Active = %v, %v", a, err)
		}
		if !slices.Contains(a.Tags, "ia") || !a.Start.Equal(T0) {
			t.Errorf("active = %+v", a)
		}
		clock.Advance(30 * time.Minute)
		if err := s.Stop(); err != nil {
			t.Fatal(err)
		}
		if a, _ := s.Active(); a != nil {
			t.Errorf("still active: %+v", a)
		}
		es, _ := s.Entries(T0, T0.Add(time.Hour))
		if len(es) != 1 || es[0].End == nil || !es[0].End.Equal(T0.Add(30*time.Minute)) {
			t.Errorf("entries = %+v", es)
		}
	})

	t.Run("starting again stops the running interval", func(t *testing.T) {
		clock := &core.FixedClock{T: T0}
		s := newTracker(t, clock)
		_ = s.Start("ia")
		clock.Advance(10 * time.Minute)
		_ = s.Start("bd")
		clock.Advance(10 * time.Minute)
		es, _ := s.Entries(T0, T0.Add(time.Hour))
		if len(es) != 2 {
			t.Fatalf("entries = %+v", es)
		}
		if es[0].End == nil || !es[0].End.Equal(T0.Add(10*time.Minute)) {
			t.Errorf("first interval not closed at the second start: %+v", es[0])
		}
		if es[1].End != nil {
			t.Errorf("second interval should be running: %+v", es[1])
		}
	})

	t.Run("stop without running interval is not an error", func(t *testing.T) {
		s := newTracker(t, &core.FixedClock{T: T0})
		if err := s.Stop(); err != nil {
			t.Error(err)
		}
	})

	t.Run("add retroactive and filter by overlap", func(t *testing.T) {
		s := newTracker(t, &core.FixedClock{T: T0})
		end := T0.Add(-time.Hour)
		if err := s.Add(core.TimeEntry{Start: T0.Add(-2 * time.Hour), End: &end, Tags: []string{"citit"}}); err != nil {
			t.Fatal(err)
		}
		// Partial overlap with the window still returns the entry.
		es, _ := s.Entries(T0.Add(-90*time.Minute), T0)
		if len(es) != 1 {
			t.Errorf("overlapping entry not returned: %+v", es)
		}
		es, _ = s.Entries(T0.Add(-30*time.Minute), T0)
		if len(es) != 0 {
			t.Errorf("non-overlapping entry returned: %+v", es)
		}
	})

	t.Run("add rejects an interval without a positive length", func(t *testing.T) {
		s := newTracker(t, &core.FixedClock{T: T0})
		if err := s.Add(core.TimeEntry{Start: T0, End: &T0, Tags: []string{"x"}}); err == nil {
			t.Error("expected error")
		}
	})
}

// Calendar checks an implementation of ports.Calendar. writable is a calendar
// that accepts writes and readOnly one that does not.
func Calendar(t *testing.T, newCal func(t *testing.T) ports.Calendar, writable, readOnly string) {
	ev := core.Event{Title: "proiect-y", Start: T0.Add(5 * time.Hour), End: T0.Add(7 * time.Hour)}

	t.Run("add to writable calendar and read back", func(t *testing.T) {
		c := newCal(t)
		if err := c.AddEvent(writable, ev); err != nil {
			t.Fatal(err)
		}
		es, err := c.Events(T0, T0.Add(24*time.Hour))
		if err != nil {
			t.Fatal(err)
		}
		if len(es) != 1 || es[0].Title != "proiect-y" || es[0].Calendar != writable {
			t.Fatalf("events = %+v", es)
		}
		if !es[0].Start.Equal(ev.Start) || !es[0].End.Equal(ev.End) {
			t.Errorf("times = %v–%v", es[0].Start, es[0].End)
		}
	})

	t.Run("read-only calendar refuses writes", func(t *testing.T) {
		c := newCal(t)
		if err := c.AddEvent(readOnly, ev); err == nil {
			t.Error("expected error")
		}
	})

	t.Run("events outside the window are not returned", func(t *testing.T) {
		c := newCal(t)
		_ = c.AddEvent(writable, ev)
		es, _ := c.Events(T0.Add(24*time.Hour), T0.Add(48*time.Hour))
		if len(es) != 0 {
			t.Errorf("events = %+v", es)
		}
	})
}

// Habits checks an implementation of ports.Habits. The implementation must
// know a habit named habit.
func Habits(t *testing.T, newHabits func(t *testing.T) ports.Habits, habit string) {
	t.Run("log and read back", func(t *testing.T) {
		h := newHabits(t)
		if err := h.Log(habit, T0, core.HabitDone); err != nil {
			t.Fatal(err)
		}
		st, err := h.Status(T0)
		if err != nil {
			t.Fatal(err)
		}
		i := slices.IndexFunc(st, func(x core.Habit) bool { return x.Name == habit })
		if i < 0 || st[i].Today != core.HabitDone {
			t.Errorf("status = %+v", st)
		}
	})

	t.Run("another day is not affected", func(t *testing.T) {
		h := newHabits(t)
		_ = h.Log(habit, T0, core.HabitDone)
		st, _ := h.Status(T0.AddDate(0, 0, 1))
		i := slices.IndexFunc(st, func(x core.Habit) bool { return x.Name == habit })
		if i < 0 || st[i].Today != core.HabitNone {
			t.Errorf("status = %+v", st)
		}
	})
}

// Notes checks an implementation of ports.Notes (the parts whose behaviour is
// already fixed by the spec; CreateFromTemplate is added in stage 5).
func Notes(t *testing.T, newNotes func(t *testing.T) ports.Notes) {
	t.Run("append creates and appends", func(t *testing.T) {
		n := newNotes(t)
		if err := n.AppendLine("inbox.md", "- prima"); err != nil {
			t.Fatal(err)
		}
		if err := n.AppendLine("inbox.md", "- a doua"); err != nil {
			t.Fatal(err)
		}
		c, err := n.Read("inbox.md")
		if err != nil {
			t.Fatal(err)
		}
		if c != "- prima\n- a doua\n" {
			t.Errorf("content = %q", c)
		}
		refs, _ := n.List()
		if !slices.ContainsFunc(refs, func(r core.NoteRef) bool { return r.Path == "inbox.md" }) {
			t.Errorf("inbox.md not listed: %+v", refs)
		}
	})

	t.Run("auto section keeps the rest of the file", func(t *testing.T) {
		n := newNotes(t)
		_ = n.AppendLine("j.md", "# Jurnal")
		_ = n.AppendLine("j.md", core.AutoStart)
		_ = n.AppendLine("j.md", "vechi")
		_ = n.AppendLine("j.md", core.AutoEnd)
		_ = n.AppendLine("j.md", "## Reflecții")
		if err := n.UpdateAutoSection("j.md", "nou"); err != nil {
			t.Fatal(err)
		}
		c, _ := n.Read("j.md")
		want := "# Jurnal\n" + core.AutoStart + "\nnou\n" + core.AutoEnd + "\n## Reflecții\n"
		if c != want {
			t.Errorf("content = %q, want %q", c, want)
		}
	})

	t.Run("reading a missing note is an error", func(t *testing.T) {
		n := newNotes(t)
		if _, err := n.Read("nu-exista.md"); err == nil {
			t.Error("expected error")
		}
	})
}
