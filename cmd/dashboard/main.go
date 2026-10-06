// Command dashboard is the entry point of the productivity dashboard
// (spec 9.5). It parses the command line, loads the configuration, wires the
// adapters and starts the TUI or runs one of the sub-commands.
package main

import (
	"flag"
	"fmt"
	"os"
	"slices"
	"strings"

	tea "github.com/charmbracelet/bubbletea"

	"github.com/fullstackdanny1/prodmaster/internal/config"
	"github.com/fullstackdanny1/prodmaster/internal/ui"
)

// subcommands lists the non-interactive commands and the stage that brings
// each of them (spec 9.5, 13).
var subcommands = map[string]int{
	"notify":      6,
	"import-timp": 4,
	"jurnal":      5,
}

func main() {
	os.Exit(run(os.Args[1:]))
}

// run returns the process exit code; keeping it out of main makes it testable.
func run(args []string) int {
	if len(args) > 0 {
		if stage, ok := subcommands[args[0]]; ok {
			fmt.Fprintf(os.Stderr, "dashboard %s: nu este implementat încă (etapa %d)\n", args[0], stage)
			return 2
		}
	}

	fs := flag.NewFlagSet("dashboard", flag.ContinueOnError)
	page := fs.String("page", "", "ecranul de pornire: "+strings.Join(config.Pages, "|"))
	fs.Usage = func() {
		fmt.Fprintf(fs.Output(), "Utilizare:\n"+
			"  dashboard [--page %s]\n"+
			"  dashboard notify | import-timp | jurnal\n", strings.Join(config.Pages, "|"))
	}
	if err := fs.Parse(args); err != nil {
		return 2
	}
	if fs.NArg() > 0 {
		fmt.Fprintf(os.Stderr, "comandă necunoscută: %s\n", fs.Arg(0))
		fs.Usage()
		return 2
	}
	if *page != "" && !slices.Contains(config.Pages, *page) {
		fmt.Fprintf(os.Stderr, "--page invalid: %q\n", *page)
		fs.Usage()
		return 2
	}

	cfg, err := config.Load(config.DefaultPath())
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		return 1
	}
	start := cfg.General.StartPage
	if *page != "" {
		start = *page
	}

	deps, wiringWarnings := buildDeps(cfg)
	warnings := append(slices.Clone(cfg.Warnings), wiringWarnings...)

	p := tea.NewProgram(ui.New(cfg, deps, start, warnings), tea.WithAltScreen())
	if _, err := p.Run(); err != nil {
		fmt.Fprintln(os.Stderr, err)
		return 1
	}
	return 0
}
