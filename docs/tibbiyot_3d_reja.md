# Tibbiyot uchun 3D taqdimot — reja (hali amalga oshirilmagan)

Holat: g'oya va tadqiqot. Hozircha kod yozilmaydi.

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
