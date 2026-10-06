package core

import "time"

// Clock gives the current time. Every rule that depends on "now" receives a
// Clock instead of calling time.Now directly, so tests can freeze time
// (spec section 5).
type Clock interface {
	Now() time.Time
}

// SystemClock is the real clock, used by the running application.
type SystemClock struct{}

func (SystemClock) Now() time.Time { return time.Now() }

// FixedClock always returns the same instant. Tests can move it with Set.
type FixedClock struct {
	T time.Time
}

func (c *FixedClock) Now() time.Time { return c.T }

// Set moves the fixed clock to t.
func (c *FixedClock) Set(t time.Time) { c.T = t }

// Advance moves the fixed clock forward by d.
func (c *FixedClock) Advance(d time.Duration) { c.T = c.T.Add(d) }
