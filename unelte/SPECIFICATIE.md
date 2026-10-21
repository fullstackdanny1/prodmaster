# Unelte – specificația suitei de utilitare

Document de implementare pentru **Unelte**: o colecție de comenzi de terminal și servicii
locale care înlocuiesc unelte online plătite pentru redactare, documente, OCR, organizarea
fișierelor, backup, CV-uri, buget personal și rezumate de știri.

Sisteme țintă: **Ubuntu / Debian**, **Fedora** și **Arch** (vezi 3.6).

Documentul e scris pentru implementare de către un agent de cod. Ce e marcat **TREBUIE**
e obligatoriu; ce e marcat **POATE** e opțional.

Proiectul-soră **Studiu** (aplicația de pregătire pentru examene: notițe, carduri, quiz-uri,
simulări de examen) are specificația lui separată și nu face parte din acest repo.
Cele două proiecte folosesc **același strat AI** și aceeași configurație AI (3.3).

---

## 1. Scop și principii

### 1.1 Ce conține suita

| Comandă / serviciu | Înlocuiește | Rol |
|---|---|---|
| `backup` | servicii de backup cu abonament | commit și push automat pentru folderele importante |
| `organizeaza` | aplicații de organizare | mută fișierele descărcate după reguli |
| `ocr-ecran` | aplicații OCR online | text dintr-o zonă a ecranului, direct în clipboard |
| `converteste` | șabloane plătite, convertoare online | Markdown → Word/PDF cu șablonul facultății |
| `verifica-format` | verificare manuală | verifică un document după regulile facultății |
| `corecteaza` | Grammarly | gramatică și ortografie locale, stil prin AI |
| `traduce` | DeepL Pro | traducere prin AI cu păstrarea formatării |
| `cv` *(amânat)* | Teal, Kickresume, Rezi | CV și scrisoare adaptate pe anunț, evidența aplicărilor |
| `buget` *(amânat)* | aplicații de buget cu abonament | categorisirea extraselor, raport lunar, abonamente |
| `rezumat` | funcțiile AI plătite ale cititoarelor RSS | rezumat zilnic din sursele tale |
| Stirling-PDF | iLovePDF, Adobe online | operații PDF în browser, local |
| Excalidraw | aplicații de whiteboard cu abonament | schițe și diagrame libere în browser, local |
| ChartDB | dbdiagram.io și alte editoare ER plătite | proiectarea bazelor de date (tabele, relații, SQL), local |

Un singur utilizator, laptop cu **Ubuntu** sau **Fedora** (Arch rămâne suportat), cu **sway**
sau alt mediu grafic (3.6). Comenzile se rulează din terminal; nu se configurează scurtături
de tastatură.

### 1.2 Principii „set and forget” (TREBUIE respectate în toate deciziile)

1. **Un repo, un instalator, o configurație.** `./install.sh` face tot; configurația stă
   într-un singur fișier TOML.
2. **Python din biblioteca standard ori de câte ori se poate.** CLI cu `argparse`, HTTP cu
   `urllib`, configurație cu `tomllib`. Singura dependență Python de bază e `python-docx`.
   Fiecare dependență nouă trebuie justificată.
3. **Programe de sistem mature în loc de cod propriu**: `pandoc`, LibreOffice, `tesseract`,
   unelte de captură și clipboard, `git`, LanguageTool. Instalatorul detectează distribuția
   și afișează comanda potrivită (`apt`, `dnf` sau `pacman`) pentru ce lipsește (3.6).
4. **Automatizările rulează cu systemd de utilizator** (timers), nu cu cron sau procese
   proprii care stau pornite.
5. **Nu distruge niciodată date.** Fără suprascrieri: rezultatele merg în fișiere noi
   (`raport.corectat.md`, `lucrare.docx`), mutările nu înlocuiesc fișiere existente și pot
   fi anulate, backup-ul nu face niciodată `push --force`.
6. **Implicit „doar arată”.** Comenzile care mută sau modifică fișiere au implicit un mod de
   previzualizare și cer `--aplica` pentru acțiunea reală (excepție: timer-ele, care rulează
   doar regulile marcate explicit ca automate).
7. **Fiecare comandă merge independent.** Lipsa unei unelte de sistem dezactivează doar
   comanda care are nevoie de ea, cu un mesaj clar.
8. **Mesaje în română, coduri de ieșire corecte**: 0 = succes, 1 = probleme găsite
   (de exemplu erori de formatare), 2 = eroare de utilizare sau de mediu.
9. **AI modular.** Orice comandă care folosește AI poate rula pe orice model (cloud sau local),
   ales din configurație per sarcină sau cu `--model` la rulare (3.3). Fără SDK-uri de furnizor.
10. **AI-ul nu e obligatoriu.** Fiecare comandă are un comportament util fără AI sau spune clar
   ce nu poate face fără el.

---

## 2. Structura repo-ului

```
unelte/
├── install.sh                 instalare și actualizare
├── config.example.toml        copiat în ~/.config/unelte/config.toml
├── ai.example.toml            copiat în ~/.config/ai/ai.toml (comun cu Studiu)
├── distro.toml                programe → pachete pe distribuții (3.6)
├── requirements.txt           python-docx (versiune exactă)
├── requirements-dev.txt       pytest
├── README.md
├── CLAUDE.md
├── unelte/                    pachetul Python
│   ├── __main__.py            `python -m unelte <comanda>`
│   ├── cli.py                 argparse, dispecer de subcomenzi
│   ├── ai/                    stratul AI comun (3.3), identic cu cel din Studiu
│   │   ├── client.py
│   │   ├── config.py
│   │   ├── schema.py          validatorul JSON Schema minimal
│   │   └── adaptoare/         openai.py, anthropic.py
│   ├── comun/
│   │   ├── config.py          citire config + valori implicite
│   │   ├── sistem.py          verificare programe, distribuție, mediu grafic, notificări, procese
│   │   ├── fisiere.py         scriere atomică, nume fără suprascriere, căi
│   │   └── jurnal.py          jurnal în ~/.local/state/unelte/
│   ├── backup.py
│   ├── organizeaza.py
│   ├── ocr_ecran.py
│   ├── converteste.py
│   ├── verifica_format.py
│   ├── corecteaza.py
│   ├── traduce.py
│   ├── cv.py                  (amânat, 12)
│   ├── buget.py               (amânat, 13)
│   ├── rezumat.py
│   └── doctor.py              `unelte doctor`
├── profiluri/                 profiluri de documente (vezi 7)
│   └── facultate/
│       ├── profil.toml
│       ├── reference.docx     șablonul Word al facultății
│       ├── stil.csl           stilul de citare
│       └── pagina-titlu.lua   filtru pandoc
│   └── cv/                    profilul pentru CV și scrisori (fără pagină de titlu)
├── prompturi/                 prompturile AI implicite (text editabil)
├── systemd/                   unități systemd de utilizator (șabloane)
├── servicii/
│   └── compose.yml            Stirling-PDF, Excalidraw și ChartDB
└── tests/
```

### 2.1 Comenzile instalate

`install.sh` creează scripturi mici în `~/.local/bin/` care rulează pachetul din `.venv`-ul
repo-ului:

```
backup  organizeaza  ocr-ecran  converteste  verifica-format  corecteaza  traduce
rezumat  unelte
```

Lansatoarele `cv` și `buget` se creează doar dacă modulele amânate au fost implementate
și activate în `[module]` (3.1).

`unelte` singur afișează lista comenzilor; `unelte doctor` verifică instalarea (vezi 16.2).
Fiecare comandă are `--help` în română, cu exemple.

---

## 3. Comun

### 3.1 Configurația: `~/.config/unelte/config.toml`

Un fișier gol TREBUIE să funcționeze (valori implicite pentru tot). Secțiunile fiecărei
comenzi sunt descrise la comanda respectivă. Secțiunea comună:

```toml
[general]
limba = "ro"
notificari = true             # notify-send la final pentru comenzile lungi și timer-e

[module]                      # modulele amânate (12, 13); false = fără lansator și fără timer
cv = false
buget = false

[ai]
# Furnizorii, modelele și ce model folosește fiecare sarcină se configurează în fișierul
# comun ~/.config/ai/ai.toml (vezi 3.3). Aici nu e nevoie de nimic.
```

### 3.2 Secretele

Unelte nu are fișier propriu de secrete. Cheile AI stau în `~/.config/ai/.env`, comun cu
Studiu (3.3). Nicio cheie nu se scrie vreodată în `config.toml`, în jurnale sau în repo.

### 3.3 Stratul AI comun (modular)

Orice funcție AI poate folosi **orice model, de la orice furnizor, inclusiv modele locale**,
fără modificări de cod. Codul cere doar o **sarcină** (de exemplu `carduri` sau `traducere`),
iar stratul AI decide, după configurație, ce furnizor și ce model o execută.

Același strat AI e folosit de **Studiu** și de **Unelte**, cu același fișier de configurare și
aceleași chei. Codul (pachetul `ai/`) e copiat intenționat în ambele proiecte, cu constanta
`AI_LAYER_VERSION`, ca fiecare proiect să poată fi actualizat independent. Textul acestei
secțiuni e identic în ambele specificații.

**Fișiere**

- `~/.config/ai/ai.toml` – furnizori, aliasuri, ce model folosește fiecare sarcină;
- `~/.config/ai/.env` – cheile (`NUME=valoare`), permisiuni `600`. Stratul AI îl citește
  singur (nu depinde de lansator); variabilele de mediu deja setate au prioritate;
- `~/.local/state/ai/consum/AAAA-LL.jsonl` – consumul, comun ambelor proiecte;
- variabila de mediu `AI_CONFIG` poate indica alt fișier de configurare (folosită în teste);
- instalatoarele ambelor proiecte creează fișierele din `ai.example.toml` dacă lipsesc și
  **nu le suprascriu niciodată**.

**Formatul `ai.toml`**

```toml
# Modelul folosit când o sarcină nu are altă setare
implicit = "gemini:gemini-3.8-flash"

[aliasuri]                       # nume scurte, folosite mai jos și în interfețe
rapid = "gemini:gemini-3.8-flash"
bun   = "gemini:gemini-3.8-flash"
# local = "ollama:<numele modelului din Ollama>"

[sarcini]                        # o sarcină lipsă folosește `implicit`
notite        = "bun"            # Studiu: notițe din PDF / transcrieri
carduri       = "bun"            # Studiu
chat          = "bun"            # Studiu
cuvinte_cheie = "rapid"          # Studiu: pasul 1 din chat
corectura_ocr = "rapid"          # Unelte: ocr-ecran --ai
stil          = "bun"            # Unelte: corecteaza --stil
traducere     = "bun"            # Unelte
cv            = "bun"            # Unelte
buget         = "rapid"          # Unelte: categorisire
rezumat       = "rapid"          # Unelte: rezumatul zilnic

[buget]
lunar_usd = 0                    # 0 = fără limită; contează doar furnizorii cu preț

[furnizori.gemini]
tip = "openai"                   # adaptorul: openai | anthropic
base_url = "https://generativelanguage.googleapis.com/v1beta/openai"
cheie = "GEMINI_API_KEY"         # NUMELE variabilei din .env, nu cheia
cereri_pe_minut = 0              # >0 dacă primești des erori 429
timeout_s = 180
schema_json = "auto"             # auto | da | nu
context_max = 0                  # tokeni; 0 = necunoscut
max_iesire = 8192
pret_intrare_1m = 0.0            # USD / 1M tokeni (0 = gratuit)
pret_iesire_1m = 0.0

[furnizori.ollama]               # modele locale; la fel LM Studio, llama.cpp server
tip = "openai"
base_url = "http://127.0.0.1:11434/v1"
cheie = ""                       # fără cheie
timeout_s = 900                  # modelele locale sunt lente pe CPU
context_max = 8192

# [furnizori.groq]
# tip = "openai"
# base_url = "https://api.groq.com/openai/v1"
# cheie = "GROQ_API_KEY"

# [furnizori.openrouter]
# tip = "openai"
# base_url = "https://openrouter.ai/api/v1"
# cheie = "OPENROUTER_API_KEY"

# [furnizori.openai]
# tip = "openai"
# base_url = "https://api.openai.com/v1"
# cheie = "OPENAI_API_KEY"

# [furnizori.anthropic]
# tip = "anthropic"
# base_url = "https://api.anthropic.com/v1"
# cheie = "ANTHROPIC_API_KEY"
```

Un fișier lipsă sau gol TREBUIE să funcționeze: valoarea implicită e furnizorul `gemini`
de mai sus. Fără cheie, funcțiile AI se opresc cu un mesaj care spune exact ce variabilă
lipsește și în ce fișier; tot restul aplicației merge normal.

**Referințe la modele și rezolvare**

- o referință e `furnizor:model` (despărțită la **primul** `:`, deci `ollama:qwen3:8b` e valid)
  sau numele unui alias;
- ordinea: alegerea explicită (opțiunea `--model` în Unelte, selectorul din interfață în Studiu)
  → `[sarcini]` → `implicit`;
- un alias poate trimite la alt alias (maximum 3 niveluri); ciclurile și furnizorii
  nedeclarați dau eroare clară la pornire, nu la primul apel.

**Adaptoare** (`ai/adaptoare/`)

Interfața unui adaptor:

```python
class Adaptor(Protocol):
    def chat(self, cerere: CerereChat) -> RaspunsChat: ...
    def modele(self) -> list[str]: ...
```

`CerereChat`: model, mesaje (`system` / `user` / `assistant`, text), temperatură, `max_iesire`,
schemă JSON opțională. `RaspunsChat`: text, tokeni de intrare, tokeni de ieșire, dacă tokenii
sunt estimați, motivul opririi.

Adaptoare obligatorii:

- **`openai`** – `POST {base_url}/chat/completions`, `Authorization: Bearer` (doar dacă există
  cheie), `response_format` de tip `json_schema` când există schemă și furnizorul o acceptă,
  tokeni din `usage.prompt_tokens` / `usage.completion_tokens`, modele din `GET {base_url}/models`.
  Acoperă Gemini, OpenAI, Groq, OpenRouter, Mistral, DeepSeek, Ollama, LM Studio,
  llama.cpp server, vLLM.
- **`anthropic`** – `POST {base_url}/messages`, antetele `x-api-key` și `anthropic-version`
  (valoarea din documentația curentă, ținută ca o constantă), mesajul `system` separat,
  `max_tokens` obligatoriu (din `max_iesire`), textul din blocurile de tip `text`, tokeni din
  `usage.input_tokens` / `usage.output_tokens`, modele din `GET {base_url}/models`. JSON-ul
  se cere prin prompt și se validează (`schema_json` tratat ca `nu`).

Un furnizor nou cu API diferit = **un singur fișier** nou în `ai/adaptoare/` plus o intrare în
dicționarul `ADAPTOARE`. Nicio altă parte a codului nu se modifică. Fără SDK-uri de furnizor:
doar `urllib` din biblioteca standard.

**Stratul comun** (`ai/client.py`)

```python
def ruleaza(sarcina: str, mesaje: list[dict], *, model: str | None = None,
            schema: dict | None = None, temperatura: float = 0.3,
            la_progres: Callable[[str], None] | None = None) -> Rezultat
def modele_configurate() -> dict        # aliasuri, sarcini → model rezolvat, furnizori
def listeaza_modele(furnizor: str) -> list[str]
def testeaza(model: str | None = None) -> Diagnostic
def estimeaza_tokeni(text: str) -> int  # len(text) / 3.5, rotunjit în sus
def estimeaza_cost(sarcina: str, tokeni_intrare: int, tokeni_iesire: int) -> float | None
```

Răspunderi:

- **rezolvarea modelului** și încărcarea cheii;
- **limitarea ritmului** per furnizor (`cereri_pe_minut`: pauză minimă între apeluri,
  `time.monotonic()` + lock);
- **reîncercări**: HTTP 429 – până la 4, cu pauza din `Retry-After` sau 5 / 15 / 45 / 90 s;
  HTTP 5xx și erori de rețea temporare – până la 2; alte erori 4xx – fără reîncercare;
  fiecare pauză e anunțată prin `la_progres` („Limită de rată la gemini, reiau în 45 s”);
- **mesaje de eroare în română**, distincte: cheie lipsă (numele variabilei și fișierul),
  cheie invalidă (401/403), model inexistent (404/400 despre model – cu sugestia comenzii
  care listează modelele), text prea lung pentru contextul modelului, buget atins,
  furnizor indisponibil (inclusiv „Ollama nu rulează” pentru adrese locale);
- **JSON structurat**: schema e un dicționar JSON Schema dintr-un subset mic, validat cu un
  validator propriu (fără dependențe): `type`, `properties`, `required`, `items`, `enum`,
  `minItems`, `maxItems`, `minLength`. Cu `schema_json = "auto"`, prima respingere a
  `response_format` (HTTP 400 care menționează formatul sau schema) dezactivează schema pentru
  acel furnizor până la repornire și reia apelul fără ea. Instrucțiunea JSON e pusă **mereu**
  și în prompt, ca orice model să o poată respecta. Răspunsul e curățat (blocuri de cod Markdown,
  text înainte și după primul obiect sau listă) și validat; la eșec, **o singură** reîncercare
  care trimite modelului eroarea de validare;
- **consum**: o linie JSONL per apel reușit:
  `{"t", "aplicatie", "sarcina", "furnizor", "model", "intrare", "iesire", "estimat", "cost_usd"}`;
  costul e 0 dacă ambele prețuri sunt 0;
- **buget**: înainte de apel, dacă `lunar_usd > 0` și suma lunii curente (din ambele aplicații)
  l-a atins, apelul e refuzat;
- **context**: dacă `context_max > 0`, funcțiile care împart texte lungi în bucăți folosesc
  cel mult jumătate din context pentru textul trimis.

**Modele locale**

Ollama, LM Studio sau llama.cpp server se declară ca furnizori `openai`, fără cheie, cu
`timeout_s` mare. Documentația explică faptul că pe un laptop fără placă video dedicată sunt
lente și că modelele mici greșesc mai des, mai ales în română; potrivite pentru sarcinile
`rapid`, mai puțin pentru notițe și carduri.

**Furnizorul implicit: Google Gemini (free tier)**

- cheia se generează gratuit din Google AI Studio și se pune în `~/.config/ai/.env`
  ca `GEMINI_API_KEY=...`;
- endpoint compatibil OpenAI: `https://generativelanguage.googleapis.com/v1beta/openai`,
  autentificare `Bearer`, ieșire structurată documentată prin `response_format` de tip
  `json_schema` (varianta `json_object` nu e documentată și nu se folosește);
- nu are endpoint `/audio/transcriptions`;
- limitele free tier-ului nu sunt publicate în documentație (se văd în AI Studio) și se pot
  schimba; de aici tratarea robustă a erorii 429 și opțiunea `cereri_pe_minut`;
- numele modelelor se schimbă în timp, iar un model retras dă 404 sau 400 – de aici mesajul
  dedicat și comanda de listare a modelelor;
- compatibilitatea OpenAI e marcată de Google ca beta, deci adaptorul folosește doar
  `chat/completions`, `response_format`, `models` și `usage`;
- pe free tier, datele pot fi folosite de Google pentru îmbunătățirea produselor, cu excepții
  regionale descrise în termenii lor; diagnosticul afișează o notă scurtă, fără a bloca nimic.

**Teste ale stratului AI**

Fără rețea și fără chei reale. Două servere false locale (unul în format OpenAI, unul în format
Anthropic) și **aceleași scenarii rulate pe ambele adaptoare**: text simplu, JSON cu schemă,
schemă respinsă cu 400 (fallback), JSON învelit într-un bloc de cod Markdown, JSON invalid urmat de unul valid,
429 cu și fără `Retry-After`, 5xx, 401, model inexistent, răspuns fără `usage`. Plus:
rezolvarea aliasurilor (lanțuri, cicluri, `:` în numele modelului), bugetul, limitarea ritmului
(cu ceas fals), validatorul de schemă, cheie lipsă.

**Specific Unelte**

- sarcinile folosite: `corectura_ocr`, `stil`, `traducere`, `cv`, `buget`, `rezumat`;
- fiecare comandă care folosește AI acceptă `--model <alias sau furnizor:model>`, cu prioritate
  față de `[sarcini]`;
- comenzile de durată afișează mesajele `la_progres` în terminal, pe o singură linie
  actualizată;
- `unelte ai test [model]`, `unelte ai modele <furnizor>`, `unelte ai sarcini`
  (tabel sarcină → model rezolvat), `unelte ai consum [AAAA-LL]` (consumul pe aplicații,
  sarcini și modele);
- `install.sh` creează `~/.config/ai/ai.toml` și `~/.config/ai/.env` (`chmod 600`) din
  `ai.example.toml` dacă lipsesc, fără a le suprascrie.

### 3.4 Prompturile

Implicite în `prompturi/<nume>.md`; personalizate în `~/.config/unelte/prompturi/<nume>.md`,
cu prioritate. Substituție simplă cu `str.format_map` (chei lipsă → șir gol).

### 3.5 Utilitare comune

- `fisiere.nume_liber(cale)` → `nume (2).ext`, `nume (3).ext` etc. dacă există deja;
- `fisiere.scrie_atomic(cale, continut)`;
- `sistem.necesita("pandoc")` → dacă programul lipsește, eroare clară cu comanda de instalare
  pentru distribuția detectată, construită din `distro.toml` (3.6);
- `sistem.notifica(titlu, mesaj, urgent=False)` → `notify-send`, ignorat silențios dacă lipsește
  sau dacă `notificari = false`;
- jurnal în `~/.local/state/unelte/<comanda>.log`, rotit (1 MB × 3).

### 3.6 Distribuții și mediul grafic

**Distribuția** e detectată din `/etc/os-release` (`ID`, apoi `ID_LIKE`): `ubuntu`, `debian`,
`linuxmint`, `pop` → `debian`; `fedora`, `rhel`, `centos` → `fedora`; `arch`, `manjaro`,
`endeavouros` → `arch`. `install.sh --distro debian|fedora|arch` are prioritate; o distribuție
nerecunoscută cere opțiunea explicit. Alegerea se reține în `~/.config/unelte/config.toml`
(`[general].distro`, implicit `"auto"`).

Maparea programelor pe pachete stă în `distro.toml`, nu în cod. Tabelul de mai jos e orientativ
și TREBUIE verificat la implementare pe versiunile curente (ultimul Ubuntu LTS, ultimul Fedora):

| Program | Debian / Ubuntu (`apt`) | Fedora (`dnf`) | Arch (`pacman`) |
|---|---|---|---|
| pandoc | `pandoc` | `pandoc` | `pandoc` |
| LibreOffice Writer | `libreoffice-writer` | `libreoffice-writer` | `libreoffice-fresh` |
| Tesseract + ro + en | `tesseract-ocr tesseract-ocr-ron tesseract-ocr-eng` | `tesseract tesseract-langpack-ron tesseract-langpack-eng` | `tesseract tesseract-data-ron tesseract-data-eng` |
| captură Wayland (wlroots) | `grim slurp` | `grim slurp` | `grim slurp` |
| clipboard Wayland | `wl-clipboard` | `wl-clipboard` | `wl-clipboard` |
| clipboard X11 | `xclip` | `xclip` | `xclip` |
| captură X11 | `maim` | `maim` | `maim` |
| notificări | `libnotify-bin` | `libnotify` | `libnotify` |
| git | `git` | `git` | `git` |
| Java (LanguageTool) | `default-jre-headless` | `java-21-openjdk-headless` | `jre-openjdk-headless` |
| containere (opțional) | `podman` | `podman` | `podman` |
| venv Python | `python3-venv` | (inclus) | (inclus) |

Instalatorul afișează **o singură** comandă (`sudo apt install ...`, `sudo dnf install ...`,
`sudo pacman -S --needed ...`) cu tot ce lipsește, grupat pe comenzile care au nevoie, și o
rulează **doar după confirmare** (sau cu `--da`). Nu rulează niciodată `sudo` fără să fi arătat
comanda.

**Mediul grafic** contează doar pentru `ocr-ecran`. `sistem.mediu_grafic()` alege, în ordine:

| Mediu (detectat din `XDG_SESSION_TYPE`, `XDG_CURRENT_DESKTOP`, `SWAYSOCK`) | Selecție + captură | Clipboard |
|---|---|---|
| Wayland, compozitor wlroots (sway, Hyprland etc.) | `slurp` + `grim` | `wl-copy` |
| Wayland, GNOME (implicit pe Ubuntu și Fedora Workstation) | `gnome-screenshot -a -f <fișier>` | `wl-copy` |
| Wayland, KDE Plasma | `spectacle -r -b -n -o <fișier>` | `wl-copy` |
| X11 | `maim -s <fișier>` | `xclip -selection clipboard` |

Unealta de captură poate fi forțată din config (`[ocr].captura = "auto" | "grim" | "gnome" |
"spectacle" | "maim"`). Dacă metoda aleasă nu e disponibilă, mesajul spune ce lipsește și
sugerează `ocr-ecran --fisier` pe o captură făcută cu unealta sistemului.

---

## 4. `backup` – backup automat cu Git

### 4.1 Rol

Pune automat sub Git folderele importante (notițele din Studiu, repo-urile proiectelor,
exportul bibliografiei din Zotero) și le trimite la toate destinațiile configurate:
GitHub acum, serverul privat (de exemplu Forgejo) mai târziu.

### 4.2 Configurare

```toml
[backup]
interval = "1h"               # folosit de timer
fisier_max_mb = 50            # fișierele mai mari sunt refuzate (GitHub respinge peste 100 MB)

[[backup.repo]]
nume = "notite"
cale = "~/Notite"

[[backup.repo]]
nume = "studiu"
cale = "~/studiu"

[[backup.repo]]
nume = "bibliografie"
cale = "~/Documente/Bibliografie"   # unde Better BibTeX exportă automat fișierul .bib

[backup.zotero]
activ = true
date = "~/Zotero"             # folderul de date Zotero
destinatie = "~/Backup/zotero"
copii_pastrate = 10
```

Destinațiile sunt pur și simplu remote-urile Git ale fiecărui repo (`git remote -v`);
adăugarea serverului privat mai târziu înseamnă doar `git remote add privat ...`.

### 4.3 Comportament

`backup` (fără argumente) rulează, pentru fiecare repo configurat:

1. verifică că e repo Git; dacă nu e, îl sare cu mesaj și sugerează `backup --initializeaza <nume>`;
2. **verificări de siguranță** pe fișierele modificate sau noi:
   - fișiere peste `fisier_max_mb` → repo-ul e sărit, cu lista fișierelor;
   - fișiere care par secrete (nume `.env`, `*.pem`, `id_rsa*`, sau conținut cu
     `-----BEGIN ... PRIVATE KEY-----`, `API_KEY=`, `SECRET=` urmat de o valoare) → repo-ul e sărit;
   - repo-ul e sărit și dacă e în mijlocul unui merge sau rebase;
3. `git add -A`; dacă există modificări: commit cu mesajul
   `backup automat AAAA-LL-ZZ HH:MM` și lista scurtă a fișierelor în corpul mesajului;
4. pentru fiecare remote: `git pull --rebase --autostash`, apoi `git push`;
   la conflict: `git rebase --abort`, notificare urgentă, repo-ul rămâne cu commit-ul local,
   **fără push forțat**;
5. scrie rezultatul în `~/.local/state/unelte/backup-stare.json`
   (ultimul succes și ultima eroare, per repo și per remote).

Pentru Zotero: dacă procesul `zotero` **nu** rulează, copiază `zotero.sqlite` (și
`better-bibtex.sqlite` dacă există) în `destinatie/AAAA-LL-ZZ_HHMM/` și păstrează doar ultimele
`copii_pastrate` copii. Dacă Zotero rulează, sare pasul fără eroare (va încerca la rularea
următoare). Baza Zotero nu intră în Git: e binară și se schimbă des.

Alte opțiuni:

- `backup --stare` – tabel cu ultimul backup reușit pentru fiecare repo și remote,
  evidențiind ce n-a reușit de peste 24 de ore;
- `backup --initializeaza <nume>` – `git init`, un `.gitignore` rezonabil, primul commit;
  remote-ul îl adaugă utilizatorul (afișează comanda de exemplu);
- `backup --doar <nume>` – un singur repo.

Notificare la final doar la erori (succesul e tăcut).

### 4.4 Automatizare

`systemd/unelte-backup.service` + `unelte-backup.timer` (`OnCalendar` după `interval`,
`Persistent=true`, ca o rulare ratată cât laptopul a stat închis să se facă la pornire).

---

## 5. `organizeaza` – organizarea fișierelor

### 5.1 Configurare

```toml
[organizeaza]
surse = ["~/Descărcări", "~/Downloads"]   # cele care nu există sunt ignorate
asteapta_minute = 2           # fișiere modificate mai recent sunt sărite (descărcări în curs)
ignora = ["*.part", "*.crdownload", "*.tmp"]

[[organizeaza.regula]]
nume = "Cursuri management"
extensii = ["pdf", "pptx", "docx"]
cuvinte = ["management", "antreprenor"]   # în numele fișierului (fără diacritice, fără majuscule)
cuvinte_continut = []                      # POATE: în textul primei pagini a PDF-ului
destinatie = "~/Facultate/Management/{an}"
automat = false               # true = rulată și de timer

[[organizeaza.regula]]
nume = "Imagini"
extensii = ["png", "jpg", "jpeg", "webp"]
destinatie = "~/Imagini/{an}-{luna}"
automat = true
```

Variabile în `destinatie`: `{an}`, `{luna}`, `{zi}` (după data modificării fișierului),
`{extensie}`. Prima regulă care se potrivește câștigă. Potrivirea cuvintelor ignoră
majusculele și diacriticele.

### 5.2 Comportament

- `organizeaza` – **doar afișează planul**: fișier → destinație → regula aplicată, plus
  fișierele fără regulă;
- `organizeaza --aplica` – execută mutările;
- `organizeaza --automat` – folosit de timer: aplică doar regulile cu `automat = true`;
- `organizeaza --anuleaza` – mută înapoi fișierele din ultima rulare (dacă sursa e liberă și
  fișierul încă e la destinație);
- `organizeaza --istoric` – ultimele rulări.

Reguli:

- mutările nu suprascriu niciodată (`fisiere.nume_liber`);
- folderele destinație se creează la nevoie;
- fiecare mutare se scrie în `~/.local/state/unelte/organizeaza.jsonl`
  (`{"rulare": id, "din": ..., "in": ..., "regula": ...}`), sursa pentru `--anuleaza`;
- fișierele ascunse și folderele din surse sunt ignorate (doar fișierele de pe primul nivel).

Timer: `unelte-organizeaza.timer`, la fiecare oră, `Persistent=true`.

---

## 6. `ocr-ecran` – text din captură de ecran

### 6.1 Comportament

1. utilizatorul selectează o zonă, iar zona e capturată într-un fișier temporar, cu metoda
   potrivită mediului grafic (3.6);
2. imaginea e mărită de 2 ori înainte de OCR când e mică (sub 1000 px lățime), cu
   `tesseract` însuși sau fără modificare dacă nu se poate, pentru acuratețe la text mic;
3. `tesseract` cu limbile din config (implicit `ron+eng`);
4. curățare minimă: unirea rândurilor rupte în mijlocul propoziției, eliminarea spațiilor
   duble, păstrarea paragrafelor (linie goală);
5. textul în clipboard (`wl-copy` sau `xclip`, după mediu);
6. notificare cu primele ~80 de caractere.

Opțiuni:

- `--fisier imagine.png` – OCR pe o imagine existentă, rezultatul la ieșirea standard;
- `--brut` – fără curățare;
- `--ai` – trece textul prin AI pentru corectarea erorilor tipice de OCR (prompt
  `ocr_corectare.md`, cu instrucțiunea de a nu schimba sensul și de a nu adăuga nimic);
- `--salveaza` – păstrează și captura în `~/Imagini/ocr/`.

Anularea selecției (Esc) iese cu cod 0, fără mesaj de eroare, indiferent de unealta de captură.

### 6.2 Configurare

```toml
[ocr]
limbi = "ron+eng"
captura = "auto"
```

Programe: Tesseract cu limbile română și engleză, unealta de captură și clipboard-ul potrivite
mediului (pachetele în 3.6).

---

## 7. Profiluri de documente

`converteste` și `verifica-format` folosesc același **profil** – un folder cu regulile unui
tip de document (de exemplu lucrările de la facultate, cu un profil separat pentru licență).

Profilurile se caută în `~/.config/unelte/profiluri/<nume>/`, apoi în `profiluri/<nume>/`
din repo. Profilul implicit se setează în config:

```toml
[documente]
profil_implicit = "facultate"
bibliografie = "~/Documente/Bibliografie/biblioteca.bib"   # exportul automat Better BibTeX
```

### 7.1 `profil.toml`

```toml
nume = "Lucrări facultate"

[pagina]
format = "A4"
margini_cm = { sus = 2.5, jos = 2.5, stanga = 3.0, dreapta = 2.0 }
numerotare = true                  # număr de pagină în subsol

[text]
font = "Times New Roman"
marime_pt = 12
spatiere_rand = 1.5
aliniere = "justify"
indent_prima_linie_cm = 1.25

[titluri]
font = "Times New Roman"
marimi_pt = [16, 14, 12]           # Heading 1, 2, 3
numerotate = true

[figuri]
legenda_obligatorie = true

[citari]
stil = "stil.csl"
bibliografie_obligatorie = true
titlu_bibliografie = "Bibliografie"

[pagina_titlu]
activa = true
campuri = ["universitate", "facultate", "titlu", "autor", "coordonator", "oras", "an"]
```

Valorile de mai sus sunt doar exemplu; utilizatorul le completează după ghidul facultății.
`reference.docx` din profil TREBUIE să fie coerent cu `profil.toml` (aceleași fonturi,
margini, spațieri) – `unelte doctor` verifică asta rulând `verifica-format` pe un document
de test generat cu `converteste`.

---

## 8. `converteste` – Markdown → Word / PDF

### 8.1 Utilizare

```
converteste lucrare.md                 # → lucrare.docx
converteste lucrare.md --pdf           # → lucrare.docx și lucrare.pdf
converteste lucrare.md --profil licenta
converteste notita.md --fara-pagina-titlu
```

### 8.2 Comportament

1. citește antetul YAML al fișierului (titlu, autor, coordonator etc.) pentru pagina de titlu;
2. rulează `pandoc`:
   - `--reference-doc` din profil;
   - `--citeproc --bibliography <config> --csl <profil>` dacă documentul conține citări
     (sintaxa pandoc `[@cheie]`, `[@cheie, p. 12]`);
   - metadate `lang: ro-RO`, `reference-section-title` din profil;
   - `--toc` dacă antetul are `cuprins: true`;
   - filtrul `pagina-titlu.lua` dacă pagina de titlu e activă: construiește pagina din
     câmpurile antetului și adaugă un salt de pagină;
   - formulele LaTeX devin ecuații Word native (comportament standard pandoc);
   - căile relative ale imaginilor se rezolvă față de folderul fișierului (`--resource-path`);
3. **PDF**: conversia se face din `.docx` cu LibreOffice
   (`soffice --headless --convert-to pdf --outdir ...`), ca PDF-ul să respecte exact
   formatarea Word. Fără LaTeX. Dacă `soffice` rulează deja ca aplicație deschisă, conversia
   folosește un profil de utilizator temporar (`-env:UserInstallation=file:///tmp/...`)
   ca să nu intre în conflict;
4. dacă documentul are cuprins, POATE actualiza câmpurile (cuprinsul) printr-un macro
   LibreOffice înainte de exportul PDF; altfel documentează că în Word cuprinsul apare după
   „Actualizare câmp”;
5. ieșirea nu suprascrie un fișier deschis: dacă există un fișier de blocare
   LibreOffice/Word (`.~lock.*#`, `~$*`) lângă destinație, scrie cu `nume_liber`;
6. la final rulează automat `verifica-format` pe rezultat și afișează un rezumat de o linie
   (`--fara-verificare` dezactivează).

Citări lipsă (chei care nu există în bibliografie): avertisment cu lista lor, înainte de
rularea pandoc (pandoc doar le-ar marca cu „???” în document).

Programe: `pandoc` și LibreOffice Writer (pachetele în 3.6).

---

## 9. `verifica-format` – verificarea formatării

### 9.1 Utilizare

```
verifica-format lucrare.docx
verifica-format lucrare.docx --profil licenta
verifica-format lucrare.md            # verifică citările față de bibliografie
verifica-format lucrare.docx --raport raport.md
```

### 9.2 Verificări pe `.docx` (cu `python-docx`)

Pentru fiecare regulă din `profil.toml`:

- **pagina**: format, margini (toleranță 0,05 cm), pe fiecare secțiune a documentului;
  numerotare: existența unui câmp `PAGE` în subsol;
- **textul**: pentru paragrafele de corp (stiluri care nu sunt titluri, legende, cuprins,
  bibliografie, tabele), **formatarea efectivă**: font, mărime, spațiere, aliniere, indent.
  Formatarea efectivă se calculează în ordinea: proprietățile run-ului → proprietățile
  paragrafului → stilul paragrafului și lanțul `based_on` → stilul implicit al documentului
  (`docDefaults` din `styles.xml`). Fără această rezolvare, rezultatele ar fi greșite;
- **titlurile**: font și mărime per nivel; ierarhie corectă (fără salt de la Heading 1
  direct la Heading 3);
- **figurile**: fiecare imagine are imediat după ea un paragraf cu stil de legendă
  (`Caption`) sau un text care începe cu „Figura”;
- **citările**: dacă documentul conține câmpuri Zotero (`ADDIN ZOTERO_ITEM`), verifică
  existența câmpului de bibliografie (`ADDIN ZOTERO_BIBL`); altfel, dacă
  `bibliografie_obligatorie`, verifică existența unui titlu egal cu `titlu_bibliografie`
  urmat de cel puțin o intrare.

### 9.3 Verificări pe `.md`

- toate cheile `[@cheie]` există în bibliografia configurată;
- lista intrărilor din bibliografie folosite și a cheilor lipsă;
- antetul are câmpurile cerute de `pagina_titlu.campuri`, dacă pagina de titlu e activă.

### 9.4 Raport

- la terminal: problemele grupate pe categorie, fiecare cu locul (numărul paragrafului și
  primele ~60 de caractere din el), valoarea găsită și valoarea cerută;
- probleme repetate (de exemplu 140 de paragrafe cu același font greșit) se comprimă:
  „140 de paragrafe au Arial 11 în loc de Times New Roman 12 (primul: §12 «...»)”;
- `--raport fisier.md` scrie același conținut în Markdown;
- cod de ieșire 1 dacă există probleme, 0 dacă nu.

Bibliografia citită cu un parser BibTeX minimal propriu (doar cheile intrărilor), fără
dependență nouă.

---

## 10. `corecteaza` – înlocuitor de Grammarly

### 10.1 Componente

1. **LanguageTool local**, ca serviciu systemd de utilizator
   (`unelte-languagetool.service`), care ascultă doar pe `127.0.0.1:8081`, cu origine permisă
   pentru extensia de browser. Instalare identică pe toate distribuțiile: `install.sh` descarcă
   arhiva oficială LanguageTool (versiune fixată în repo, verificată cu SHA-256) în
   `~/.local/share/unelte/languagetool/` și o rulează cu Java din sistem (3.6). Actualizarea e
   un pas manual: schimbi versiunea și suma de control, rulezi `install.sh` din nou.
   Extensia LanguageTool din browser se îndreaptă spre `http://127.0.0.1:8081` din setările
   ei – README explică pașii.
2. Comanda **`corecteaza`**, care folosește serverul local pentru gramatică și ortografie,
   iar AI-ul doar la cerere, pentru stil.

### 10.2 Utilizare

```
corecteaza text.md                  # raport cu greșelile
corecteaza text.md --interactiv     # treci prin fiecare greșeală și alegi corectura
corecteaza text.md --stil           # + rescriere de stil prin AI, rezultat separat
corecteaza lucrare.docx             # doar raport (fără modificări în .docx)
echo "text" | corecteaza -          # de la intrarea standard
```

### 10.3 Comportament

- limba implicită `ro-RO` (config), cu `--limba en-US` pentru alte texte;
- **Markdown**: înainte de trimitere, porțiunile care nu sunt text natural sunt înlocuite
  cu spații de aceeași lungime (antetul YAML, blocurile de cod, codul inline, formulele
  `$...$` și `$$...$$`, URL-urile, sintaxa linkurilor și a imaginilor), ca pozițiile
  raportate de LanguageTool să corespundă exact textului original;
- **.docx**: textul paragrafelor extras cu `python-docx`, verificat pe paragrafe;
  raportul indică numărul paragrafului;
- textele lungi se trimit în bucăți de cel mult 20.000 de caractere, tăiate la granițe de
  paragraf, cu ajustarea pozițiilor;
- **dicționar personal**: `~/.config/unelte/dictionar.txt` (un cuvânt pe linie); greșelile
  de ortografie pentru aceste cuvinte sunt filtrate local. `--adauga-cuvant X` îl adaugă;
- **reguli ignorate**: lista de id-uri de reguli LanguageTool din config;
- `--interactiv`: pentru fiecare problemă afișează contextul cu greșeala evidențiată,
  mesajul și sugestiile numerotate; tastele: `1`–`9` aplică sugestia, `s` sare, `i` ignoră
  regula, `a` adaugă cuvântul în dicționar, `q` termină. Rezultatul se scrie în
  `<nume>.corectat.<ext>`, niciodată peste original (doar pentru `.md` și `.txt`);
- `--stil`: textul (după corecturile gramaticale, dacă s-au făcut) trece prin AI cu
  promptul `stil.md` (păstrează sensul, terminologia și formatarea Markdown; fără adăugiri);
  rezultatul în `<nume>.stil.md` și un rezumat al diferențelor la terminal
  (`difflib`, la nivel de cuvânt, doar primele 30 de modificări);
- serverul local indisponibil → mesaj cu `systemctl --user start unelte-languagetool`.

### 10.4 Configurare

```toml
[corecteaza]
server = "http://127.0.0.1:8081"
limba = "ro-RO"
reguli_ignorate = []
```

---

## 11. `traduce` – traducere prin AI

### 11.1 Utilizare

```
traduce articol.md --in en            # → articol.en.md
traduce rezumat.md --in ro --din en
traduce document.docx --in en         # → document.en.docx
echo "text" | traduce - --in en
```

### 11.2 Comportament

- **Markdown**: se împarte în blocuri (paragrafe, liste, tabele, titluri); blocurile de cod,
  formulele și antetul YAML **nu** se trimit și rămân identice; blocurile se grupează în bucăți
  de ~6.000 de caractere, trimise cu promptul `traducere.md` (păstrează exact sintaxa Markdown,
  linkurile, numerele și formulele inline; traduce doar textul). Rezultatul se reasamblează
  în ordinea originală;
- **.docx**: traducere pe paragrafe și celule de tabel cu `python-docx`, păstrând stilul
  paragrafului; formatarea din interiorul paragrafului (cuvinte îngroșate izolate etc.) se
  pierde – limitarea e documentată în README și afișată la rulare;
- **glosar**: `~/.config/unelte/glosar.toml` cu perechi de termeni per limbă
  (de exemplu `"active circulante" = "current assets"`), inclus în prompt ca listă de
  termeni obligatorii, ca traducerile să fie consecvente între documente;
- validare: numărul de blocuri primite trebuie să fie egal cu cel trimis (cererea și
  răspunsul folosesc JSON cu schemă: listă de `{id, text}`); la nepotrivire, bucata se
  retrimite o dată, apoi comanda se oprește cu eroare, fără fișier parțial;
- rezultatul nu suprascrie originalul.

---

## 12. `cv` – CV adaptat pe anunț și evidența aplicărilor

> **Modul amânat.** Rămâne în specificație ca referință, dar **nu se implementează** în etapele
> curente (vezi 18) și nu se activează. Când utilizatorul cere explicit implementarea, modulul
> se construiește după această secțiune, rămâne **dezactivat implicit** (`[module]` în 3.1) și
> nu instalează lansator sau timer până nu e activat.

### 12.1 Rol

Înlocuiește generatoarele de CV și scrisori cu abonament. Experiența se scrie **o singură dată**
într-un fișier structurat; pentru fiecare anunț, AI-ul alege și reformulează doar ce e relevant,
fără să inventeze nimic, iar `converteste` produce documentele finale.

### 12.2 Date

```toml
[cv]
date = "~/Documente/Cariera/cv.yaml"     # sursa unică
aplicari = "~/Documente/Cariera/Aplicari" # un folder per aplicare
profil = "cv"                              # profil de document (7), cu șablonul de CV
reaminteste_dupa_zile = 14
```

`cv.yaml` (exemplu creat de `cv initializeaza`, cu comentarii):

```yaml
persoana: {nume: "", email: "", telefon: "", oras: "", linkuri: [github, linkedin]}
rezumat: "Student la Informatică Economică, interesat de audit și analiza datelor."
experienta:
  - id: exp-practica-2026
    rol: "Practicant audit"
    organizatie: "..."
    perioada: "iul. 2026 – sep. 2026"
    realizari:
      - id: r1
        text: "Am verificat 120 de facturi pentru conformitate TVA."
        etichete: [audit, excel, tva]
proiecte:
  - id: pr-studiu
    nume: "Studiu – aplicație de învățare"
    tehnologii: [Python, FastAPI, SQLite]
    realizari: [{id: r1, text: "...", etichete: [python, sql]}]
educatie: [...]
competente: {tehnice: [SQL, Python, Excel], limbi: ["engleză C1"]}
certificari: [...]
```

Fiecare realizare are un `id` stabil, folosit pentru verificarea că AI-ul nu inventează (12.4).

### 12.3 Comenzi

```
cv initializeaza                       # creează cv.yaml de exemplu (nu suprascrie)
cv genereaza [--limba en] [--pdf]      # CV-ul general, fără AI
cv adapteaza anunt.txt [--pdf]         # sau `-` pentru textul lipit la intrarea standard
cv adapteaza --url https://...         # încearcă să descarce anunțul (vezi mai jos)
cv aplicari                            # tabelul aplicărilor
cv stare <id> interviu                 # trimis | interviu | oferta | respins | retras
cv reaminteste                         # aplicările fără răspuns de peste N zile
```

`--url` descarcă pagina cu `urllib` și extrage textul cu `html.parser` din biblioteca standard;
dacă textul extras e sub 500 de caractere (pagini care cer autentificare sau sunt generate
în browser), comanda cere textul lipit și nu insistă.

### 12.4 `cv adapteaza`

1. citește `cv.yaml` și anunțul;
2. apel AI (sarcina `cv`, schemă JSON):
   `{firma, post, cuvinte_cheie_anunt[], selectie: [{id_realizare, text_reformulat}],
   ordine_sectiuni[], rezumat_adaptat, competente_relevante[], lacune[], scrisoare}`;
3. **verificarea anti-invenție** (fără AI, obligatorie):
   - fiecare `id_realizare` trebuie să existe în `cv.yaml`;
   - numerele, procentele, numele de tehnologii și de organizații din `text_reformulat` și din
     `rezumat_adaptat` trebuie să apară în realizarea sursă sau în `cv.yaml`; altfel elementul
     e respins și înlocuit cu textul original, cu avertisment;
   - competențele trebuie să existe în `competente`;
   - `lacune` (cerințe din anunț fără acoperire în CV) se afișează utilizatorului și **nu** se
     adaugă în CV;
4. construiește CV-ul și scrisoarea ca Markdown și le convertește prin `converteste` cu profilul
   `cv` (fără pagină de titlu);
5. creează folderul `Aplicari/AAAA-LL-ZZ Firma – Post/` cu `cv.docx`, `scrisoare.docx`
   (și PDF-urile, cu `--pdf`), `anunt.md` (anunțul salvat), `analiza.md` (cuvinte cheie
   acoperite și neacoperite, lacune, ce s-a respins la verificare) și `aplicare.toml`
   (`firma`, `post`, `data`, `stare = "pregatit"`, `istoric = []`);
6. afișează calea folderului și rezumatul analizei.

Scrisoarea: maximum o pagină, în limba anunțului, fără formule generice; promptul `cv_scrisoare.md`
cere explicit să se folosească doar fapte din `cv.yaml`.

### 12.5 Evidența aplicărilor

Sursa de adevăr sunt fișierele `aplicare.toml` din fiecare folder (fără bază de date).
`cv aplicari` le citește și afișează tabelul: dată, firmă, post, stare, zile de la ultima
schimbare. `cv stare` actualizează starea și adaugă în `istoric` data schimbării.
`cv reaminteste` e rulat și de timer-ul săptămânal `unelte-cv.timer` și trimite o notificare
doar dacă există aplicări de urmărit.

---

## 13. `buget` – buget personal din extrasele bancare

> **Modul amânat.** Rămâne în specificație ca referință, dar **nu se implementează** în etapele
> curente (vezi 18) și nu se activează. Când utilizatorul cere explicit implementarea, modulul
> se construiește după această secțiune, rămâne **dezactivat implicit** (`[module]` în 3.1) și
> nu instalează lansator sau timer până nu e activat.

### 13.1 Rol

Înlocuiește aplicațiile de buget cu abonament: imporți extrasul CSV din aplicația băncii,
tranzacțiile sunt categorisite (reguli, apoi AI doar pentru ce nu se potrivește) și primești
un raport lunar, cu abonamentele recurente detectate. Totul rămâne local, în fișiere text.

### 13.2 Date

```toml
[buget]
folder = "~/Documente/Buget"
moneda = "RON"
ai = true                    # false = doar reguli, fără niciun apel AI
```

```
Buget/
├── banci/<nume>.toml        cum se citește CSV-ul fiecărei bănci
├── categorii.toml           lista categoriilor (+ subcategorii) și bugetele lunare
├── reguli.toml              reguli de categorisire, în ordine
├── extrase/                 CSV-urile originale importate (neschimbate)
├── tranzactii/AAAA-LL.csv   tranzacțiile normalizate și categorisite
└── rapoarte/AAAA-LL.md      rapoartele lunare
```

Folderul e potrivit pentru `backup` (4), cu remote **privat**.

**Profil de bancă** (`banci/<nume>.toml`) – formatele diferă între bănci și se schimbă în timp,
deci nu se scriu în cod:

```toml
nume = "Banca mea"
codificare = "utf-8"          # sau "cp1250", "iso-8859-2"
separator = ";"
sari_randuri = 0
format_data = "%d.%m.%Y"
separator_zecimal = ","
coloane = {data = "Data", descriere = "Detalii", suma = "Suma", debit = "", credit = ""}
semn = "suma"                 # suma (negativ = cheltuială) | debit_credit
```

`buget banca noua extras.csv` detectează codificarea și separatorul, afișează antetul și primele
rânduri și scrie un profil-schiță de completat. Repo-ul conține doar un exemplu generic,
marcat clar ca exemplu, fără a pretinde că descrie o bancă anume.

### 13.3 Comenzi

```
buget importa extras.csv --banca <nume>   # normalizare + categorisire
buget revizuieste                         # tranzacțiile nesigure, una câte una
buget raport [AAAA-LL] [--html]
buget abonamente
buget cauta "mega image" [--luna AAAA-LL]
```

### 13.4 Import și categorisire

1. copiază CSV-ul original în `extrase/` (cu `nume_liber`);
2. normalizează: dată ISO, sumă ca număr cu semn, descriere curățată (spații), `id` = hash din
   (dată, sumă, descriere normalizată, bancă); tranzacțiile deja existente sunt sărite, deci
   reimportul aceluiași extras e sigur;
3. categorisire, în ordine:
   - **reguli** din `reguli.toml` (`contine`, `regex`, `suma_min`/`suma_max`, `categorie`);
   - **AI** (sarcina `buget`, dacă `ai = true`) doar pentru ce a rămas, în loturi de 50, cu
     categoriile permise date în schemă (`enum`) și o încredere 0–1. Se trimit **doar** descrierea
     și suma; secvențele de peste 6 cifre (IBAN, numere de card, referințe) sunt mascate înainte;
   - încredere sub 0,7 sau eroare AI → `Necategorizat`;
4. scrie lunile afectate în `tranzactii/AAAA-LL.csv` (atomic, sortat după dată).

`buget revizuieste` arată fiecare tranzacție `Necategorizat` sau categorisită de AI cu încredere
mică: alegi categoria cu o tastă și poți crea pe loc o regulă („Toate tranzacțiile care conțin
«MEGA IMAGE» → Alimente?”). În timp, regulile acoperă aproape tot și apelurile AI scad spre zero.

### 13.5 Abonamente

Detecție fără AI: același comerciant (descriere normalizată, fără cifre), sume apropiate
(±10%), cel puțin 3 apariții la intervale aproximativ lunare (25–35 de zile) sau anuale.
`buget abonamente` arată costul lunar al fiecăruia, ultima plată, abonamentele noi și
creșterile de preț față de plata anterioară.

### 13.6 Raport lunar

`rapoarte/AAAA-LL.md` (și, cu `--html`, un fișier HTML autonom cu grafice SVG simple, fără
biblioteci externe):

- venituri, cheltuieli, sold;
- cheltuieli pe categorii, comparate cu bugetul din `categorii.toml` și cu media ultimelor 3 luni;
- cei mai mari comercianți;
- abonamentele active și costul lor lunar;
- tranzacțiile încă necategorisite.

Tranzacțiile în altă monedă păstrează suma originală; dacă extrasul are și suma în RON, raportul
o folosește; altfel sunt listate separat, fără conversie automată.

Timer opțional `unelte-buget.timer`: în prima zi a lunii generează raportul lunii precedente și
trimite o notificare.

---

## 14. `rezumat` – rezumatul zilnic din surse RSS

### 14.1 Rol

Înlocuiește funcțiile plătite de rezumat din cititoarele de știri: o dată pe zi, citește sursele
tale (RSS / Atom), alege ce e relevant pentru interesele tale și scrie o notiță scurtă cu
rezumatele și linkurile.

### 14.2 Configurare

```toml
[rezumat]
ora = "07:30"
iesire = "~/Notite/Rezumate"         # folderul de notițe Studiu sau oricare altul
interese = "audit și securitate crypto, piața muncii pentru juniori IT, educație financiară"
max_pe_subiect = 5
text_complet = false                 # true = descarcă și articolul, nu doar descrierea din feed

[[rezumat.subiect]]
nume = "Securitate crypto"
surse = ["https://exemplu.org/feed.xml"]

[[rezumat.subiect]]
nume = "Carieră"
surse = ["https://exemplu.ro/rss"]
```

### 14.3 Comportament

1. descarcă fiecare feed cu `urllib`, cu cereri condiționate (`ETag`, `Last-Modified` păstrate
   în starea locală), User-Agent onest, timeout și cel mult o descărcare pe zi per sursă în
   funcționarea normală;
2. citește RSS 2.0 și Atom cu `xml.etree` (fără dependențe); sursele care eșuează sunt notate
   în rezumat la final, fără a opri restul;
3. păstrează doar elementele noi (id-uri văzute în `~/.local/state/unelte/rezumat.json`,
   curățate după 60 de zile);
4. pe subiect, un apel AI (sarcina `rezumat`, schemă JSON) primește titlurile și descrierile
   (cel mult 1.000 de caractere fiecare) și întoarce, pentru cel mult `max_pe_subiect` elemente,
   `{id, relevanta 0–1, rezumat}` (1–2 propoziții în română, doar din textul primit);
5. scrie `AAAA-LL-ZZ.md` în `iesire`, cu antetul
   `tip: rezumat`, `sursa: ai`, `generat_la` (Studiu nu le pune în „De revizuit”), grupat pe
   subiecte: titlu ca link, sursa, rezumatul;
6. notificare: „Rezumatul zilei: N articole noi”.

Fără AI (cheie lipsă, `--fara-ai` sau eroare): notița conține doar titlurile și linkurile,
grupate pe subiecte, cele mai noi primele.

Comenzi: `rezumat` (rulează acum), `rezumat --surse` (verifică fiecare sursă și raportează
cele care nu răspund sau nu sunt feed-uri valide). Timer: `unelte-rezumat.timer`, zilnic la
`ora`, `Persistent=true`.

---

## 15. Servicii instalate (Stirling-PDF, Excalidraw și ChartDB)

Nu se scrie cod pentru ele, doar configurația de rulare:

- `servicii/compose.yml` cu cele trei servicii, porturi legate **doar** la `127.0.0.1`
  (de exemplu `127.0.0.1:8090` pentru Stirling-PDF, `127.0.0.1:8091` pentru Excalidraw și
  `127.0.0.1:8092` pentru ChartDB), `restart: unless-stopped`, volume pentru datele
  Stirling-PDF în `~/.local/share/unelte/stirling/`;
- ChartDB: funcțiile AI proprii rămân dezactivate (nu se configurează nicio cheie);
  importul schemei, editarea diagramei și exportul SQL funcționează fără ele. Diagramele se
  salvează în browser, deci README recomandă exportul periodic al diagramelor importante
  (fișier JSON sau SQL) într-un folder inclus în `backup`;
- Excalidraw: la fel, desenele stau în browser; README recomandă salvarea ca fișier
  `.excalidraw` și exportul SVG lângă notițe;
- imaginile cu **tag de versiune fixat** (nu `latest`), alese la implementare din
  versiunile stabile curente; actualizarea e un pas manual documentat în README
  (schimbi tag-ul, `docker compose pull && docker compose up -d`);
- `install.sh --servicii` le pornește dacă Docker sau Podman e instalat; altfel afișează
  instrucțiunile și continuă fără ele;
- `unelte doctor` verifică dacă porturile răspund.

Stirling-PDF folosește pentru OCR propriul Tesseract din imagine; nu depinde de cel de pe sistem.

Fiecare unealtă de diagrame are un singur rol, ca să nu existe dublură:

| Unealtă | Pentru ce | Unde trăiește rezultatul |
|---|---|---|
| Mermaid în notițele Studiu | diagrame **simple** care fac parte din materie: un flux, o ierarhie, o schemă ER mică de examen | ca text în notiță, versionat cu Git |
| Excalidraw (Unelte) | schițe **libere**: arhitecturi, idei, hărți mentale | fișierul `.excalidraw` și exportul SVG/PNG, salvat lângă notiță |
| ChartDB (Unelte) | **proiectarea reală** a unei baze de date: tabele, chei, relații, SQL | diagrama în ChartDB, exportul SQL în proiect și o imagine în notiță |

Regula de alegere: dacă diagrama trebuie să apară în notiță și să se modifice odată cu ea,
e Mermaid; dacă e un desen liber, e Excalidraw; dacă se termină cu un script SQL, e ChartDB.
Imaginile exportate (SVG, PNG) se pun în folderul materiei și se inserează în notiță cu
`![descriere](fisier.svg)`, comportament deja suportat.

---

## 16. Instalare și diagnoză

### 16.1 `install.sh`

Idempotent (rulat de mai multe ori dă același rezultat). Pași:

1. detectează distribuția (sau folosește `--distro`) și verifică Python ≥ 3.11 și modulul `venv`;
2. creează `.venv` și instalează `requirements.txt` (doar dacă s-a schimbat față de ultima instalare);
3. creează `~/.config/unelte/` cu `config.toml` (din exemplu), `dictionar.txt`, `glosar.toml`
   și `~/.config/ai/` cu `ai.toml` și `.env` (`chmod 600`), dacă lipsesc – **nu le suprascrie
   niciodată**;
4. scrie lansatoarele în `~/.local/bin/` și avertizează dacă folderul nu e în `PATH`;
5. instalează unitățile systemd de utilizator din `systemd/` (cu căile reale completate)
   și activează timer-ele; `--fara-systemd` sare pasul;
6. verifică programele de sistem și afișează **o singură** comandă de instalare pentru
   distribuția detectată, cu tot ce lipsește, grupat pe comenzile care au nevoie; o rulează
   doar după confirmare (3.6);
7. descarcă LanguageTool dacă lipsește sau dacă versiunea fixată s-a schimbat (10.1);
8. la final rulează `unelte doctor`.

`install.sh --dezinstaleaza` oprește și elimină unitățile systemd și lansatoarele;
configurația și datele rămân.

### 16.2 `unelte doctor`

Tabel cu fiecare comandă și starea ei (gata / lipsește X / neconfigurat), plus:

- distribuția și mediul grafic detectate, cu metoda de captură aleasă pentru `ocr-ecran`;
- AI: `ai.toml` valid, fiecare furnizor folosit de o sarcină are cheia prezentă (fără a o
  afișa), testul unui apel minim per furnizor folosit (`--fara-retea` îl sare);
- serverul LanguageTool răspunde;
- timer-ele systemd active și ultima lor rulare;
- `backup --stare` pe scurt;
- serviciile din compose răspund (dacă sunt instalate);
- coerența profilului implicit (vezi 7.1).

---

## 17. Teste

`pytest`, fără rețea și fără cheie. Dublurile:

- **AI fals**: cele două servere false din 3.3 (format OpenAI și format Anthropic);
- **LanguageTool fals**: server HTTP local care întoarce potriviri predefinite pentru `/v2/check`;
- **procese externe**: `sistem.ruleaza` înlocuit în teste, cu verificarea argumentelor;
  testele care chiar au nevoie de `pandoc`, `git` sau `tesseract` sunt marcate și sărite
  automat dacă programul lipsește.

Acoperire minimă:

- `backup`: commit și push pe un remote bare local; refuzul fișierelor mari și al secretelor;
  conflictul nu duce la push forțat; rotația copiilor Zotero; Zotero pornit → pas sărit;
- `organizeaza`: plan fără modificări; `--aplica`; fără suprascriere; `--anuleaza`;
  fișiere recente sărite; potrivire fără diacritice;
- `ocr-ecran`: curățarea textului; anularea selecției;
- `converteste`: argumentele pandoc corecte per profil; avertismentul pentru citări lipsă;
- `verifica-format`: documente `.docx` generate în test cu probleme cunoscute (margini,
  font moștenit din stil, legendă lipsă, salt de nivel la titluri) și un document corect;
  rezolvarea formatării efective prin lanțul de stiluri;
- `corecteaza`: mascarea Markdown păstrează pozițiile; dicționarul personal filtrează;
  bucățile lungi au pozițiile ajustate corect; rezultatul nu suprascrie originalul;
- `traduce`: blocurile de cod și formulele rămân identice; nepotrivirea numărului de blocuri
  e detectată;
- stratul AI: scenariile din 3.3, rulate pe ambele adaptoare; `--model` are prioritate;
- distribuții și mediu grafic: detectarea din fișiere `os-release` de test (Ubuntu, Fedora,
  Arch, Mint, necunoscută), comenzile generate din `distro.toml`, alegerea uneltei de captură
  din variabile de mediu simulate;
- `cv` *(la implementarea modulului amânat)*: verificarea anti-invenție respinge un număr, o tehnologie și un id de realizare
  inexistente; folderul aplicării conține toate fișierele; `cv reaminteste` respectă pragul;
- `buget` *(la implementarea modulului amânat)*: un profil de bancă cu `cp1250`, `;` și virgulă zecimală; reimportul aceluiași extras
  nu dublează nimic; regulile au prioritate față de AI; mascarea secvențelor lungi de cifre;
  detecția abonamentelor (lunar, anual, creștere de preț); raportul fără AI;
- `rezumat`: RSS 2.0 și Atom din fișiere locale, elementele văzute nu se repetă, cererile
  condiționate, sursa defectă nu oprește restul, notița fără AI;
- `install.sh`: rulat de două ori nu suprascrie configurația (test într-un `HOME` temporar).

---

## 18. Etape de implementare

Fiecare etapă se termină cu testele ei trecând și cu `unelte doctor` raportând corect starea.

1. **Fundație**: structura repo-ului, `install.sh` cu detectarea distribuției și `distro.toml`,
   config, stratul AI comun (3.3) cu ambele adaptoare și comenzile `unelte ai ...`, `comun/`,
   lansatoare, `unelte doctor`, infrastructura de teste. *Gata când:* `install.sh` merge pe
   Ubuntu și pe Fedora (verificat cel puțin în containere), iar schimbarea modelului din
   `ai.toml` sau cu `--model` nu cere nicio modificare de cod.
2. **`backup`** + timer. *Gata când:* o modificare în `~/Notite` ajunge pe GitHub în cel mult
   o oră fără nicio intervenție, iar un fișier `.env` pus din greșeală în folder blochează backup-ul
   cu notificare.
3. **`organizeaza`** + timer. *Gata când:* planul afișat corespunde exact cu ce face `--aplica`,
   iar `--anuleaza` readuce totul.
4. **`ocr-ecran`**. *Gata când:* textul dintr-un slide în română ajunge în clipboard cu diacritice,
   pe sway și pe GNOME.
5. **`converteste`**. *Gata când:* un `.md` cu titluri, formule, o imagine și citări devine un
   `.docx` cu pagina de titlu și bibliografie, iar `--pdf` produce un PDF identic ca aspect.
6. **`verifica-format`**. *Gata când:* documentul generat la etapa 5 trece fără probleme, iar un
   document cu formatare greșită primește un raport comprimat și ușor de citit.
7. **`corecteaza`** + serviciul LanguageTool. *Gata când:* extensia din browser folosește serverul
   local, iar comanda raportează corect greșelile dintr-un `.md` cu formule și cod.
8. **`traduce`**. *Gata când:* un `.md` cu tabele, cod și formule e tradus fără să se strice
   structura.
9. **`rezumat`** + timer. *Gata când:* notița zilei apare la ora configurată, fără duplicate de
   la o zi la alta, și se vede în Studiu fără să apară în „De revizuit”.
10. **Servicii**: `compose.yml` cu Stirling-PDF, Excalidraw și ChartDB, `install.sh --servicii`,
    verificarea din `doctor`. *Gata când:* toate trei se deschid pe `127.0.0.1` după o repornire
    a laptopului, fără intervenție.

**Etape amânate** (doar la cererea explicită a utilizatorului; până atunci nu se implementează):

- **A. `cv`** + timer. *Gata când:* un anunț lipit produce folderul aplicării cu CV și scrisoare,
  iar o realizare inventată de model e respinsă și semnalată; modulul rămâne dezactivat până la
  `[module].cv = true`.
- **B. `buget`** + timer. *Gata când:* două luni de extrase reale sunt importate, abonamentele
  recurente sunt găsite, iar după `buget revizuieste` reimportul nu mai face apeluri AI pentru
  aceiași comercianți; modulul rămâne dezactivat până la `[module].buget = true`.

---

## 19. În afara scopului

- aplicația **Studiu** (are specificația ei);
- pregătirea de interviu și exersarea limbilor străine (proiect separat, planificat pentru
  mai târziu; va putea folosi același strat AI);
- proiectele de crypto și audit (scrise separat de utilizator);
- hub-ul personal (video, muzică, galerie, aplicație Flutter);
- scurtături de tastatură în mediul grafic;
- interfață grafică pentru comenzi.
