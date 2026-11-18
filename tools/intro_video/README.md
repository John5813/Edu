# Tanishtiruv videosi (bosh sahifa, kirgan foydalanuvchi uchun)

Saytdagi video: `webapp/site/static/intro-wide.mp4` (kompyuter, 16:9) va `intro-tall.mp4` (telefon, 9:16),
muqovalari `intro-wide.webp`, `intro-tall.webp`. Bu papka — o'sha videoni qayta yozib olish vositalari.

Video saytning o'zidan yozib olinadi: haqiqiy sahifalar, haqiqiy slayd generatori. Faqat AI soxta
(kredit sarflanmaydi), do'kon namunaviy ishlar bilan to'ldiriladi, mijoz ma'lumotlari ishlatilmaydi.

## Fayllar

| Fayl | Vazifasi |
|---|---|
| `scenes.json` | 14 sahna: nomi va ovoz matni (subtitr ham shundan). Ovoz yozdirish uchun jadval: `docs/video/tanishtiruv_video_ovoz_matni.xlsx` |
| `botchat.html` | Videoning boshidagi bot suhbati (Taqdimot → «🌐 Ochish» → saytga haqiqiy /go kirishi) va oxiridagi «fayl botga keldi» |
| `demo_content.py` | Namoyish taqdimoti slaydlari va do'kondagi namunaviy ishlar |
| `prep_shop.py`, `shot_dir.js` | Do'kon ishlarining oldindan ko'rish rasmlari (`shop_prev/`) |
| `videoserver.py` | Namoyish serveri (port 8798), soxta AI, foydalanuvchi «Ali Valiyev», sayt rejimi yoqilgan; `/demo/bot`, `/demo/go` (kirish havolasi), `/demo/pay` (Click to'lovi o'rnida: yetishmagan summa tushadi va kutayotgan buyurtma o'zi boshlanadi). Balans boshida `BALANCE` (sukut 0) |
| `fake_docs.py` | Hujjat xizmatlari uchun soxta AI (videoserver undan foydalanadi) |
| `record.js` | Saytni brauzerda bosib, kadrlarni yozib oladi (`desktop` yoki `mobile`) |
| `audio/narration.mp3` | Ovoz yozuvi (bitta fayl, sahnalar ketma-ket) |
| `align.py` | Ovozni pauzalar bo'yicha sahnalarga bo'ladi: `audio/01.wav … 14.wav` + `cues.json` (subtitr vaqtlari) |
| `assemble.py` | Kadrlar + ovoz + subtitr → MP4; har sahna o'z ovozi uzunligiga moslanadi |

## Qayta yaratish

```bash
cd tools/intro_video
# 1) do'kon rasmlari
python prep_shop.py && node shot_dir.js shop_html shop_prev
# 2) server (alohida oynada)
python videoserver.py
# 3) yozib olish
node record.js desktop rec_d
node record.js mobile rec_m
# 4) ovoz: har sahna alohida fayl (audio/01.mp3 … 14.mp3) bo'lsa align.py shart emas;
#    bitta narration.mp3 bo'lsa — pauzalar bo'yicha bo'linadi:
python align.py
python assemble.py rec_d out/edufayl_intro_desktop.mp4 --audio audio
python assemble.py rec_m out/edufayl_intro_mobile.mp4 --audio audio
# 5) sayt uchun siqish
ffmpeg -i out/edufayl_intro_desktop.mp4 -vf scale=1280:720 -c:v libx264 -preset slow -crf 25 -c:a aac -b:a 96k -ac 1 \
  -movflags +faststart ../../webapp/site/static/intro-wide.mp4
ffmpeg -i out/edufayl_intro_mobile.mp4 -vf scale=720:1280 -c:v libx264 -preset slow -crf 25 -c:a aac -b:a 96k -ac 1 \
  -movflags +faststart ../../webapp/site/static/intro-tall.mp4
# 6) muqovalar (videoning 25-soniyasidan)
ffmpeg -ss 25 -i ../../webapp/site/static/intro-wide.mp4 -frames:v 1 -c:v libwebp -quality 80 ../../webapp/site/static/intro-wide.webp
ffmpeg -ss 25 -i ../../webapp/site/static/intro-tall.mp4 -frames:v 1 -c:v libwebp -quality 80 ../../webapp/site/static/intro-tall.webp
```

Kerak: `ffmpeg` (libx264, libass), Node + `playwright` (`PW_CORE` bilan boshqasini berish mumkin),
Chromium (o'rnatilgani ishlatiladi; boshqasi — `CHROME` o'zgaruvchisi). Har yozuvdan oldin serverni qayta ishga tushiring
(buyurtma, to'lov va balans holati yozuvdan keyin o'zgaradi). Matn o'zgarsa: `scenes.json` ni tahrirlang, yangi ovoz yozdiring
(`audio/narration.mp3`, sahnalar orasida qisqa pauza), so'ng 4–5-qadamlar. `--no-subs` — subtitrsiz.
