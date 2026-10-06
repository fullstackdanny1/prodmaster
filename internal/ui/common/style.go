package common

import (
	"fmt"
	"time"

	"github.com/charmbracelet/lipgloss"

	"github.com/fullstackdanny1/prodmaster/internal/core"
)

// Shared styles. Colours are ANSI indices so they follow the terminal theme.
var (
	Title     = lipgloss.NewStyle().Bold(true)
	Dim       = lipgloss.NewStyle().Foreground(lipgloss.Color("8"))
	Key       = lipgloss.NewStyle().Bold(true)
	TabActive = lipgloss.NewStyle().Bold(true).Reverse(true)
	TabIdle   = lipgloss.NewStyle()
	Separator = lipgloss.NewStyle().Foreground(lipgloss.Color("8"))
	Info      = lipgloss.NewStyle().Foreground(lipgloss.Color("2"))
	Warn      = lipgloss.NewStyle().Foreground(lipgloss.Color("3"))
	Error     = lipgloss.NewStyle().Foreground(lipgloss.Color("1")).Bold(true)
	Popup     = lipgloss.NewStyle().Border(lipgloss.RoundedBorder()).Padding(0, 1)
)

// ProjectStyle returns the style used wherever a project appears (spec 5.9).
func ProjectStyle(p core.Palette, project string) lipgloss.Style {
	return lipgloss.NewStyle().Foreground(lipgloss.Color(p.Color(project)))
}

// FormatClock formats a duration as "h:mm" ("0:42", "12:05"), the format of the
// running timer in the top bar. Negative durations count as zero.
func FormatClock(d time.Duration) string {
	if d < 0 {
		d = 0
	}
	m := int(d / time.Minute)
	return fmt.Sprintf("%d:%02d", m/60, m%60)
}
