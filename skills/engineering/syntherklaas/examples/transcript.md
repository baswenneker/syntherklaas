# Voorbeeld-sessie

Een geïllustreerde walkthrough van wat een gesprek met `/syntherklaas` eruit ziet.
Lengtes en exacte phrasing variëren — dit is geen script maar een schets.

---

**user:** `/syntherklaas`

**claude:** Ik ga je vragen stellen om een datamodel te bouwen en daarvan
synthetische data te genereren. Zeg `stop` op elk moment om af te breken.

Faker-locale? (default: `nl_NL` — accepteert bv. `en_US`, `de_DE`, `fr_FR`, ...)

**user:** nl_NL

**claude:** Top. Welke tabel beginnen we mee?

**user:** klanten

**claude:** Heb je voorbeeld-data om te paste'n, of definiëren we kolommen samen?

**user:**
```
id, naam, bsn, email, leeftijd
1, Jan de Vries, 123456782, jan@bedrijf.nl, 42
2, Anna Bakker, 987654328, anna@firma.nl, 31
```

**claude:** Op basis daarvan stel ik dit voor voor `klanten`:

| col      | provider     | constraint | voorbeeld         |
|----------|--------------|------------|-------------------|
| id       | sequential   | PK         | 1, 2, 3, ...      |
| naam     | faker.name   | NOT NULL   | Pieter Jansen     |
| bsn      | nl.bsn       | UNIQUE     | 123456782         |
| email    | faker.email  | UNIQUE     | x@example.com     |
| leeftijd | numeric_range int (uniform 18–80) | | 42 |

Klopt? (`ok` / `wijzig kolom <naam>`)

**user:** wijzig leeftijd, maak er een normaalverdeling van gem 42 sd 15

**claude:** Aangepast:

| leeftijd | numeric_range int (normal mean=42 sd=15, clipped 18–80) | | 42 |

Foreign keys naar andere tabellen? (bv. `user_id → users.id` of `geen`)

**user:** geen

**claude:** Nog een tabel of klaar?

**user:** ja, orders

**claude:** Heb je voorbeeld-data om te paste'n, of definiëren we kolommen samen?

**user:** samen. id, klant_id, datum, status

**claude:** Voorbeeldwaarden voor `status`?

**user:** open / closed / cancelled

**claude:** Voorgesteld voor `orders`:

| col      | provider                              | constraint | voorbeeld     |
|----------|---------------------------------------|------------|---------------|
| id       | sequential                            | PK         | 1, 2, 3, ...  |
| klant_id | fk → klanten.id                       | NOT NULL   | 1..50         |
| datum    | datetime_range (uniform)              |            | 2024-06-15    |
| status   | categorical [open, closed, cancelled] |            | open          |

Klopt?

**user:** ok

**claude:** Foreign keys nog meer dan `klant_id`?

**user:** nee

**claude:** Nog een tabel of klaar?

**user:** klaar

**claude:** Datamodel:

```
┌─────────────────────────────────┐         ┌─────────────────────────┐
│ klanten                         │ 1     * │ orders                  │
├─────────────────────────────────┤─────────┤─────────────────────────┤
│ id (PK)                INT      │         │ id (PK)         INT     │
│ naam                   STR      │         │ klant_id (FK)   INT ────┤
│ bsn (UQ)               STR      │         │ datum           DATETIME│
│ email (UQ)             STR      │         │ status          STR     │
│ leeftijd               INT      │         └─────────────────────────┘
└─────────────────────────────────┘
```

Klopt?

**user:** ok

**claude:** Volume per tabel:

- `klanten` — hoeveel rijen?

**user:** 50

**claude:** - `orders` — hoeveel per klant? (vast getal, of `poisson 4`, `normal 4±2`, `uniform 0-10`)

**user:** poisson 4, minimum 0

**claude:** Tijdsperiode voor `orders.datum`? (bv. `2024-01-01..2024-12-31`)

**user:** 2024-01-01..2024-12-31

**claude:** Gewichten voor `orders.status`? (`uniform` of bv. `60/30/10`)

**user:** 60/30/10

**claude:** Schema klaar. Genereer preview (10 rijen per tabel)...

```
klanten (50 totaal)

| id | naam              | bsn       | email                  | leeftijd | ...
|  1 | Ali Schellekens   | 391171823 | leonholthuis@example…  |       47 | ...
|  2 | Finn Jansdr-…     | 278248962 | molenvigo@example.net  |       26 | ...
| ...
```

```
orders (≈200 totaal)

| id | klant_id | datum               | status   |
|  1 |        1 | 2024-04-12 09:11:33 | open     |
|  2 |        1 | 2024-08-30 14:22:01 | closed   |
| ...
```

Tevreden? (`ok` / `regenerate` met andere seed / `wijzig` schema)

**user:** ok

**claude:** Output-formaat?

1. losse CSV-bestanden (in een directory)
2. losse XLSX-bestanden (in een directory)
3. één multi-sheet XLSX
4. SQLite database

**user:** 4

**claude:** Output-pad?

**user:** ./demo.db

**claude:** Geschreven:
```
Wrote sqlite -> ./demo.db
  klanten: 50 rows
  orders:  192 rows
```

Wil je dit schema opslaan voor herbruik? (geef een pad, of zeg `nee`)

**user:** ./demo-schema.yaml

**claude:** Opgeslagen als `./demo-schema.yaml`. Volgende keer kun je het
reproduceren met `/syntherklaas ./demo-schema.yaml` — dan toon ik alleen een
confirmatie en draai dezelfde generatie.

---

## Re-invoke met dezelfde YAML

**user:** `/syntherklaas ./demo-schema.yaml`

**claude:** Schema gevonden in `./demo-schema.yaml`:

- 2 tabellen — `klanten` (50 rijen), `orders` (~Poisson(4) per klant ≈ 200)
- locale: `nl_NL`, seed: `42`
- output: `sqlite` → `./demo.db`

Preview (10 rijen per tabel):

```
klanten — id, naam, bsn, email, leeftijd
1, Ali Schellekens, 391171823, leonholthuis@example.com, 47
...
```

OK om te genereren? (`ok` / `annuleer`)

**user:** ok

**claude:** Wrote sqlite → `./demo.db`. Done.
