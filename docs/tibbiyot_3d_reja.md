# Tibbiyot uchun 3D taqdimot — reja (hali amalga oshirilmagan)

Holat: 1-bosqich (prototip) tayyor — `services/med3d/`, demo: bosh suyagi (3 slayd). Botga hali ulanmagan.

## Maqsad
Faqat tibbiyot mavzulari uchun haqiqiy `.glb` 3D modelli PowerPoint taqdimot.
Slayddan slaydga Morph o'tishida 3D qismlar harakatlanadi (masalan: 1-slayd — bosh suyagi to'liq,
2-slayd — tepasi chiqib ketadi, jag' aylanib gorizontal holatga o'tadi). Yorliq-chiziqlar bilan qismlar nomlanadi.

## Kim uchun
Darsda ko'rsatish uchun emas — talabaga tushuntirish uchun. Fayl kompyuter/proyektorda (PowerPoint 365/2019+)
ochiladi. Telefonda 3D ko'rinmaydi — bot foydalanuvchiga "kompyuterda oching" deb aytadi.

## Texnik xulosalar
- Morph bitta modelni bo'laklarga ajrata olmaydi -> har qism alohida GLB, hammasi bir koordinata tizimida,
  qo'shni slaydlarda bir xil nom (`!!cranium`, `!!mandible`).
- python-pptx 3D bilmaydi: `mc:AlternateContent` + `am3d:model3d` + `ppt/media/*.glb`
  (`model/gltf.binary`) + PNG `mc:Fallback`. Spes: MS-ODRAWXML 2.31. Namuna: OfficeCLI.
- Asos: `services/pro3d/build.py` (Morph, `!!obj`) — rasm o'rniga GLB qo'yish.
- PNG zaxira va yorliq koordinatalari: o'zimiz render (Chromium + Three.js) va proyeksiya.

## Model manbasi
- https://github.com/ashemag/human-atlas — BodyParts3D 4.0, 2 234 mesh, 3 432 nom, CC BY 4.0 (manba ko'rsatiladi).
  Ma'lumot GLB emas: `public/models/atlas.json` (katalog) + `body-0..14.bin` (brauzer uchun o'z formati).
- Muqobil: Z-Anatomy (CC BY-SA).

## Saqlash qarori
Barcha a'zolarni oldindan GLB qilmaymiz va har safar GitHub'dan ham chaqirmaymiz:
1. Manba ma'lumot (BodyParts3D, aniq versiya) + katalog bir marta serverga olinadi.
2. GLB kerak bo'lganda qismlardan yig'iladi va keshlanadi (slayd sahnasi bo'yicha).
3. Ko'p ishlatiladigan to'plamlar (bosh suyagi, yurak, miya, skelet...) oldindan tayyorlab qo'yiladi.

## 1-bosqich: nima qilindi
- `tools/med3d_tayyorla.py` — atlasdan sahna guruhlarini GLB ga aylantiradi (bir marta, hostdan tashqarida).
  Natija: `assets/med3d/<sahna>/<guruh>.glb` + `scene.json`. Bosh suyagi: cranium 1.5 MB, mandible 0.3 MB.
- Guruhlar bir xil chegara qutisiga ega (ko'rinmas nol yuzali uchburchak) — bir ramkada aniq yopishadi.
- `services/med3d/pptx3d.py` — `am3d:model3d` XML (OfficeCLI namunasi asosida), zaxira — 1×1 bo'sh PNG.
- `services/med3d/camera.py` — PowerPoint kamerasining nusxasi: ramka joyi va yorliq nuqtalari.
  Aylanish yo'nalishi taxmin (o'ng qo'l qoidasi, XYZ) — PowerPoint'da tekshirish kerak, xato bo'lsa `SIGN`.
- `services/med3d/deck.py` — reja (JSON) → PPTX: chapda matn, o'ngda 3D, yorliqlar, Morph 2.2 s.
- Test: `python test_med3d.py`.

## Keyingi bosqichlar
1. Demo faylni haqiqiy PowerPoint'da tekshirish (aylanish yo'nalishi, yorliq nuqtalari aniqligi).
2. Yangi sahnalar: yurak, miya, skelet, o'pka, ko'z...
3. AI rejasi: mavzu → sahna, slaydlar, burchaklar, yorliqlar (faqat katalogdan).
4. Botga ulash: "kompyuterda oching" ogohlantirishi bilan.

## Kelishuv: to'liq avtomatlashtirish (qabul qilindi)
Sahnalarni qo'lda tayyorlash shart emas — tizim mavzu so'ralgan zahoti 3D taqdimotni o'zi yasaydi:
1. Atlas (siqilgan ~33 MB) serverda turadi; GLB yig'ish yengil (bosh suyagi ~0.5 s) — hostda so'rov paytida.
2. **Organlar lug'ati** (bir marta): atlas qismlari organlarga guruhlanadi (chap/o'ng, bo'laklar, takrorlar
   birlashtiriladi), har biriga tekshirilgan o'zbekcha nom va rang. Sabab: atlas nomlari doim mantiqiy emas
   (jigar "Hepatovenous segment" deb vena tizimida; "liver" tushunchasida faqat tomirlar; takror id lar).
3. Har so'rovda AI shu lug'atdan organlarni tanlaydi, slaydlar rejasini yozadi; mayda organlar uchun
   kichikroq sahna (chegara qutisi) avtomatik; natija keshlanadi.
4. Botda yangi tur sifatida (pro3d kabi): mos organ topilmasa — oldindan aytiladi, pul yechilmaydi.
Holat: YOZILDI (3D Anatomiya). Qo'lda sahnalar (skull, digestive) namuna sifatida qoldi.

### Avtomatik tizim — qanday ishlaydi
- `services/med3d/lugat.py` — ~100 organ: o'zbekcha nom, rang, erkak/ayol atlasidagi qoidalar, `inside`.
  `tools/med3d_lugat.py` → `assets/med3d/lugat.json` (qism id lari, chegaralar, nuqtalar).
- `services/med3d/manba.py` — atlas (slorksmo/Human-Atlas, aniq commit) birinchi so'rovda `data/med3d_atlas/`
  ga yuklanadi (~130 MB, git'da emas). Oldindan: `python tools/med3d_lugat.py --yukla`.
- `services/med3d/auto.py` — AI reja (MED3D_MODEL, sukut Claude Sonnet 5; zaxira — premium zanjiri):
  mavzu anatomiya emasmi (NotAnatomy → pul qaytadi), tana, organlar, burchaklar, yorliqlar. Reja tekshiriladi;
  yashirin organ ochiladi; slaydlar sahnalarga bo'linadi (3D ramka ≤ 26"); katta organ soddalashtiriladi
  (`simplify.py`); bir xil GLB slaydlar orasida bitta fayl.
- Bot: "🫀 3D Anatomiya" — bosilganda ogohlantirish (faqat tana tuzilishi, kompyuterda) + Ha/Yo'q;
  manba so'ralmaydi; narx oddiy taqdimotdek; hozircha faqat adminlarga (hammaga: `MED3D_OCHIQ=1`).
- Testlar: `python test_med3d.py`, `python test_med3d_auto.py`.
- PowerPoint'da tekshirilishi kerak: aylanish yo'nalishi, yorug'lik, bir GLB ni bir necha slayd ulashishi.

## Ayol tanasi (topildi)
- Manba: https://github.com/slorksmo/Human-Atlas — human-atlas'ning ayol tanasi qo'shilgan versiyasi.
  `public/models/atlas-female.json` + `female-N.bin` — biz o'qiydigan format bilan bir xil
  (`Atlas(dir, "atlas-female.json")`). Ma'lumot: Human Reference Atlas female v1.10 (HuBMAP), NLM
  Visible Human Female asosida, CC BY 4.0. Oyoq mushaklari: Andreassen et al. 2023, CC BY 4.0.
- 1 220 tuzilma, ~2.77 mln uchburchak: reproduktiv (bachadon qismlari, naylar, tuxumdonlar, qin,
  boylamlar — 38), homiladorlik (yo'ldosh, kindik tizimchasi, amnion — 8), yurak (bo'lmacha, qorincha,
  klapanlar — 14), hazm (84; quloq oldi bezi, tanglay, ko'r ichak, sigmasimon ichak ham bor), miya (283),
  buyrak (87).
- Kamchilik: manbada bosh suyagi, qovurg'a, yelka, qo'l va oyoq panjasi suyaklari yo'q, mushak deyarli yo'q;
  repo ularni erkak tanasidan olib to'ldirgan (`system: "borrowed"`) — ayolga xos emas.
- Tekshirildi: bachadon+naylar+tuxumdonlar, yurak, yo'ldosh GLB qilib chizildi — sifat yaxshi.
- Diqqat: nom bo'yicha qidirishda "Cervi" bo'yin umurtqalarini ham topadi — tizim (system) bo'yicha filtrlash shart.

## Haqiqiy 3D, joyida almashish, lotincha nomlar (2026-10)
- Muammo: PowerPoint har 3D modelni alohida qatlam qilib chizadi, modellar orasida chuqurlikni solishtirmaydi —
  alohida organlar bo'lsa tomir yurak orqasiga kirmay ustiga chiqib qolardi. Qaror: slayddagi hamma organ
  BITTA GLB (`auto.build_scenes`, nomi organlar to'plamidan — `set_id`).
- Harakat: to'plam o'zgarmasa — bir xil nomli model, Morph aylantiradi/yaqinlashtiradi. To'plam o'zgarsa —
  yordamchi slayd (`fade`, `auto`: advTm=0, raqamga kirmaydi, `frame_of` — kamera joyida): eski model so'nadi,
  yangisi o'sha joyda paydo bo'ladi (soya to'plamga bog'liq emas — qolayotgan organ piksellari bir xil), keyin
  yangi model burilib yangi joyiga keladi. Sahna almashganda — avvalgidek uchib ketish/kelish.
- Yorliq: o'zbekcha nom + lotincha nom (`lugat.LATIN`, Terminologia Anatomica). Boshqa organ ortida
  yopilgan organga yorliq qo'yilmaydi (`Camera.visible_share` — to'suvchilar organ to'ridan olingan zich
  nuqtalar bilan chuqurlik xaritasiga chiziladi).
- Yaqinlashish cheklovi: fokus butun ko'rinishdan `ZOOM_LIMIT` (1.6) martadan katta bo'lmaydi.
- Tekshiruv: PowerPoint Linux'da yo'q — Morph simulyatori (three.js, kadrma-kadr, MP4) bilan ko'rilgan;
  haqiqiy PowerPoint'da tekshirish kerak: yordamchi slayd o'zi o'tishi, so'nish paytidagi xiralashish.

## Dizayn tizimi va harakat rejissyori (2026-10)
- `design.py`: 12 uslub (kobalt, atlas, vitrina, rentgen, pastel, laboratoriya, klinik, zumrad, okean, grafit,
  oq, shafaq) — fon/gradient, shriftlar, yorliq turi (pill/tag/plain), chiziq (to'g'ri/tirsakli/egri), Morph
  qiladigan fon bezaklari, model ostidagi soya, model ohangi (real/pastel/ivory/xray/warm), 3D yorug'lik to'plami.
  6 kompozitsiya: chap_matn, ong_matn, markaz, qahramon, karta, pastki.
- Hamma narsa Morph qiladi: sarlavha, matn, panel, bezaklar, soya; yorliqlar yondan suzib kiradi.
- `director.py`: har slaydga kompozitsiya va kamera harakati (orbita, aylanish, yuqoridan/pastdan, yaqin/uzoq,
  sayohat, portlash) — ketma-ket takrorlanmaydi; asosiy burchak — fokus yaxshi ko'rinadigan, old tomondagi.
- Portlash: organlar alohida modelga almashadi, ajraladi, qayta yig'iladi, yaxlit modelga qaytadi.
- Savol slaydi (8+ slayd): raqamli belgilar, javoblar bosilganda chiqadi.
- To'qima naqshlari: mushak tolasi, o'pka g'ovakligi, suyak donadorligi (`ao.pattern`).
- Botda uslub tanlash qadami (namuna rasm `assets/med3d/uslublar.jpg`, «Avtomatik» — mavzuga qarab).
- Sifat nazorati (`deck.quality`): yorliqlar ustma-ust/matnga, model matnga tegmasligi — logga yoziladi.
