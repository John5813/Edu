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
