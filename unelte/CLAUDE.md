# Instrucțiuni pentru agentul de cod

- Documentul de referință al proiectului este `SPECIFICATIE.md`. Citește-l integral înainte de orice modificare.
- Implementează pe etape, în ordinea din secțiunea 18. O etapă e terminată doar când testele ei trec
  și `unelte doctor` raportează corect starea.
- Respectă principiile „set and forget” din secțiunea 1.2: biblioteca standard Python ori de câte ori se
  poate, `python-docx` ca singură dependență de bază, programe de sistem mature în loc de cod propriu,
  systemd de utilizator pentru automatizări. Nu adăuga dependențe sau servicii necerute; dacă una pare
  necesară, explică de ce înainte s-o adaugi.
- AI-ul e modular (secțiunea 3.3): comenzile apelează doar `ai.ruleaza(sarcina, ...)`, acceptă `--model`
  și nu conțin nimic specific unui furnizor sau model. Pachetul `unelte/ai/` trebuie să rămână identic cu
  `app/ai/` din proiectul Studiu; dacă îl modifici, notează în mesajul commit-ului și crește
  `AI_LAYER_VERSION`.
- Sistemele țintă sunt Ubuntu/Debian, Fedora și Arch, cu orice mediu grafic (secțiunea 3.6). Numele
  pachetelor stau în `distro.toml`, nu în cod. Nu rula niciodată `sudo` fără să fi afișat comanda și fără
  confirmare.
- Nu suprascrie și nu șterge niciodată fișierele utilizatorului; comenzile care modifică fișiere au
  implicit modul de previzualizare.
- Mesajele, `--help` și README sunt în română; identificatorii din cod în engleză.
- Testele nu folosesc rețeaua și nici chei reale: folosesc dublurile descrise în secțiunea 17.
- Modulele `cv` și `buget` sunt amânate (secțiunile 12, 13 și 18): nu le implementa până nu ți se cere
  explicit, iar după implementare rămân dezactivate implicit.
- `install.sh` trebuie să rămână idempotent și să nu suprascrie niciodată configurația existentă.
