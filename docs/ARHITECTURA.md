# Ghid pentru citirea codului

Ghidul explică organizarea codului, ordinea în care merită citit și drumul unei apăsări de tastă prin aplicație. Comentariile din cod sunt în engleză (specificația, 9.1); explicațiile de aici sunt în română.

## 1. Ideea centrală: porturi și adaptoare

```
              ┌──────────────── ui (Bubble Tea) ────────────────┐
              │  app.go: taburi, bare, meniu, ajutor            │
              │  agenda/ tasks/ time/ notes/ : ecranele         │
              └───────────────┬─────────────────────────────────┘
                              │ folosește doar
              ┌───────────────▼──────────────┐     ┌──────────────┐
              │ ports: interfețele           │◄────│ core: tipuri │
              │ Tasks, TimeTracker, Calendar │     │ și reguli    │
              └───────────────▲──────────────┘     └──────────────┘
                              │ implementează
     ┌──────────┬─────────────┼─────────────┬──────────┐
   fake/    taskwarrior/  timewarrior/    khal/     harsh/ …
 (în memorie)   (etapa 2)    (etapa 2)  (etapa 3) (etapa 6)
```

- **`core`** conține tipurile aplicației (`Task`, `Event`, `TimeEntry`, `Habit`) și regulile din secțiunea 5. Nu știe nimic despre unelte.
- **`ports`** conține interfețele: ce trebuie să știe să facă un „furnizor de sarcini”, un „furnizor de timp” etc.
- **Adaptoarele** implementează interfețele pentru o unealtă anume. Doar ele rulează comenzi externe și traduc rezultatul în tipurile din `core`.
- **`ui`** primește adaptoarele prin structura `ui.Deps` și nu cunoaște tipurile concrete.

Ca să înlocuiți o unealtă, scrieți un adaptor nou care implementează interfața și trece testele de contract (secțiunea 5 de mai jos). Nucleul și interfața rămân neschimbate.

## 2. Harta directoarelor

| Cale | Ce conține |
|---|---|
| `cmd/dashboard/main.go` | punctul de intrare: argumentele din linia de comandă, încărcarea configurării, pornirea TUI-ului |
| `cmd/dashboard/wire.go` | **singurul loc** care alege implementarea concretă pentru fiecare port (`"fake"`, `"taskwarrior"`, …) |
| `internal/core/model.go` | tipurile de domeniu (4.2) |
| `internal/core/clock.go` | ceasul injectabil (`Clock`, `SystemClock`, `FixedClock` pentru teste) |
| `internal/core/color.go` | validarea culorilor și `Palette` (5.9) |
| `internal/core/project.go` | convenția de nume de proiect (4.1) și găsirea proiectului dintr-un interval de timp |
| `internal/core/autosection.go` | înlocuirea secțiunii `<!-- auto:start -->…<!-- auto:end -->` din jurnal (7.2) |
| `internal/ports/ports.go` | interfețele (9.3) |
| `internal/ports/contract/` | testele de contract, comune tuturor adaptoarelor (12) |
| `internal/adapters/fake/` | implementări în memorie ale tuturor porturilor |
| `internal/config/` | citirea și validarea `config.toml` (10) |
| `internal/ui/app.go` | modelul principal: taburi, cronometrul din bara de sus, bara de jos, scurtăturile globale |
| `internal/ui/keys.go` | lista scurtăturilor globale, meniul `Space`, popup-ul de ajutor |
| `internal/ui/common/` | interfața `Page`, stilurile, suprapunerea popup-urilor peste conținut |
| `internal/ui/{agenda,tasks,time,notes}/` | cele patru ecrane (deocamdată schițe) |

## 3. Ordinea recomandată de citire

1. `internal/core/model.go`: vocabularul aplicației.
2. `internal/ports/ports.go`: ce operații există.
3. `internal/adapters/fake/tasks.go`: o implementare simplă a unei interfețe.
4. `internal/ports/contract/contract.go`: comportamentul cerut oricărui adaptor.
5. `internal/config/config.go`: cum se citește configurarea și cum se tratează valorile greșite.
6. `internal/ui/app.go`, apoi `keys.go`: cum funcționează interfața.
7. `cmd/dashboard/main.go` și `wire.go`: cum se leagă totul.

## 4. Cum funcționează interfața (Bubble Tea)

Bubble Tea folosește arhitectura Elm. Toată starea stă într-o singură valoare (`ui.Model`) și se schimbă doar în `Update`:

```
       mesaj (tastă, tick, rezultat)            comandă (tea.Cmd)
  ──────────────►  Update(model, mesaj)  ──────────────────────────►  rulează în fundal
                         │                                                  │
                         ▼                                                  │
                    model nou ───► View() ───► text pe ecran                │
                         ▲                                                  │
                         └─────────────── mesaj cu rezultatul ◄─────────────┘
```

Exemplu: utilizatorul apasă `3`.

1. Bubble Tea trimite `tea.KeyMsg` cu textul `"3"` către `Model.Update`.
2. `Update` îl dă mai departe la `handleKey`, care șterge mesajul de stare și vede că nu e deschis niciun popup.
3. `"3"` este o tastă globală, așa că se apelează `switchTo(2)`. Aceasta schimbă `m.active` și întoarce comanda `reload()`, pentru că datele se reîncarcă la schimbarea ecranului (9.6).
4. Bubble Tea apelează `View()`, care desenează bara de sus, ecranul `Timp`, bara de jos.
5. În paralel, comanda din `reload()` citește cronometrul activ (`TimeTracker.Active()`) și trimite rezultatul ca `timerMsg`. `Update` îl salvează în `m.timer`.

Alte mesaje:

- `tickMsg`, o dată pe secundă: actualizează doar `m.now`, deci cronometrul din bara de sus avansează fără a reciti datele (9.6).
- `refreshMsg`, la fiecare `refresh_seconds`: reîncarcă datele.
- Orice mesaj pe care modelul principal nu îl tratează ajunge la ecranul activ (`Page.Update`). Așa vor primi ecranele, începând cu etapa 2, tastele proprii și datele încărcate.

### Popup-urile

`Space` și `?` setează `m.overlay`. Cât timp un popup e deschis, tastele merg doar la el. Desenarea se face în `View`: conținutul ecranului se desenează normal, apoi `common.Overlay` scrie popup-ul peste el, rând cu rând (meniul în colțul din dreapta jos, ca în Helix; ajutorul în centru).

### Scurtăturile neimplementate

Fiecare scurtătură are câmpul `Stage`. Dacă e mai mare decât 0, scurtătura e afișată estompat, iar la apăsare bara de jos spune `„adaugă sarcină” vine în etapa 2`. La implementare se șterge câmpul `Stage`, iar acțiunea se tratează în ecranul respectiv.

## 5. Testele

| Ce | Unde | Cum |
|---|---|---|
| Regulile nucleului | `internal/core/core_test.go` | funcții pure, cu ceas fix |
| Contractul porturilor | `internal/ports/contract/` | aceleași teste pentru orice implementare |
| Adaptoarele fake | `internal/adapters/fake/fake_test.go` | rulează testele de contract |
| Configurarea | `internal/config/config_test.go` | fișiere TOML temporare, inclusiv `config.example.toml` |
| Interfața | `internal/ui/app_test.go` | se trimit mesaje în `Update` și se verifică starea și textul din `View()` |
| Linia de comandă | `cmd/dashboard/main_test.go` | argumente invalide, alegerea adaptoarelor |

Un adaptor real nou (de exemplu Taskwarrior, în etapa 2) adaugă un test de forma:

```go
func TestContract(t *testing.T) {
    if _, err := exec.LookPath("task"); err != nil {
        t.Skip("task nu este instalat")
    }
    contract.Tasks(t, func(t *testing.T, c *core.FixedClock) ports.Tasks {
        dir := t.TempDir()
        t.Setenv("TASKDATA", dir)
        t.Setenv("TASKRC", filepath.Join(dir, "taskrc"))
        return taskwarrior.New(c)
    })
}
```

## 6. Dependențe

| Bibliotecă | De ce |
|---|---|
| `charmbracelet/bubbletea` v1 | bucla TUI-ului (9.1) |
| `charmbracelet/lipgloss` | stiluri, culori, aranjare (9.1) |
| `charmbracelet/x/ansi` | tăierea textului colorat după lățimea vizibilă, pentru popup-uri și bare. E deja o dependență a lui Bubble Tea; este fixată la versiunea pe care o cere Bubble Tea v1.3.10 |
| `BurntSushi/toml` | citirea configurării (9.1) |

Bubbles (componente), Glamour (Markdown) și biblioteca de căutare fuzzy se adaugă în etapele în care sunt folosite.
