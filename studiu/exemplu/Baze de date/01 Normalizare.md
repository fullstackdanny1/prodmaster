# Normalizarea bazelor de date

Scopul normalizării: eliminarea redundanței și a anomaliilor de actualizare.

- **1NF** – fiecare atribut conține valori atomice, fără grupuri repetitive.
- **2NF** – 1NF + fiecare atribut non-cheie depinde de **întreaga** cheie primară.
- **3NF** – 2NF + nu există dependențe tranzitive între atribute non-cheie.

```sql
-- Exemplu: separarea clienților de comenzi
CREATE TABLE clienti (id INTEGER PRIMARY KEY, nume TEXT, oras TEXT);
CREATE TABLE comenzi (id INTEGER PRIMARY KEY, client_id INTEGER REFERENCES clienti(id), data DATE);
```
