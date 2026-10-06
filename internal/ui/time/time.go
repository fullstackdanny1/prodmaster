// Package timeview is screen 3: time per project and its chart (spec 6.7). In
// stage 1 it is a placeholder; it is built in stage 4.
//
// The directory is called "time" as in spec 9.2, but the package is named
// timeview so it does not clash with the standard library package "time".
package timeview

import "github.com/fullstackdanny1/prodmaster/internal/ui/common"

// New returns the Time screen.
func New() common.Page {
	return common.NewPlaceholder("Timp", 4, []string{
		"proiectele, ordonate după timpul din perioada selectată",
		"graficul proiectului selectat, în culoarea lui",
		"plan vs. realitate",
		"perioade: săptămâna, luna, anul (cu [ și ])",
	}, []common.Hint{
		{Key: "[ ]", Desc: "perioada", Stage: 4},
		{Key: "t", Desc: "timp manual", Stage: 4},
		{Key: "I", Desc: "import telefon", Stage: 4},
	})
}
