package core

import (
	"fmt"
	"regexp"
	"strconv"
	"strings"
)

// Project colours (spec 5.9).
//
// Colours are configured as terminal colour names ("green"), ANSI indices
// ("208") or hex values ("#e5a50a"). NormalizeColor turns all three into the
// form the UI library understands: a decimal ANSI index or a hex string.

// terminalColorNames maps the standard 16 terminal colour names to their ANSI
// index. Both "bright-x" and "brightx" spellings are accepted.
var terminalColorNames = map[string]int{
	"black": 0, "red": 1, "green": 2, "yellow": 3,
	"blue": 4, "magenta": 5, "cyan": 6, "white": 7,
	"gray": 8, "grey": 8, "bright-black": 8,
	"bright-red": 9, "bright-green": 10, "bright-yellow": 11,
	"bright-blue": 12, "bright-magenta": 13, "bright-cyan": 14, "bright-white": 15,
}

var hexColor = regexp.MustCompile(`^#([0-9a-fA-F]{6}|[0-9a-fA-F]{3})$`)

// NormalizeColor validates a configured colour value and returns it as either
// an ANSI index ("2", "208") or a lowercase hex string ("#e5a50a").
func NormalizeColor(value string) (string, error) {
	v := strings.ToLower(strings.TrimSpace(value))
	if v == "" {
		return "", fmt.Errorf("culoare goală")
	}
	if hexColor.MatchString(v) {
		return v, nil
	}
	if n, err := strconv.Atoi(v); err == nil {
		if n < 0 || n > 255 {
			return "", fmt.Errorf("indice ANSI în afara intervalului 0–255: %q", value)
		}
		return strconv.Itoa(n), nil
	}
	name := v
	if strings.HasPrefix(name, "bright") && !strings.HasPrefix(name, "bright-") {
		name = "bright-" + strings.TrimPrefix(name, "bright")
	}
	if n, ok := terminalColorNames[name]; ok {
		return strconv.Itoa(n), nil
	}
	return "", fmt.Errorf("culoare necunoscută: %q", value)
}

// Palette resolves the colour of any project. It may hold colours for projects
// that do not exist yet: such entries are never listed anywhere, they simply
// apply as soon as the project shows up in a tool (spec 5.9).
type Palette struct {
	Default  string            // normalised colour for projects without their own
	Projects map[string]string // project name -> normalised colour
}

// Color returns the colour of project, falling back to the default.
func (p Palette) Color(project string) string {
	if c, ok := p.Projects[project]; ok {
		return c
	}
	return p.Default
}
