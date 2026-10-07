# Hand-collected regulations: notes (2026-10-07)

Built from the PDFs Abdulaziz uploaded. The ids and hashes follow spec section 6. `retrieved_at` is set to 2026-10-07.

| File | What | Status |
|---|---|---|
| reg_2ab88e2596_v1.json | Balady/MoMaH Restaurant Requirements, **official English translation** (83k chars, 32 sections) | Clean. The Arabic PDF extracts with swapped letters, so the English version is used (`language_original: en`). The PDF says the Arabic version prevails. The source PDF itself numbers sections 3.4/3.5 as 3.2/3.3 in places, so two refs repeat. Sections 4.3 and 4.5 are merged into the sections before them. |
| reg_ac04b7a838_v1.json | SFDA food poisoning penalties table, Arabic (8k chars) | **Repaired text, check it.** The PDF font swaps letter pairs (المادة came out as املادة). I fixed this with OCR plus rules. Table rows are flattened, so fine amounts and row numbers can sit on separate lines. `published_date`/`effective_date` = 2026-03-30 is the date the SFDA site lists, and the decision says it applies from publication. The decision itself is dated 1447/07/02 AH (2025-12-22). |
| reg_026c0000a3_v1.json | ZATCA E-invoicing Regulation, English (7 articles) | Clean. Article Seven says it takes effect on publication in the Official Gazette, which isn't stated, so `effective_date` is null. |
| reg_6260105d05_v1.json | ZATCA E-Invoicing Implementation Resolution No. 62738, English (62k chars, 9 clauses) | Clean. `published_date` = the decision date, 23/11/1443 AH = 2022-06-22. The uploaded file is the 2023-05-19 amended version. Long, so send only the relevant clauses to Ultra. |
| reg_9a5e4ff6ba_v1.json | ZATCA e-invoicing Wave 25 announcement, English (pasted page text) | Clean. Threshold SAR 187,500; integration deadline 2027-02-01 is an obligation date, not `effective_date`. |
| reg_8cd5ff5b8d_v1.json | SFDA menu rules announcement, Arabic (pasted from oldsfda.sfda.gov.sa/ar/news/3745904) | Clean. `effective_date` 2025-07-01 is stated in the text. The page's body starts mid-sentence ("تهدف إلى…"), as published. The new sfda.gov.sa link now returns 404. |

**Not used:** `101329.pdf` is a scanned image. When OCR'd, it turns out to be an amendment to the **remote-work** rules (العمل عن بعد), not the mall Saudization decision, so it doesn't fit a cafe.
