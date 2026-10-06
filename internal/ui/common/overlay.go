package common

import (
	"strings"

	"github.com/charmbracelet/x/ansi"
)

// Overlay draws fg on top of bg with fg's top-left corner at column x, row y.
//
// Both strings may contain ANSI colour codes; the ansi package cuts lines by
// visible width, so colours outside the popup are preserved. Parts of fg that
// fall outside bg are clipped.
func Overlay(bg, fg string, x, y int) string {
	bgLines := strings.Split(bg, "\n")
	fgLines := strings.Split(fg, "\n")
	for i, line := range fgLines {
		row := y + i
		if row < 0 || row >= len(bgLines) {
			continue
		}
		base := bgLines[row]
		w := ansi.StringWidth(line)
		if pad := x - ansi.StringWidth(base); pad > 0 {
			base += strings.Repeat(" ", pad)
		}
		left := ansi.Truncate(base, x, "")
		right := ansi.TruncateLeft(base, x+w, "")
		bgLines[row] = left + line + "\x1b[0m" + right
	}
	return strings.Join(bgLines, "\n")
}
