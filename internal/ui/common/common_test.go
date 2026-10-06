package common

import (
	"testing"
	"time"
)

func TestFormatClock(t *testing.T) {
	cases := map[time.Duration]string{
		0:                               "0:00",
		42 * time.Minute:                "0:42",
		42*time.Minute + 59*time.Second: "0:42",
		2*time.Hour + 5*time.Minute:     "2:05",
		-time.Minute:                    "0:00",
		12*time.Hour + 30*time.Minute:   "12:30",
	}
	for d, want := range cases {
		if got := FormatClock(d); got != want {
			t.Errorf("FormatClock(%v) = %q, want %q", d, got, want)
		}
	}
}

func TestOverlay(t *testing.T) {
	bg := "aaaaa\nbbbbb\nccccc"
	got := Overlay(bg, "XY\nZW", 1, 1)
	want := "aaaaa\nbXY\x1b[0mbb\ncZW\x1b[0mcc"
	if got != want {
		t.Errorf("got %q, want %q", got, want)
	}
}

func TestOverlayPadsShortLinesAndClips(t *testing.T) {
	got := Overlay("a\nb", "X\nY\nZ", 3, 1)
	want := "a\nb  X\x1b[0m"
	if got != want {
		t.Errorf("got %q, want %q", got, want)
	}
}
