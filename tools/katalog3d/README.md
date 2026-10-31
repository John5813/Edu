# Umumiy 3D katalog (NASA'dan tashqari)

**2074 ta model**, hammasi ~12,5 GB: Objaverse/Sketchfab — 1698, Smithsonian — 376.
Litsenziya: CC BY 4.0 — 1552, CC0 — 522.

O'zbekiston yodgorliklari (15 ta): Registon, Bibixonim, Go'ri Amir, Ulug'bek rasadxonasi sekstanti, Oqsaroy
va Amir Temur dahmasi (Shahrisabz), Amir Temur haykallari, Buxoro madrasasi, oftoba, gilam, non, Teshiktosh.

| Fan | Soni |
|---|---|
| biologiya | 683 |
| tarix | 390 |
| san'at | 187 |
| arxitektura | 181 |
| transport | 173 |
| texnika | 138 |
| geografiya | 96 |
| astronomiya | 48 |
| oshxona | 39 |
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
| `services/kat3d/yukla.py` | Serverga avtomatik yuklash (kerak bo'lganda o'zi) |
| `tools/katalog3d/yukla.sh` | Hammasini birdan yuklash (ixtiyoriy) |

## Serverga yuklash — avtomatik

Qo'lda hech narsa qilish shart emas (3D Anatomiya atlasi kabi). `services/kat3d/yukla.py`:

1. Bot ishga tushganda konvertor paketlari o'zi o'rnatiladi (`npm install`, bir marta, bir necha soniya).
2. Mijoz mavzusiga mos modellar topilishi bilan serverda yo'qlari fonda yuklana boshlaydi: manbadan
   olinib, PowerPoint'ga mos qilib o'giriladi (bitta model ~2–7 soniya, natija katalogdagi bilan bir xil).
   Mijoz to'lov qilguncha odatda tayyor bo'ladi; bo'lmasa taqdimot yig'ish ularni kutadi.
3. Katalog yangilansa (yangi model yoki yangi `data/katalog3d/*.json` katalog) — yangi modellar ham birinchi
   kerak bo'lganda o'zi yuklanadi. Manbasi: `data/katalog3d/*.jsonl` dagi yozuv yoki katalog yozuvidagi
   `manba_url` (to'g'ridan-to'g'ri GLB havola).

Kerak: `node` 18+ va `npm`, `huggingface.co` hamda `3d-api.si.edu` ga internet. Node bo'lmasa bot faqat
diskdagi modellarni taklif qiladi (logda ogohlantirish chiqadi).

Doimiy diskli serverda hammasini oldindan yuklab qo'yish (keyin hech bir buyurtma kutmaydi):

```bash
KATALOG3D_OLDINDAN=1          # bot ishga tushganda fonda, bittadan (buyurtmalar navbati ustun)
bash tools/katalog3d/yukla.sh # yoki qo'lda, hammasi birdan (~12,5 GB, 4 yadroda ~15–20 daqiqa)
```

Modellar `data/katalog3d_modellar/` ga tushadi (`KATALOG3D_DIR` bilan boshqa joy). `KATALOG3D_YUKLOVCHI` —
bir vaqtda nechta model yuklanadi (sukut 3).

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
| `deck.py` | Slaydlar: 14 kompozitsiya, haqiqiy 3D ob'ektlar, Morph bilan uchib-aylanib o'tish, sahnaga kirish/chiqish |
| `yukla.py` | Modellar serverga kerak bo'lganda o'zi yuklanadi (pastda) |

Har varoq boshqacha: AI har slayd uchun mazmuniga mos kompozitsiya tanlaydi — paragraflar, vaqt chizig'i,
ikki ustunli taqqoslash, kartalar, raqamlangan bosqichlar, asosiy fikr/iqtibos, «Bilasizmi?» savoli,
raqamlar, katta model, uchta model, ro'yxat. Ketma-ket bir xil dizayn bo'lmaydi, nuqtali ro'yxat ko'pi bilan
ikki slaydda; matn hajmi ham slayddan slaydga farq qiladi. Shrift joyga moslanadi, sig'magan matn
o'chmaydi — ma'ruzachi izohiga ko'chadi.

Harakat: model qo'shni slaydlarda Morph bilan uchib, aylanib o'tadi; sayyora va globuslar slaydda o'z joyida
juda sekin aylanadi (PowerPoint «Turntable», 40 soniyada bir marta, `KAT3D_TURN_SECONDS`), boshqa modellar
o'tishlar orasida harakatsiz turadi. «Tungi ko'k» uslubida fondagi nur chiziqlari ham Morph bilan suriladi.
Taqqoslash uchun jadval kompozitsiyasi bor (O'zbekiston qatori ajratib ko'rsatiladi).

Modellar hech qachon oddiy rasmga aylantirilmaydi — har slaydda PowerPoint 3D ob'ekti. Tibbiyotdan
boshqa mavzularda modelning qismlari yorliq-chiziq bilan nomlanmaydi. CC BY mualliflari model ostida
va oxirgi slayd izohida yoziladi.

Matnni admin panelda tanlangan premium AI yozadi. Sozlash: `KAT3D_MODEL` / `KAT3D_SEARCH_MODEL` (faqat
majburan boshqa model kerak bo'lsa), `KAT3D_MAX_MB=42`
(bitta taqdimotdagi modellar hajmi — Telegram 50 MB), `KAT3D_REVIEW=0` (fakt tekshiruvisiz).
