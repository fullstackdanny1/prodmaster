# dashboard: productivitate în terminal

O aplicație TUI care adună într-o singură vedere calendarul (khal), sarcinile (Taskwarrior), timpul (Timewarrior), obiceiurile (harsh) și notițele Markdown. Aplicația nu are bază de date proprie: citește și scrie doar prin aceste unelte.

Specificația completă este în [`docs/SPECIFICATIE.md`](docs/SPECIFICATIE.md). Ghidul pentru citirea codului este în [`docs/ARHITECTURA.md`](docs/ARHITECTURA.md).

## Stare

| Etapă | Conținut | Stare |
|---|---|---|
| 1 | Fundația: structură, configurare, interfețe, adaptoare `fake`, schelet UI | **gata** ([rezumat](docs/sesiuni/etapa-1.md)) |
| 2 | Sarcini și timp (Taskwarrior, Timewarrior) | — |
| 3 | Agenda (khal) | — |
| 4 | Ecranul Timp | — |
| 5 | Notițe | — |
| 6 | Obiceiuri, revizuire, `dashboard notify` | — |

În etapa 1 ecranele afișează ce vor conține. Tastele care nu funcționează încă apar estompate și, la apăsare, spun în ce etapă vin.

## Compilare și rulare

Este nevoie de Go 1.24 sau mai nou.

```sh
go build -o dashboard ./cmd/dashboard
./dashboard                 # pornește pe ecranul din configurare
./dashboard --page timp     # agenda | sarcini | timp | notite
```

## Configurare

```sh
mkdir -p ~/.config/dashboard
cp config.example.toml ~/.config/dashboard/config.toml
```

Dacă fișierul lipsește, aplicația pornește cu valorile implicite. Valorile greșite (o culoare necunoscută, o pagină inexistentă) nu opresc aplicația: sunt semnalate în bara de jos și se folosește valoarea implicită.

Ca să încercați interfața fără uneltele instalate, puneți `"fake"` la adaptoare:

```toml
[adapters]
calendar = "fake"
tasks = "fake"
time = "fake"
habits = "fake"
```

## Teste

```sh
go test ./...
```

## Scurtături (etapa 1)

| Tastă | Acțiune |
|---|---|
| `1`–`4`, `Tab`, `Shift+Tab` | schimbă ecranul |
| `Space` | meniul de acțiuni |
| `?` | ajutor |
| `q`, `Ctrl+C` | ieșire |

## Alte proiecte din acest repo

| Folder | Ce este |
|---|---|
| [`studiu/`](studiu/) | aplicația web locală pentru pregătirea examenelor (notițe, carduri, quiz, examen, chat) |
| [`unelte/`](unelte/) | suita de comenzi de terminal (backup, organizare, OCR, conversie, corectură, traducere, rezumat) |

Cele două proiecte folosesc același strat AI (`studiu/app/ai/` = `unelte/unelte/ai/`) și aceeași
configurație, `~/.config/ai/ai.toml`.
