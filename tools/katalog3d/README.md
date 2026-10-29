# Umumiy 3D katalog (NASA'dan tashqari)

Taqdimotlarga tayyor 3D modellar: tarix, biologiya, san'at, arxitektura, transport, texnika,
geografiya, astronomiya va boshqalar. Har model PowerPoint'ga mos `.glb` qilib tayyorlanadi.

| Fayl | Nima |
|---|---|
| `data/katalog3d/katalog.json` | Yakuniy ro'yxat: o'zbekcha nom, fan, litsenziya, muallif, `attribution`, fayl yo'li, uchburchak, hajm |
| `data/katalog3d/tanlov.jsonl` | Yuklash ro'yxati: har model qayerdan olinadi (manba URL) |
| `data/katalog3d/preview/<id>.jpg` | Har model rasmi (384×384) — botda tanlash uchun |
| `services/katalog3d.py` | `qidir()`, `model_yoli()`, `joylash()` — slaydga qo'yish |
| `tools/katalog3d/yukla.sh` | Serverga yuklash (bitta buyruq) |

## Serverga yuklash

```bash
bash tools/katalog3d/yukla.sh --max 30     # avval sinov
nohup bash tools/katalog3d/yukla.sh > katalog3d.log 2>&1 &    # hammasi
```

Kerak: `python3`, `node` 18+ va `npm`, `huggingface.co` hamda `3d-api.si.edu` ga internet. Kalit kerak emas.
Modellar `data/katalog3d_modellar/` ga tushadi (`KATALOG3D_DIR` bilan boshqa joy). Hammasi ~15 GB,
8 yadroli serverda ~1 soat. Uzilsa qayta ishga tushiring: tayyorlari o'tkazib yuboriladi. Oxirida
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
   va fan berilgan. Takrorlar olib tashlangan.
3. Smithsonian: CC0 paketlardan muzey buyumlari, qazilmalar, hayvon va o'simlik namunalari. Marjon va
   chig'anoqlardan har turkumdan bittadan olingan.

## Konvertatsiya (`glb_tayyorla.mjs`)

Draco va meshopt siqish yechiladi, WebP/KTX2 teksturalar JPEG/PNG ga o'tkaziladi (PowerPoint
ularni o'qimaydi). Teksturalar ≤ 2048 px, to'r ≤ 200 ming uchburchak qilinadi. Node transformlari
geometriyaga o'tkaziladi, shunda `services/med3d/glb.bounds()` haqiqiy chegara qutisini beradi va
model ramkada markazda turadi. Skelet yoki animatsiyali modellarga bu bosqich tegmaydi
(`pishirilgan: false`).

Preview rasmlar: `node tools/katalog3d/rasm.mjs <katalog> <model-viewer.min.js> --hajm 384`
(Playwright va `@google/model-viewer` kerak; serverda shart emas, rasmlar git'da bor).
