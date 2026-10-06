// Package agenda is screen 1: the chronological list of events and work
// blocks (spec 6.5). In stage 1 it is a placeholder; it is built in stage 3.
package agenda

import "github.com/fullstackdanny1/prodmaster/internal/ui/common"

// New returns the Agenda screen.
func New() common.Page {
	return common.NewPlaceholder("Agendă", 3, []string{
		"evenimentele și blocurile de lucru, pe zile, de azi înainte",
		"sarcinile cursurilor sub fiecare eveniment",
		"progresul blocurilor și subtask-urile împrumutate",
		"detaliile elementului selectat în panoul din dreapta",
	}, []common.Hint{
		{Key: "x", Desc: "bifează", Stage: 3},
		{Key: "b", Desc: "bloc nou", Stage: 3},
		{Key: "i", Desc: "împrumută subtask-uri", Stage: 3},
		{Key: "n", Desc: "notița prelegerii", Stage: 5},
	})
}
