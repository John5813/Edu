# Umumiy 3D katalog (NASA'dan tashqari)

**2059 ta model**, hammasi ~12,4 GB: Objaverse/Sketchfab — 1683, Smithsonian — 376.
Litsenziya: CC BY 4.0 — 1537, CC0 — 522.

| Fan | Soni |
|---|---|
| biologiya | 683 |
| tarix | 387 |
| san'at | 184 |
| arxitektura | 174 |
| transport | 173 |
| texnika | 138 |
| geografiya | 96 |
| astronomiya | 47 |
| oshxona | 38 |
| fizika | 37 |
| informatika | 35 |
| musiqa | 32 |
| tibbiyot | 19 |
| sport | 10 |
| kimyo | 3 |
| adabiyot | 2 |
| matematika | 1 |

Taqdimotlarga tayyor 3D modellar: tarix, biologiya, san'at, arxitektura, transport, texnika,
geografiya, astronomiya va boshqalar. Har model PowerPoint'ga mos `.glb` qilib tayyorlanadi.

| Fayl | Nima |
|---|---|
| `data/katalog3d/katalog.json` | Yakuniy ro'yxat: o'zbekcha nom, fan, litsenziya, muallif, `attribution`, fayl yo'li, uchburchak, hajm |
| `data/katalog3d/tanlov.jsonl` | Yuklash ro'yxati: har model qayerdan olinadi (manba URL) |
| `data/katalog3d/preview/<id>.jpg` | Har model rasmi (384×384) — botda tanlash uchun |
| `data/katalog3d/mask/<id>.png` | Rasmning shaffoflik niqobi — 3D ob'ekt ichidagi zaxira rasm fonsiz bo'lishi uchun |
| `services/katalog3d.py` | `qidir()`, `model_yoli()`, `joylash()` — slaydga qo'yish |
| `tools/katalog3d/yukla.sh` | Serverga yuklash (bitta buyruq) |

## Serverga yuklash

```bash
bash tools/katalog3d/yukla.sh --max 30     # avval sinov
nohup bash tools/katalog3d/yukla.sh > katalog3d.log 2>&1 &    # hammasi
```

Kerak: `python3`, `node` 18+ va `npm`, `huggingface.co` hamda `3d-api.si.edu` ga internet. Kalit kerak emas.
Modellar `data/katalog3d_modellar/` ga tushadi (`KATALOG3D_DIR` bilan boshqa joy). Hammasi ~12,5 GB,
4 yadroli serverda ~15–20 daqiqa (asosan konvertatsiya). Uzilsa qayta ishga tushiring: tayyorlari o'tkazib yuboriladi. Oxirida
`tekshir.py` nechta model borligini aytadi.

## Manbalar va litsenziya

- **Objaverse 1.0** (Sketchfab, `allenai/objaverse`): faqat **CC0** va **CC BY 4.0**. NC, ND va SA
  litsenziyalilar olinmagan, chunki Edufayl pullik xizmat.
- **Smithsonian Open Access**: faqat yozuvida `CC0` deb belgilangan 3D paketlar (rasmiy Open Access
  ro'yxatidan tekshirilgan).

CC BY modellarda muallifni ko'rsatish **majburiy**. `joylash()` model ostiga `attribution` yozuvini
("3D: Muallif · CC BY 4.0") o'zi qo'yadi. To'liq matn `attribution_full` da — uni "Manbalar" slaydiga
qo'shing. Har model papkasida `LICENSE.txt` ham bor.

## Qanday saralangan

1. `objaverse_nomzod.py`: Objaverse'ning 800 mingga yaqin yozuvidan faqat CC0/CC BY, ≥10 like,
   2000–3 mln uchburchak, 18+ emas. O'yinchoq, qo'g'irchoq, o'yin va multfilm qahramonlari, anime,
   Rubik kubi, low-poly/stylized, AI modellar, qurol, sci-fi va fantasy so'zlar bo'yicha chiqarib tashlangan.
   Kategoriya kvotasi bor, bir muallifdan ko'pi bilan 20 ta.
2. Qolgan ~3250 nomzod qo'lda ko'rib chiqilgan: ta'limga mosi qoldirilgan, har biriga o'zbekcha nom
   va fan berilgan. Takrorlar, haykalcha/suvenir/maskot, shaxmat va o'yin konsollari ham olib tashlangan.
3. Smithsonian: CC0 paketlardan muzey buyumlari, qazilmalar, hayvon va o'simlik namunalari. Marjon va
   chig'anoqlardan har turkumdan bittadan olingan.
4. Konvertatsiyadan keyin har model chizib ko'rilgan: rasmi bo'sh, juda mayda yoki tarqoq chiqqanlari
   va 600 ming uchburchakdan pastga soddalashmaganlari katalogdan chiqarilgan.

## Konvertatsiya (`glb_tayyorla.mjs`)

Draco va meshopt siqish yechiladi, WebP/KTX2 teksturalar JPEG/PNG ga o'tkaziladi (PowerPoint
ularni o'qimaydi). Eski spec/gloss materiallar metal/rough ga o'tkaziladi (aks holda PowerPoint'da model oq chiqadi).
Teksturalar ≤ 2048 px, to'r ~200 ming uchburchakka soddalashtiriladi. Asosiy massadan uzoqdagi mayda
bo'laklar (ramkani buzadigan) olib tashlanadi. Node transformlari
geometriyaga o'tkaziladi, shunda `services/med3d/glb.bounds()` haqiqiy chegara qutisini beradi va
model ramkada markazda turadi. Skelet yoki animatsiyali modellarga bu bosqich tegmaydi
(`pishirilgan: false`).

Preview rasmlar: `node tools/katalog3d/rasm.mjs <katalog> <model-viewer.min.js> --hajm 384`
(Playwright va `@google/model-viewer` kerak; serverda shart emas, rasmlar git'da bor).

Niqoblar (`data/katalog3d/mask/<id>.png`): xuddi shu buyruq `--maska` bilan fonsiz chizadi, keyin
`python tools/katalog3d/maska.py <katalog>` shaffoflik kanalini yig'adi. 3D taqdimotda har 3D ob'ekt
ichidagi zaxira rasm (3D ko'rinmaydigan dasturlar uchun majburiy) shu niqob bilan fonsiz qilinadi.

## 3D taqdimot (`services/kat3d/`)

Botdagi «🧊 3D taqdimot» tugmasi mavzu so'raydi va to'lovdan oldin tekshiradi: tana tuzilishi bo'lsa —
3D Anatomiya, aks holda shu katalog (va `data/katalog3d/` dagi boshqa `*.json` kataloglar) bo'yicha qidiradi.
Mos modellar topilsa, mijozga nomi va rasmi ko'rsatiladi va taqdimot aynan shular bilan yasaladi.

| Fayl | Nima |
|---|---|
| `qidiruv.py` | AI mavzuni kalit so'zlarga yoyadi → nom/teg bo'yicha 80 nomzod → AI «asosiy» va «yordamchi»ni tanlaydi |
| `reja.py` | AI slaydlar rejasi (kompozitsiya, matn, raqamlar, modellar), tuzatish va fakt tekshiruvi |
| `uslub.py` | 10 ta dizayn uslubi (3D Anatomiya dizayn tizimidan) va fan bo'yicha tanlov |
| `deck.py` | Slaydlar: haqiqiy 3D ob'ektlar, Morph bilan uchib-aylanib o'tish, sahnaga kirish/chiqish |

Modellar hech qachon oddiy rasmga aylantirilmaydi — har slaydda PowerPoint 3D ob'ekti. Tibbiyotdan
boshqa mavzularda modelning qismlari yorliq-chiziq bilan nomlanmaydi. CC BY mualliflari model ostida
va oxirgi slayd izohida yoziladi.

Sozlash: `KAT3D_MODEL` / `KAT3D_SEARCH_MODEL` (AI modeli, bo'sh bo'lsa umumiy), `KAT3D_MAX_MB=42`
(bitta taqdimotdagi modellar hajmi — Telegram 50 MB), `KAT3D_REVIEW=0` (fakt tekshiruvisiz).
