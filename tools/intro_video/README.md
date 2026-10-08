# Tanishtiruv videosi (bosh sahifa, kirgan foydalanuvchi uchun)

Saytdagi video: `webapp/site/static/intro-wide.mp4` (kompyuter, 16:9) va `intro-tall.mp4` (telefon, 9:16),
muqovalari `intro-wide.jpg`, `intro-tall.jpg`. Bu papka — o'sha videoni qayta yozib olish vositalari.

Video saytning o'zidan yozib olinadi: haqiqiy sahifalar, haqiqiy slayd generatori. Faqat AI soxta
(kredit sarflanmaydi), do'kon namunaviy ishlar bilan to'ldiriladi, mijoz ma'lumotlari ishlatilmaydi.

## Fayllar

| Fayl | Vazifasi |
|---|---|
| `scenes.json` | 14 sahna: nomi va ovoz matni (subtitr ham shundan) |
| `demo_content.py` | Namoyish taqdimoti slaydlari va do'kondagi namunaviy ishlar |
| `prep_shop.py`, `shot_dir.js` | Do'kon ishlarining oldindan ko'rish rasmlari (`shop_prev/`) |
| `videoserver.py` | Namoyish serveri (port 8798), soxta AI, foydalanuvchi «Ali Valiyev» |
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
# 4) ovozni bo'lish va yig'ish
python align.py
python assemble.py rec_d out/edufayl_intro_desktop.mp4 --audio audio
python assemble.py rec_m out/edufayl_intro_mobile.mp4 --audio audio
# 5) sayt uchun siqish
ffmpeg -i out/edufayl_intro_desktop.mp4 -vf scale=1280:720 -c:v libx264 -preset slow -crf 25 -c:a aac -b:a 96k -ac 1 \
  -movflags +faststart ../../webapp/site/static/intro-wide.mp4
ffmpeg -i out/edufayl_intro_mobile.mp4 -vf scale=720:1280 -c:v libx264 -preset slow -crf 25 -c:a aac -b:a 96k -ac 1 \
  -movflags +faststart ../../webapp/site/static/intro-tall.mp4
```

Kerak: `ffmpeg` (libx264, libass), Node + `playwright-core` (`PW_CORE` bilan yo'lini berish mumkin),
Chromium (`CHROME` o'zgaruvchisi). Matn o'zgarsa: `scenes.json` ni tahrirlang, yangi ovoz yozdiring
(`audio/narration.mp3`, sahnalar orasida qisqa pauza), so'ng 4–5-qadamlar. `--no-subs` — subtitrsiz.
