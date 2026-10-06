package fake

import (
	"fmt"
	"slices"
	"sort"
	"sync"
	"time"

	"github.com/fullstackdanny1/prodmaster/internal/core"
)

// TimeTracker is an in-memory time log with a single running interval, like
// Timewarrior.
type TimeTracker struct {
	mu      sync.Mutex
	clock   core.Clock
	entries []core.TimeEntry
}

func NewTimeTracker(clock core.Clock) *TimeTracker { return &TimeTracker{clock: clock} }

func (s *TimeTracker) Start(tags ...string) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.stop()
	s.entries = append(s.entries, core.TimeEntry{Start: s.clock.Now(), Tags: slices.Clone(tags)})
	return nil
}

func (s *TimeTracker) Stop() error {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.stop()
	return nil
}

func (s *TimeTracker) stop() {
	for i := range s.entries {
		if s.entries[i].End == nil {
			now := s.clock.Now()
			s.entries[i].End = &now
		}
	}
}

func (s *TimeTracker) Active() (*core.TimeEntry, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	for _, e := range s.entries {
		if e.End == nil {
			c := copyEntry(e)
			return &c, nil
		}
	}
	return nil, nil
}

func (s *TimeTracker) Entries(from, to time.Time) ([]core.TimeEntry, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	now := s.clock.Now()
	var out []core.TimeEntry
	for _, e := range s.entries {
		end := now
		if e.End != nil {
			end = *e.End
		}
		if e.Start.Before(to) && end.After(from) {
			out = append(out, copyEntry(e))
		}
	}
	sort.Slice(out, func(i, j int) bool { return out[i].Start.Before(out[j].Start) })
	return out, nil
}

func (s *TimeTracker) Add(e core.TimeEntry) error {
	if e.End == nil || !e.End.After(e.Start) {
		return fmt.Errorf("interval invalid: sfârșitul trebuie să fie după început")
	}
	s.mu.Lock()
	defer s.mu.Unlock()
	s.entries = append(s.entries, copyEntry(e))
	return nil
}

func copyEntry(e core.TimeEntry) core.TimeEntry {
	e.Tags = slices.Clone(e.Tags)
	if e.End != nil {
		v := *e.End
		e.End = &v
	}
	return e
}
